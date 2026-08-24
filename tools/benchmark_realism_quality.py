"""Compare uniform baseline generation with public-distribution-calibrated generation."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "generate-synthetic-data" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_spec  # noqa: E402
import generate  # noqa: E402
import materialize_spec  # noqa: E402

DEFAULT_SPEC = ROOT / "datasets" / "public-data" / "realism" / "aggregate-spec.json"
DEFAULT_JSON = ROOT / "datasets" / "public-data" / "realism" / "quality-benchmark.json"
DEFAULT_MARKDOWN = ROOT / "datasets" / "public-data" / "realism" / "quality-benchmark.md"


def flatten_weights(spec: dict[str, Any]) -> dict[str, Any]:
    baseline = copy.deepcopy(spec)
    for column in baseline["columns"]:
        generator = column.get("generator")
        if generator:
            generator["tokens"] = {value: 1 for value in generator["tokens"]}
            generator["lengths"] = {value: 1 for value in generator["lengths"]}
        surrogate = column.get("surrogate", {})
        for component in surrogate.get("components", {}).values():
            if isinstance(component.get("values"), dict):
                component["values"] = {value: 1 for value in component["values"]}
    return baseline


def final_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    columns = materialize_spec.normalize_columns(spec)
    rows = materialize_spec.generate_rows(spec, columns, spec["rows"], spec["seed"])
    frame = pd.DataFrame(rows)
    roles = {role: [column["name"] for column in columns if column["role"] == role] for role in generate.ROLES}
    for offset, column in enumerate(columns):
        if column["role"] != "identifier":
            continue
        config = materialize_spec.policy_column(column)
        frame[column["name"]] = generate.weighted_template_values(
            len(frame),
            spec["seed"] + 1000 + offset,
            column["name"],
            config,
            roles,
            frame,
        )
    return frame.to_dict(orient="records")


def selected_metrics(report: dict[str, Any]) -> dict[str, float | None]:
    identifiers = report["metrics"]["identifier_templates"]
    selected: dict[str, float | None] = {
        "text.token_tv": report["metrics"]["text_distributions"]["consumer_summary"]["token_tv"],
        "text.length_tv": report["metrics"]["text_distributions"]["consumer_summary"]["length_tv"],
    }
    for column, values in identifiers.items():
        for component, tv in values["component_tv"].items():
            selected[f"{column}.{component}.tv"] = tv
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.spec.is_file():
        raise FileNotFoundError(args.spec)
    existing = [path for path in (args.json, args.markdown) if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite: {', '.join(str(path) for path in existing)}")
    target = json.loads(args.spec.read_text(encoding="utf-8"))
    calibrated_rows = final_rows(target)
    baseline_rows = final_rows(flatten_weights(target))
    calibrated_report = evaluate_spec.evaluate(target, calibrated_rows)
    baseline_report = evaluate_spec.evaluate(target, baseline_rows)
    calibrated = selected_metrics(calibrated_report)
    baseline = selected_metrics(baseline_report)
    improvements = {
        key: (baseline[key] - calibrated[key] if baseline[key] is not None and calibrated[key] is not None else None)
        for key in calibrated
    }
    report = {
        "schema_version": 1,
        "spec": str(args.spec),
        "rows": target["rows"],
        "baseline": {
            "method": "uniform component and token weights",
            "passed": baseline_report["passed"],
            "failed_gates": baseline_report["failed_gates"],
            "metrics": baseline,
        },
        "calibrated": {
            "method": "published aggregate component and token weights",
            "passed": calibrated_report["passed"],
            "failed_gates": calibrated_report["failed_gates"],
            "metrics": calibrated,
        },
        "absolute_tv_reduction": improvements,
        "passed": calibrated_report["passed"]
        and any(value is not None and value >= 0.05 for value in improvements.values()),
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Realism quality benchmark",
        "",
        f"Rows: {target['rows']:,}. Overall gate: **{'PASS' if report['passed'] else 'FAIL'}**.",
        "",
        "| Metric | Uniform baseline TV | Calibrated TV | Absolute reduction |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key in calibrated:
        lines.append(f"| `{key}` | {baseline[key]:.4f} | {calibrated[key]:.4f} | {improvements[key]:.4f} |")
    lines.extend(
        [
            "",
            "Lower total-variation distance is better. This benchmark measures distribution fidelity only; it does not "
            "claim that generated text is semantically coherent or that generated addresses are deliverable.",
        ]
    )
    args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "json": str(args.json), "markdown": str(args.markdown)}, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

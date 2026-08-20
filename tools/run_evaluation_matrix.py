from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "evaluations" / "catalog.json"
MODALITY_ORDER = ("tabular", "tabular+text")


def load_catalog(path: Path) -> dict[str, Any]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("evaluation catalog schema_version must be 1")
    scenarios = catalog.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("evaluation catalog must contain scenarios")
    identifiers = [scenario.get("id") for scenario in scenarios]
    if len(set(identifiers)) != len(identifiers) or any(not identifier for identifier in identifiers):
        raise ValueError("evaluation scenario ids must be present and unique")
    orders = [scenario.get("order") for scenario in scenarios]
    if orders != list(range(1, len(scenarios) + 1)):
        raise ValueError("evaluation scenarios must use contiguous order values starting at 1")
    modalities = [scenario.get("modality") for scenario in scenarios]
    required = list(MODALITY_ORDER)
    if modalities[: len(required)] != required:
        raise ValueError(f"the first scenarios must be ordered as: {', '.join(required)}")
    return catalog


def source_rows(scenario_id: str, count: int) -> tuple[list[str], list[dict[str, Any]]]:
    if scenario_id == "tabular":
        columns = ["customer_id", "region", "age_band", "monthly_spend", "account_tier"]
        regions = ("north", "south", "east", "west")
        age_bands = ("18-29", "30-44", "45-59", "60+")
        tiers = ("standard", "plus", "premium")
        rows = [
            {
                "customer_id": f"real-customer-{index:04d}",
                "region": regions[index % len(regions)],
                "age_band": age_bands[(index // 3) % len(age_bands)],
                "monthly_spend": round(35.0 + (index % 24) * 3.75 + (index // 24) * 0.17, 2),
                "account_tier": tiers[(index // 5) % len(tiers)],
            }
            for index in range(count)
        ]
        return columns, rows
    if scenario_id == "tabular-text":
        columns = ["ticket_id", "channel", "resolution_hours", "topic", "message"]
        channels = ("email", "chat", "phone")
        topics = ("billing", "delivery", "account", "returns")
        messages = (
            "The invoice total was unclear and support explained every charge.",
            "My parcel arrived late but the agent provided a useful update.",
            "Account access failed once and the reset instructions solved it.",
            "The return label worked and the refund status was easy to follow.",
            "Billing support answered quickly and corrected the duplicate fee.",
            "Delivery tracking stopped updating before the package arrived.",
            "The account setup guide was concise and easy to understand.",
            "Return instructions were accurate and the process felt simple.",
        )
        rows = [
            {
                "ticket_id": f"real-ticket-{index:04d}",
                "channel": channels[index % len(channels)],
                "resolution_hours": round(0.75 + (index % 18) * 0.6 + (index // 18) * 0.03, 2),
                "topic": topics[index % len(topics)],
                "message": messages[index % len(messages)],
            }
            for index in range(count)
        ]
        return columns, rows
    raise ValueError(f"no source fixture builder for scenario: {scenario_id}")


def write_source(path: Path, scenario: dict[str, Any]) -> None:
    columns, rows = source_rows(str(scenario["id"]), int(scenario["rows"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "exit_code": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def planner_command(scenario: dict[str, Any], paths: dict[str, Path]) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "skills" / "plan-synthetic-data" / "scripts" / "plan.py"),
        str(paths["source"]),
        str(paths["policy"]),
        "--public",
        ",".join(scenario["public"]),
        "--protected",
        ",".join(scenario["protected"]),
        "--identifier",
        ",".join(scenario["identifier"]),
        "--quality-profile",
        "fast",
        "--max-epochs",
        "2",
        "--max-training-minutes",
        "1",
        "--output",
        str(paths["candidate"]),
        "--report",
        str(paths["generation_report"]),
        "--workspace",
        str(paths["workspace"]),
        "--rows",
        str(scenario["rows"]),
        "--seed",
        str(scenario["seed"]),
    ]
    for column, encoding in scenario.get("encodings", {}).items():
        command.extend(["--encoding", f"{column}={encoding}"])
    for name, value in scenario.get("quality_acceptance", {}).items():
        command.extend(["--acceptance", f"{name}={value}"])
    return command


def evaluate_command(
    paths: dict[str, Path],
    synthetic: Path,
    output: Path,
    generation_report: Path | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "skills" / "evaluate-synthetic-data" / "scripts" / "evaluate.py"),
        str(paths["source"]),
        str(synthetic),
        str(paths["policy"]),
        str(output),
    ]
    if generation_report is not None:
        command.extend(["--generation-report", str(generation_report)])
    return command


def report_metrics(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    report = json.loads(path.read_text(encoding="utf-8"))
    quality = report.get("quality", {})
    distributions = quality.get("distributions", {})
    text = quality.get("text", {})
    return {
        "passed": report.get("passed"),
        "failed_gates": report.get("failed_gates", []),
        "mean_numeric_ks": distributions.get("mean_numeric_ks"),
        "mean_categorical_tv": distributions.get("mean_categorical_tv"),
        "mean_text_length_ks": text.get("mean_length_ks"),
        "mean_text_tfidf_distance": text.get("mean_tfidf_centroid_distance"),
        "propensity_auc": quality.get("propensity_auc"),
        "exact_replay": report.get("privacy", {}).get("exact_modeled_row_replay_ratio"),
        "identifier_overlap": report.get("privacy", {}).get("identifier_overlap"),
    }


def run_scenario(scenario: dict[str, Any], output_root: Path) -> dict[str, Any]:
    root = output_root / f"{int(scenario['order']):02d}-{scenario['id']}"
    paths = {
        "source": root / "source.csv",
        "policy": root / "policy.json",
        "candidate": root / "candidate.csv",
        "generation_report": root / "generation.json",
        "workspace": root / "workspace",
        "evaluation": root / "evaluation.json",
        "negative_evaluation": root / "negative-control.evaluation.json",
    }
    write_source(paths["source"], scenario)
    commands: dict[str, dict[str, Any]] = {}
    commands["plan"] = run_command(planner_command(scenario, paths), ROOT)
    if commands["plan"]["exit_code"] == 0:
        commands["dry_run"] = run_command(
            [
                sys.executable,
                str(ROOT / "skills" / "generate-synthetic-data" / "scripts" / "generate.py"),
                str(paths["policy"]),
                "--dry-run",
            ],
            ROOT,
        )
        commands["generate"] = run_command(
            [
                sys.executable,
                str(ROOT / "skills" / "generate-synthetic-data" / "scripts" / "generate.py"),
                str(paths["policy"]),
            ],
            ROOT,
        )
        if commands["generate"]["exit_code"] == 0:
            commands["evaluate"] = run_command(
                evaluate_command(paths, paths["candidate"], paths["evaluation"], paths["generation_report"]),
                ROOT,
            )
        commands["negative_control"] = run_command(
            evaluate_command(paths, paths["source"], paths["negative_evaluation"]),
            ROOT,
        )
    expected = {
        "plan": 0,
        "dry_run": 0,
        "generate": 0,
        "evaluate": 0,
        "negative_control": 2,
    }
    checks = {name: commands.get(name, {}).get("exit_code") == code for name, code in expected.items()}
    return {
        "order": scenario["order"],
        "id": scenario["id"],
        "modality": scenario["modality"],
        "request": scenario["request"],
        "passed": all(checks.values()),
        "checks": checks,
        "commands": commands,
        "candidate_metrics": report_metrics(paths["evaluation"]),
        "negative_control_metrics": report_metrics(paths["negative_evaluation"]),
        "artifacts": {name: str(path) for name, path in paths.items() if name != "workspace"},
    }


def markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Rata Evaluation State of the Art",
        "",
        f"Evidence run: `{summary['captured_utc']}`",
        "",
        "This report records an executable, ordered assessment of the repository. It is evidence for these",
        "fixtures and",
        "configured gates, not a general utility claim and not proof of anonymization.",
        "",
        "## Ordered scenarios",
        "",
        "| Order | Scenario | Modality | Candidate | Negative control | Overall |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for scenario in summary["scenarios"]:
        candidate = scenario["candidate_metrics"]
        negative = scenario["negative_control_metrics"]
        lines.append(
            f"| {scenario['order']} | `{scenario['id']}` | {scenario['modality']} | "
            f"{'pass' if candidate and candidate['passed'] else 'fail/not run'} | "
            f"{'rejected' if negative and not negative['passed'] else 'unexpected'} | "
            f"{'pass' if scenario['passed'] else 'fail'} |"
        )
    for scenario in summary["scenarios"]:
        lines.extend(["", f"## {scenario['order']}. {scenario['id']}", "", scenario["request"], ""])
        metrics = scenario["candidate_metrics"]
        if metrics:
            lines.extend(
                [
                    f"- Candidate passed: `{metrics['passed']}`",
                    f"- Failed gates: `{', '.join(metrics['failed_gates']) or 'none'}`",
                    f"- Mean numeric KS: `{metrics['mean_numeric_ks']}`",
                    f"- Mean categorical TV: `{metrics['mean_categorical_tv']}`",
                    f"- Mean text length KS: `{metrics['mean_text_length_ks']}`",
                    f"- Mean text TF-IDF centroid distance: `{metrics['mean_text_tfidf_distance']}`",
                    f"- Propensity AUC: `{metrics['propensity_auc']}`",
                    f"- Exact modeled-row replay: `{metrics['exact_replay']}`",
                ]
            )
        negative = scenario["negative_control_metrics"]
        if negative:
            lines.append(f"- Negative-control failed gates: `{', '.join(negative['failed_gates'])}`")
    lines.extend(
        [
            "",
            "## Interpretation and limits",
            "",
            "- The tabular path covers marginal distribution, correlation, propensity, replay, overlap, schema,",
            "  and evidence gates.",
            "- `TABULAR_CHARACTER` columns use length-distribution KS and character n-gram TF-IDF centroid",
            "  distance instead of exact-category TV.",
            "- TF-IDF is lexical rather than semantic; human review and downstream-task evaluation remain",
            "  necessary for language quality.",
            "- Text nearest-neighbor similarity and exact replay are diagnostics, not formal privacy guarantees.",
            "- Only a bound DP checkpoint supports a differential-privacy claim when private columns are present.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ordered Rata tabular and tabular-plus-text evaluation matrix."
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        if not args.overwrite:
            raise FileExistsError(f"refusing to overwrite evidence directory: {args.output_dir}")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(args.catalog)
    summary = {
        "schema_version": 1,
        "captured_utc": datetime.now(UTC).isoformat(),
        "catalog": str(args.catalog.resolve()),
        "scenarios": [run_scenario(scenario, args.output_dir) for scenario in catalog["scenarios"]],
    }
    summary["passed"] = all(scenario["passed"] for scenario in summary["scenarios"])
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "state-of-art.md").write_text(markdown_report(summary), encoding="utf-8")
    print(json.dumps({"passed": summary["passed"], "summary": str(args.output_dir / "summary.json")}, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

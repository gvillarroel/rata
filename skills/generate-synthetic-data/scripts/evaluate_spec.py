# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from materialize_spec import correlation_contract, normalize_columns, numeric_distribution, parse_datetime, sha256_file

DEFAULT_ACCEPTANCE = {
    "max_missing_rate_delta": 0.05,
    "max_numeric_mean_relative_error": 0.15,
    "max_numeric_std_relative_error": 0.2,
    "max_numeric_bounds_violation_ratio": 0.0,
    "max_categorical_tv": 0.15,
    "max_correlation_delta": 0.2,
    "min_identifier_uniqueness_ratio": 1.0,
}


def load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    if suffix == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("JSON synthetic data must contain an array of objects")
        return rows
    if suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("JSONL synthetic data must contain one object per line")
        return rows
    raise ValueError("constraint evaluation supports CSV, JSON, JSONL, or NDJSON")


def missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def safe_float(value: Any) -> float | None:
    if missing(value) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def target_numeric_moments(distribution: dict[str, Any]) -> tuple[float, float]:
    if distribution["kind"] == "normal":
        return distribution["mean"], distribution["std"]
    if distribution["kind"] == "uniform":
        width = distribution["max"] - distribution["min"]
        return (distribution["min"] + distribution["max"]) / 2, width / math.sqrt(12)
    return distribution["value"], 0.0


def relative_error(observed: float, expected: float, scale: float) -> float:
    return abs(observed - expected) / max(abs(expected), abs(scale), 1e-9)


def categorical_target(column: dict[str, Any]) -> dict[str, float]:
    if column["type"] == "boolean" and "values" not in column:
        probability_true = float(column.get("probability_true", 0.5))
        return {"false": 1 - probability_true, "true": probability_true}
    raw = column["values"]
    if isinstance(raw, list):
        return {str(value): 1 / len(raw) for value in raw}
    total = sum(float(weight) for weight in raw.values())
    return {str(value): float(weight) / total for value, weight in raw.items()}


def categorical_tv(values: list[Any], expected: dict[str, float]) -> float | None:
    observed_values = [
        str(value).lower() if isinstance(value, bool) else str(value) for value in values if not missing(value)
    ]
    if not observed_values:
        return None
    counts = Counter(observed_values)
    categories = set(counts) | set(expected)
    return 0.5 * sum(
        abs(counts[category] / len(observed_values) - expected.get(category, 0.0)) for category in categories
    )


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    if not left_scale or not right_scale:
        return None
    return numerator / (left_scale * right_scale)


def gate(name: str, value: Any, threshold: Any, operator: str, required: bool = True) -> dict[str, Any]:
    if not required:
        passed = True
    elif operator == "eq":
        passed = value == threshold
    elif operator == "lte":
        passed = value is not None and value <= threshold
    elif operator == "gte":
        passed = value is not None and value >= threshold
    else:
        raise ValueError(f"unsupported gate operator: {operator}")
    return {
        "name": name,
        "value": value,
        "threshold": threshold,
        "operator": operator,
        "required": required,
        "passed": passed,
    }


def evaluate(spec: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("synthetic dataset has no rows")
    columns = normalize_columns(spec)
    configured = {column["name"]: column for column in columns}
    observed_columns = set().union(*(row.keys() for row in rows))
    released = {column["name"] for column in columns if column["role"] != "drop"}
    dropped = {column["name"] for column in columns if column["role"] == "drop"}
    missing_columns = sorted(released - observed_columns)
    unexpected_columns = sorted(observed_columns - released)
    unexpected_dropped = sorted(observed_columns & dropped)
    acceptance = {**DEFAULT_ACCEPTANCE, **spec.get("acceptance", {})}
    metrics: dict[str, Any] = {
        "missing_rate_delta": {},
        "numeric": {},
        "categorical_tv": {},
        "datetime": {},
        "identifier_uniqueness": {},
        "correlations": {},
    }
    gates = [
        gate("released_columns_present", not missing_columns, True, "eq"),
        gate("unexpected_columns_absent", not unexpected_columns, True, "eq"),
        gate("dropped_columns_absent", not unexpected_dropped, True, "eq"),
    ]
    for name in sorted(released & observed_columns):
        column = configured[name]
        values = [row.get(name) for row in rows]
        observed_missing = sum(missing(value) for value in values) / len(values)
        missing_delta = abs(observed_missing - column["missing_rate"])
        metrics["missing_rate_delta"][name] = missing_delta
        gates.append(
            gate(
                f"column.{name}.missing_rate_delta",
                missing_delta,
                acceptance["max_missing_rate_delta"],
                "lte",
            )
        )
        if column["type"] in {"number", "integer"}:
            distribution = numeric_distribution(column)
            numeric_values = [value for raw in values if (value := safe_float(raw)) is not None]
            expected_mean, expected_std = target_numeric_moments(distribution)
            observed_mean = fmean(numeric_values) if numeric_values else None
            observed_std = pstdev(numeric_values) if numeric_values else None
            mean_error = (
                relative_error(observed_mean, expected_mean, expected_std) if observed_mean is not None else None
            )
            std_error = relative_error(observed_std, expected_std, expected_mean) if observed_std is not None else None
            minimum = distribution.get("min")
            maximum = distribution.get("max")
            violations = [
                value
                for value in numeric_values
                if (minimum is not None and value < minimum) or (maximum is not None and value > maximum)
            ]
            violation_ratio = len(violations) / len(numeric_values) if numeric_values else None
            metrics["numeric"][name] = {
                "observed_mean": observed_mean,
                "expected_mean": expected_mean,
                "observed_std": observed_std,
                "expected_std": expected_std,
                "mean_relative_error": mean_error,
                "std_relative_error": std_error,
                "bounds_violation_ratio": violation_ratio,
            }
            gates.extend(
                [
                    gate(
                        f"column.{name}.numeric_mean_relative_error",
                        mean_error,
                        acceptance["max_numeric_mean_relative_error"],
                        "lte",
                    ),
                    gate(
                        f"column.{name}.numeric_std_relative_error",
                        std_error,
                        acceptance["max_numeric_std_relative_error"],
                        "lte",
                        required=distribution["kind"] != "constant",
                    ),
                    gate(
                        f"column.{name}.numeric_bounds_violation_ratio",
                        violation_ratio,
                        acceptance["max_numeric_bounds_violation_ratio"],
                        "lte",
                        required=minimum is not None or maximum is not None,
                    ),
                ]
            )
        elif column["type"] in {"categorical", "boolean", "string"}:
            tv = categorical_tv(values, categorical_target(column))
            metrics["categorical_tv"][name] = tv
            gates.append(gate(f"column.{name}.categorical_tv", tv, acceptance["max_categorical_tv"], "lte"))
        elif column["type"] == "datetime":
            start = parse_datetime(column["min"], f"{name}.min")
            end = parse_datetime(column["max"], f"{name}.max")
            parsed = []
            invalid = 0
            for value in values:
                if missing(value):
                    continue
                try:
                    parsed.append(parse_datetime(str(value), name))
                except ValueError:
                    invalid += 1
            outside = sum(value < start or value > end for value in parsed)
            violation_ratio = (invalid + outside) / max(1, len(parsed) + invalid)
            metrics["datetime"][name] = {"bounds_or_parse_violation_ratio": violation_ratio}
            gates.append(gate(f"column.{name}.datetime_validity", violation_ratio, 0.0, "lte"))
        elif column["type"] == "identifier":
            present = [str(value) for value in values if not missing(value)]
            uniqueness = len(set(present)) / len(present) if present else None
            metrics["identifier_uniqueness"][name] = uniqueness
            gates.append(
                gate(
                    f"column.{name}.identifier_uniqueness",
                    uniqueness,
                    acceptance["min_identifier_uniqueness_ratio"],
                    "gte",
                )
            )
    correlation_names, _ = correlation_contract(spec, columns)
    if correlation_names:
        expected = spec["correlations"]["matrix"]
        for left_index, left in enumerate(correlation_names):
            for right_index in range(left_index + 1, len(correlation_names)):
                right = correlation_names[right_index]
                pairs = [
                    (left_value, right_value)
                    for row in rows
                    if (left_value := safe_float(row.get(left))) is not None
                    and (right_value := safe_float(row.get(right))) is not None
                ]
                observed = pearson([pair[0] for pair in pairs], [pair[1] for pair in pairs])
                target = float(expected[left_index][right_index])
                delta = abs(observed - target) if observed is not None else None
                key = f"{left}|{right}"
                metrics["correlations"][key] = {"observed": observed, "expected": target, "delta": delta}
                gates.append(gate(f"correlation.{key}", delta, acceptance["max_correlation_delta"], "lte"))
    passed = all(item["passed"] for item in gates if item["required"])
    return {
        "schema_version": 1,
        "passed": passed,
        "rows": len(rows),
        "schema": {
            "missing_released_columns": missing_columns,
            "unexpected_columns": unexpected_columns,
            "unexpected_dropped_columns": unexpected_dropped,
        },
        "metrics": metrics,
        "acceptance": acceptance,
        "gates": gates,
        "failed_gates": [item["name"] for item in gates if item["required"] and not item["passed"]],
        "caveats": [
            "Constraint fidelity does not establish similarity to any unobserved source population.",
            "Differential-privacy claims require separate bound generation evidence when private columns are used.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate synthetic rows against a schema/statistics specification.")
    parser.add_argument("spec", type=Path)
    parser.add_argument("synthetic", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.spec.is_file():
        raise FileNotFoundError(args.spec)
    if not args.synthetic.is_file():
        raise FileNotFoundError(args.synthetic)
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite: {args.output}")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or spec.get("version") != 1:
        raise ValueError("spec version must be 1")
    report = evaluate(spec, load_rows(args.synthetic))
    report.update(
        {
            "spec": str(args.spec),
            "synthetic": str(args.synthetic),
            "evidence": {
                "spec_sha256": sha256_file(args.spec),
                "synthetic_sha256": sha256_file(args.synthetic),
            },
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "report": str(args.output)}, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

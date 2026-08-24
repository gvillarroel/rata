# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import string
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from materialize_spec import (
    correlation_contract,
    derived_contract,
    derived_value,
    identifier_surrogate_contract,
    joint_distribution_contract,
    normalize_columns,
    numeric_distribution,
    parse_datetime,
    sha256_file,
    text_generator_contract,
)

DEFAULT_ACCEPTANCE = {
    "max_missing_rate_delta": 0.05,
    "max_numeric_mean_relative_error": 0.15,
    "max_numeric_std_relative_error": 0.2,
    "max_numeric_bounds_violation_ratio": 0.0,
    "max_categorical_tv": 0.15,
    "max_correlation_delta": 0.2,
    "max_derived_constraint_violation_ratio": 0.0,
    "max_integer_violation_ratio": 0.0,
    "max_invalid_joint_combination_ratio": 0.0,
    "max_joint_distribution_tv": 0.15,
    "max_numeric_type_violation_ratio": 0.0,
    "max_pattern_violation_ratio": 0.0,
    "max_undeclared_categorical_value_ratio": 0.0,
    "min_identifier_uniqueness_ratio": 1.0,
    "max_identifier_component_tv": 0.15,
    "max_identifier_template_violation_ratio": 0.0,
    "max_text_length_tv": 0.15,
    "max_text_token_tv": 0.15,
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
    if distribution["kind"] in {"normal", "lognormal"}:
        return distribution["mean"], distribution["std"]
    if distribution["kind"] == "uniform":
        width = distribution["max"] - distribution["min"]
        return (distribution["min"] + distribution["max"]) / 2, width / math.sqrt(12)
    return distribution["value"], 0.0


def relative_error(observed: float, expected: float, scale: float) -> float:
    return abs(observed - expected) / max(abs(expected), abs(scale), 1e-9)


def categorical_key(value: Any, boolean: bool) -> str:
    rendered = str(value)
    if not boolean:
        return rendered
    normalized = rendered.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return "true"
    if normalized in {"false", "0", "no"}:
        return "false"
    return normalized


def categorical_target(column: dict[str, Any]) -> dict[str, float]:
    boolean = column["type"] == "boolean"
    if column["type"] == "boolean" and "values" not in column:
        probability_true = float(column.get("probability_true", 0.5))
        return {"false": 1 - probability_true, "true": probability_true}
    raw = column["values"]
    if isinstance(raw, list):
        weighted = [(value, 1.0) for value in raw]
    else:
        weighted = [(value, float(weight)) for value, weight in raw.items()]
    normalized: dict[str, float] = {}
    for value, weight in weighted:
        key = categorical_key(value, boolean)
        normalized[key] = normalized.get(key, 0.0) + weight
    total = sum(normalized.values())
    return {key: weight / total for key, weight in normalized.items()}


def categorical_tv(values: list[Any], expected: dict[str, float], boolean: bool = False) -> float | None:
    observed_values = [categorical_key(value, boolean) for value in values if not missing(value)]
    if not observed_values:
        return None
    counts = Counter(observed_values)
    categories = set(counts) | set(expected)
    return 0.5 * sum(
        abs(counts[category] / len(observed_values) - expected.get(category, 0.0)) for category in categories
    )


def distribution_tv(observed: Counter[Any], expected_weights: dict[Any, float]) -> float | None:
    observed_total = sum(observed.values())
    expected_total = sum(expected_weights.values())
    if observed_total <= 0 or expected_total <= 0:
        return None
    categories = set(observed) | set(expected_weights)
    return 0.5 * sum(
        abs(observed[category] / observed_total - expected_weights.get(category, 0.0) / expected_total)
        for category in categories
    )


def text_distribution_metrics(values: list[Any], column: dict[str, Any]) -> dict[str, float | None]:
    contract = text_generator_contract(column)
    token_counts: Counter[str] = Counter()
    length_counts: Counter[int] = Counter()
    terminal = contract["terminal"]
    for raw in values:
        if missing(raw):
            continue
        rendered = str(raw)
        if terminal and rendered.endswith(terminal):
            rendered = rendered[: -len(terminal)]
        tokens = rendered.split(contract["separator"])
        tokens = [token.casefold() for token in tokens if token]
        if tokens:
            token_counts.update(tokens)
            length_counts[len(tokens)] += 1
    expected_tokens: dict[str, float] = {}
    for token, weight in zip(contract["tokens"], contract["token_weights"], strict=True):
        key = token.casefold()
        expected_tokens[key] = expected_tokens.get(key, 0.0) + weight
    expected_lengths = dict(zip(contract["lengths"], contract["length_weights"], strict=True))
    return {
        "token_tv": distribution_tv(token_counts, expected_tokens),
        "length_tv": distribution_tv(length_counts, expected_lengths),
    }


def identifier_template_metrics(
    rows: list[dict[str, Any]], column: dict[str, Any], columns: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    contract = identifier_surrogate_contract(column, columns)
    component_counts: dict[str, Counter[str]] = {
        name: Counter() for name, component in contract["components"].items() if component["kind"] == "choice"
    }
    allowed_values = {
        name: set(component["values"])
        for name, component in contract["components"].items()
        if component["kind"] == "choice"
    }
    parts: list[str] = []
    for literal, field, _format_spec, _conversion in string.Formatter().parse(contract["template"]):
        parts.append(re.escape(literal))
        if field is None:
            continue
        component = contract["components"].get(field)
        if component is not None and component["kind"] == "integer":
            parts.append(f"(?P<{field}>-?\\d+)")
        elif component is not None:
            alternatives = "|".join(re.escape(value) for value in sorted(component["values"], key=len, reverse=True))
            parts.append(f"(?P<{field}>{alternatives})")
        else:
            parts.append(f"(?P<{field}>.*?)")
    template_pattern = re.compile("".join(parts))
    violations = 0
    for row in rows:
        match = template_pattern.fullmatch(str(row.get(column["name"], "")))
        if match is None:
            violations += 1
            continue
        component_invalid = False
        for reference in contract["references"]:
            if match.group(reference) != str(row.get(reference, "")):
                component_invalid = True
        for name, component in contract["components"].items():
            observed = match.group(name)
            if component["kind"] == "choice":
                if observed not in allowed_values[name]:
                    component_invalid = True
                else:
                    component_counts[name][observed] += 1
            elif not component["min"] <= int(observed) <= component["max"]:
                component_invalid = True
        violations += int(component_invalid)
    component_tv = {}
    for name, counts in component_counts.items():
        component = contract["components"][name]
        expected = dict(zip(component["values"], component["weights"], strict=True))
        component_tv[name] = distribution_tv(counts, expected)
    return {"template_violation_ratio": violations / len(rows), "component_tv": component_tv}


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


def joint_distribution_metrics(rows: list[dict[str, Any]], group: dict[str, Any]) -> dict[str, float | None]:
    expected_weights = {row["key"]: float(row["weight"]) for row in group["rows"]}
    expected_total = sum(expected_weights.values())
    expected = {key: weight / expected_total for key, weight in expected_weights.items()}
    observed = Counter(tuple(str(row.get(name, "")) for name in group["columns"]) for row in rows)
    invalid = sum(count for key, count in observed.items() if key not in expected)
    categories = set(observed) | set(expected)
    tv = 0.5 * sum(abs(observed[key] / len(rows) - expected.get(key, 0.0)) for key in categories)
    return {"tv": tv, "invalid_combination_ratio": invalid / len(rows)}


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
        "derived_constraints": {},
        "datetime": {},
        "identifier_uniqueness": {},
        "integer_violation_ratio": {},
        "identifier_templates": {},
        "joint_distributions": {},
        "numeric_type_violation_ratio": {},
        "pattern_violation_ratio": {},
        "text_distributions": {},
        "undeclared_categorical_value_ratio": {},
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
            present_values = [raw for raw in values if not missing(raw)]
            numeric_values = [value for raw in values if (value := safe_float(raw)) is not None]
            type_violation = (
                (len(present_values) - len(numeric_values)) / len(present_values) if present_values else None
            )
            metrics["numeric_type_violation_ratio"][name] = type_violation
            gates.append(
                gate(
                    f"column.{name}.numeric_type_violation_ratio",
                    type_violation,
                    acceptance["max_numeric_type_violation_ratio"],
                    "lte",
                )
            )
            if column["type"] == "integer":
                integer_violation = (
                    sum(abs(value - round(value)) > 1e-9 for value in numeric_values) / len(numeric_values)
                    if numeric_values
                    else None
                )
                metrics["integer_violation_ratio"][name] = integer_violation
                gates.append(
                    gate(
                        f"column.{name}.integer_violation_ratio",
                        integer_violation,
                        acceptance["max_integer_violation_ratio"],
                        "lte",
                    )
                )
            if column.get("derived") is None:
                distribution = numeric_distribution(column)
                expected_mean, expected_std = target_numeric_moments(distribution)
                observed_mean = fmean(numeric_values) if numeric_values else None
                observed_std = pstdev(numeric_values) if numeric_values else None
                mean_error = (
                    relative_error(observed_mean, expected_mean, expected_std) if observed_mean is not None else None
                )
                std_error = (
                    relative_error(observed_std, expected_std, expected_mean) if observed_std is not None else None
                )
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
        elif column["type"] == "string" and "generator" in column:
            text_metrics = text_distribution_metrics(values, column)
            metrics["text_distributions"][name] = text_metrics
            gates.extend(
                [
                    gate(
                        f"column.{name}.text_token_tv",
                        text_metrics["token_tv"],
                        acceptance["max_text_token_tv"],
                        "lte",
                    ),
                    gate(
                        f"column.{name}.text_length_tv",
                        text_metrics["length_tv"],
                        acceptance["max_text_length_tv"],
                        "lte",
                    ),
                ]
            )
            if column.get("pattern") is not None:
                present = [str(value) for value in values if not missing(value)]
                pattern_violation = (
                    sum(re.fullmatch(column["pattern"], value) is None for value in present) / len(present)
                    if present
                    else None
                )
                metrics["pattern_violation_ratio"][name] = pattern_violation
                gates.append(
                    gate(
                        f"column.{name}.pattern_violation_ratio",
                        pattern_violation,
                        acceptance["max_pattern_violation_ratio"],
                        "lte",
                    )
                )
        elif column["type"] in {"categorical", "boolean", "string"}:
            boolean = column["type"] == "boolean"
            expected_categories = categorical_target(column)
            present_categories = [categorical_key(value, boolean) for value in values if not missing(value)]
            undeclared_ratio = (
                sum(value not in expected_categories for value in present_categories) / len(present_categories)
                if present_categories
                else None
            )
            metrics["undeclared_categorical_value_ratio"][name] = undeclared_ratio
            gates.append(
                gate(
                    f"column.{name}.undeclared_categorical_value_ratio",
                    undeclared_ratio,
                    acceptance["max_undeclared_categorical_value_ratio"],
                    "lte",
                )
            )
            tv = categorical_tv(values, expected_categories, boolean)
            metrics["categorical_tv"][name] = tv
            gates.append(gate(f"column.{name}.categorical_tv", tv, acceptance["max_categorical_tv"], "lte"))
            if column.get("pattern") is not None:
                present = [str(value) for value in values if not missing(value)]
                pattern_violation = (
                    sum(re.fullmatch(column["pattern"], value) is None for value in present) / len(present)
                    if present
                    else None
                )
                metrics["pattern_violation_ratio"][name] = pattern_violation
                gates.append(
                    gate(
                        f"column.{name}.pattern_violation_ratio",
                        pattern_violation,
                        acceptance["max_pattern_violation_ratio"],
                        "lte",
                    )
                )
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
            if column.get("surrogate", {}).get("strategy", "").lower() == "weighted_template":
                template_metrics = identifier_template_metrics(rows, column, configured)
                metrics["identifier_templates"][name] = template_metrics
                gates.append(
                    gate(
                        f"column.{name}.identifier_template_violation_ratio",
                        template_metrics["template_violation_ratio"],
                        acceptance["max_identifier_template_violation_ratio"],
                        "lte",
                    )
                )
                for component, tv in template_metrics["component_tv"].items():
                    gates.append(
                        gate(
                            f"column.{name}.component.{component}.tv",
                            tv,
                            acceptance["max_identifier_component_tv"],
                            "lte",
                        )
                    )
    for column in derived_contract(columns):
        name = column["name"]
        if name not in released or name not in observed_columns:
            continue
        violations = 0
        for row in rows:
            observed = safe_float(row.get(name))
            try:
                expected = float(derived_value(column, row))
            except (KeyError, TypeError, ValueError):
                expected = None
            tolerance = column["derived"]["tolerance"]
            if observed is None or expected is None or abs(observed - expected) > tolerance:
                violations += 1
        violation_ratio = violations / len(rows)
        metrics["derived_constraints"][name] = {
            "kind": column["derived"]["kind"],
            "columns": column["derived"]["columns"],
            "tolerance": column["derived"]["tolerance"],
            "violation_ratio": violation_ratio,
        }
        gates.append(
            gate(
                f"derived.{name}.violation_ratio",
                violation_ratio,
                acceptance["max_derived_constraint_violation_ratio"],
                "lte",
            )
        )
    for group in joint_distribution_contract(spec, columns):
        joint_metrics = joint_distribution_metrics(rows, group)
        metrics["joint_distributions"][group["name"]] = joint_metrics
        gates.extend(
            [
                gate(
                    f"joint.{group['name']}.invalid_combination_ratio",
                    joint_metrics["invalid_combination_ratio"],
                    acceptance["max_invalid_joint_combination_ratio"],
                    "lte",
                ),
                gate(
                    f"joint.{group['name']}.tv",
                    joint_metrics["tv"],
                    acceptance["max_joint_distribution_tv"],
                    "lte",
                ),
            ]
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


def run(args: argparse.Namespace) -> int:
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


def write_failed_constraint_report(args: argparse.Namespace, error: Exception) -> Path | None:
    if args.output.exists() or args.output.resolve() in {args.spec.resolve(), args.synthetic.resolve()}:
        return None
    evidence: dict[str, str] = {}
    for name, path in (("spec", args.spec), ("synthetic", args.synthetic)):
        if path.is_file():
            evidence[f"{name}_sha256"] = sha256_file(path)
    error_message = str(error)
    report = {
        "schema_version": 1,
        "passed": False,
        "status": "constraint-evaluation-failed",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "spec": str(args.spec),
        "synthetic": str(args.synthetic),
        "error": {
            "type": type(error).__name__,
            "message_sha256": hashlib.sha256(error_message.encode("utf-8")).hexdigest(),
            "message_length": len(error_message),
        },
        "evidence": evidence,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return args.output


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except Exception as error:
        try:
            failure_report = write_failed_constraint_report(args, error)
            if failure_report is not None:
                error.add_note(f"Constraint evaluation failure report: {failure_report}")
        except Exception as report_error:
            error.add_note(f"Unable to write constraint evaluation failure report: {report_error}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())

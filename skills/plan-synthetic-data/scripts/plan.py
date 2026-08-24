# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = [
#   "fastavro==1.12.2",
#   "pandas==3.0.3",
#   "pyarrow==25.0.0",
# ]
# ///

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
from fastavro import reader as avro_reader

ROLES = {"public", "protected", "private", "identifier", "drop"}
INPUT_KINDS = {"source", "synthetic-reference", "aggregate-proxy"}
STRING_PRESERVING_ENCODINGS = {"TABULAR_CATEGORICAL", "TABULAR_CHARACTER", "TABULAR_LAT_LONG"}
ENCODINGS = {
    "AUTO",
    "TABULAR_CATEGORICAL",
    "TABULAR_NUMERIC_AUTO",
    "TABULAR_NUMERIC_DISCRETE",
    "TABULAR_NUMERIC_BINNED",
    "TABULAR_NUMERIC_DIGIT",
    "TABULAR_CHARACTER",
    "TABULAR_DATETIME",
    "TABULAR_DATETIME_RELATIVE",
    "TABULAR_LAT_LONG",
}
QUALITY_DEFAULTS = {
    "fast": {"max_epochs": 10, "max_training_minutes": 2.0},
    "balanced": {"max_epochs": 50, "max_training_minutes": 10.0},
    "high": {"max_epochs": 100, "max_training_minutes": 60.0},
}
ACCEPTANCE_DEFAULTS = {
    "max_exact_row_replay_ratio": 0.0,
    "max_identifier_overlap_ratio": 0.0,
    "max_private_rare_value_replay_ratio": 0.0,
    "max_protected_rare_value_replay_ratio": 0.05,
    "max_mean_numeric_ks": 0.2,
    "max_column_numeric_ks": 0.3,
    "max_mean_categorical_tv": 0.2,
    "max_column_categorical_tv": 0.3,
    "max_mean_text_length_ks": 0.2,
    "max_column_text_length_ks": 0.3,
    "max_mean_text_tfidf_distance": 0.35,
    "max_column_text_tfidf_distance": 0.5,
    "max_mean_missing_rate_delta": 0.1,
    "max_column_missing_rate_delta": 0.15,
    "max_mean_abs_correlation_delta": 0.25,
    "max_correlation_delta": 0.4,
    "max_propensity_auc": 0.8,
}
COLUMN_ACCEPTANCE_KEYS = {
    "max_numeric_ks",
    "max_categorical_tv",
    "max_text_length_ks",
    "max_text_tfidf_distance",
    "max_missing_rate_delta",
    "max_rare_value_replay_ratio",
}
IDENTIFIER_PATTERN = re.compile(
    r"(^|_)(id|uuid|guid|email|e_mail|phone|mobile|ssn|sin|passport|ip|ip_address|address|token|"
    r"account_number|card_number|cik|npi|uei|duns|ein|tin|tax_id|loan_number|award_id|case_number|"
    r"dot_number|mc_number|legal_name|borrower_name|recipient_name|provider_name|registered_agent)(_|$)",
    re.IGNORECASE,
)
SENSITIVE_PATTERN = re.compile(
    r"(^|_)(diagnosis|disease|health|medical|salary|income|credit|debt|religion|ethnicity|race|biometric|"
    r"genetic|secret|birthdate|birth_date|date_of_birth|dob|payroll|wage|wages|revenue|receipt|receipts|"
    r"sales|loan|approval_amount|award_amount|balance|delinquency|credit_limit)(_|$)",
    re.IGNORECASE,
)


def load_table(path: Path, string_columns: set[str] | None = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        header = pd.read_csv(path, nrows=0)
        dtype = {column: "string" for column in string_columns or set() if column in header.columns}
        return pd.read_csv(path, dtype=dtype)
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".avro":
        with path.open("rb") as handle:
            return pd.DataFrame.from_records(avro_reader(handle))
    raise ValueError(f"unsupported input format: {suffix or '<none>'}")


def parse_columns(value: str | None) -> set[str]:
    if not value:
        return set()
    return {column.strip() for column in value.split(",") if column.strip()}


def parse_encodings(values: list[str] | None) -> dict[str, str]:
    encodings: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"encoding must use COLUMN=TYPE: {value}")
        column, encoding = (part.strip() for part in value.split("=", 1))
        encoding = encoding.upper()
        if not column or encoding not in ENCODINGS:
            raise ValueError(f"unsupported encoding assignment: {value}")
        if column in encodings:
            raise ValueError(f"duplicate encoding assignment: {column}")
        encodings[column] = encoding
    return encodings


def parse_acceptance(values: list[str] | None) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"acceptance override must use NAME=VALUE: {value}")
        name, raw = (part.strip() for part in value.split("=", 1))
        if name not in ACCEPTANCE_DEFAULTS:
            raise ValueError(f"unsupported acceptance threshold: {name}")
        threshold = float(raw)
        if not 0 <= threshold <= 1:
            raise ValueError(f"acceptance threshold must be between zero and one: {name}")
        overrides[name] = threshold
    return overrides


def parse_column_requirements(values: list[str] | None) -> dict[str, dict[str, float]]:
    requirements: dict[str, dict[str, float]] = {}
    for value in values or []:
        if "=" not in value or "." not in value.split("=", 1)[0]:
            raise ValueError(f"column requirement must use COLUMN.METRIC=VALUE: {value}")
        selector, raw = (part.strip() for part in value.split("=", 1))
        column, metric = (part.strip() for part in selector.rsplit(".", 1))
        if not column or metric not in COLUMN_ACCEPTANCE_KEYS:
            raise ValueError(f"unsupported column requirement: {value}")
        threshold = float(raw)
        if not 0 <= threshold <= 1:
            raise ValueError(f"column threshold must be between zero and one: {selector}")
        if metric in requirements.setdefault(column, {}):
            raise ValueError(f"duplicate column requirement: {selector}")
        requirements[column][metric] = threshold
    return requirements


def column_profile(series: pd.Series) -> dict[str, Any]:
    non_null = series.dropna()
    row_count = len(series)
    nested = bool(non_null.map(lambda value: isinstance(value, (dict, list, tuple, set))).any())
    if nested:
        comparable = non_null.map(
            lambda value: (
                json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list, tuple)) else str(value)
            )
        )
        distinct = int(comparable.nunique())
    else:
        distinct = int(non_null.nunique())
    avg_string_length = None
    if not pd.api.types.is_numeric_dtype(series) and len(non_null):
        avg_string_length = float(non_null.astype(str).str.len().mean())
    return {
        "dtype": str(series.dtype),
        "rows": row_count,
        "non_null": int(len(non_null)),
        "missing_ratio": float(series.isna().mean()) if row_count else 0.0,
        "distinct": distinct,
        "uniqueness_ratio": float(distinct / len(non_null)) if len(non_null) else 0.0,
        "average_string_length": avg_string_length,
        "nested": nested,
    }


def infer_role(name: str, profile: dict[str, Any], inferred_encoding: str | None = None) -> tuple[str, str]:
    if profile.get("nested"):
        return "drop", "nested values must be flattened before tabular synthesis"
    if IDENTIFIER_PATTERN.search(name):
        return "identifier", "identifier-like column name"
    if SENSITIVE_PATTERN.search(name):
        return "private", "sensitive column name"
    if profile["average_string_length"] is not None and profile["average_string_length"] > 80:
        return "drop", "long free-text values are not supported by the tabular engine"
    if inferred_encoding and "DATETIME" in inferred_encoding:
        return "protected", "date/time values require privacy review"
    if profile["uniqueness_ratio"] >= 0.98 and not profile["dtype"].startswith(("int", "float", "bool")):
        return "identifier", "near-unique non-numeric values"
    return "protected", "conservative default"


def infer_encoding(series: pd.Series) -> tuple[str | None, str | None]:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TABULAR_DATETIME", "datetime dtype"
    if pd.api.types.is_object_dtype(series) or isinstance(series.dtype, pd.StringDtype):
        non_blank = series.dropna().astype(str).str.strip()
        non_blank = non_blank[non_blank.ne("")]
        if len(non_blank) >= 20:
            parsed = pd.to_datetime(non_blank, format="mixed", errors="coerce")
            if float(parsed.notna().mean()) >= 0.9:
                return "TABULAR_DATETIME", "at least 90% of string values parse as datetimes"
    return None, None


def default_paths(input_path: Path) -> dict[str, str]:
    stem = input_path.stem
    parent = input_path.parent
    return {
        "output": str(parent / f"{stem}.synthetic{input_path.suffix}"),
        "report": str(parent / f"{stem}.synthetic.report.json"),
        "workspace": str(parent / f"{stem}.synthetic-workspace"),
    }


def validate_artifact_paths(input_path: Path, policy_path: Path, dataset: dict[str, Any]) -> None:
    paths = {
        "input": input_path.resolve(),
        "policy": policy_path.resolve(),
        "output": Path(dataset["output"]).resolve(),
        "report": Path(dataset["report"]).resolve(),
        "workspace": Path(dataset["workspace"]).resolve(),
    }
    collisions: list[str] = []
    names = list(paths)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            if paths[left] == paths[right]:
                collisions.append(f"{left}={right}")
    if collisions:
        raise ValueError(f"artifact paths must be distinct: {', '.join(collisions)}")


def build_policy(
    frame: pd.DataFrame,
    input_path: Path,
    assignments: dict[str, set[str]],
    default_role: str,
    encoding_overrides: dict[str, str] | None = None,
    input_kind: str = "source",
    input_report: Path | None = None,
) -> dict[str, Any]:
    if input_kind not in INPUT_KINDS:
        raise ValueError(f"unsupported input kind: {input_kind}")
    encoding_overrides = encoding_overrides or {}
    unknown = sorted(set().union(*assignments.values()) - set(frame.columns))
    if unknown:
        raise ValueError(f"unknown columns: {', '.join(unknown)}")
    unknown_encodings = sorted(set(encoding_overrides) - set(frame.columns))
    if unknown_encodings:
        raise ValueError(f"unknown encoding columns: {', '.join(unknown_encodings)}")

    owners: dict[str, list[str]] = {}
    for role, columns in assignments.items():
        for column in columns:
            owners.setdefault(column, []).append(role)
    conflicts = {column: roles for column, roles in owners.items() if len(roles) > 1}
    if conflicts:
        rendered = ", ".join(f"{column}={roles}" for column, roles in sorted(conflicts.items()))
        raise ValueError(f"columns assigned to multiple roles: {rendered}")

    columns: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    for name in frame.columns:
        profile = column_profile(frame[name])
        explicit = next((role for role, members in assignments.items() if name in members), None)
        inferred_encoding, encoding_reason = infer_encoding(frame[name])
        inferred_role, reason = infer_role(name, profile, inferred_encoding)
        role = explicit or (inferred_role if inferred_role != "protected" else default_role)
        if profile["nested"] and role != "drop":
            raise ValueError(f"nested column must be flattened or assigned drop: {name}")
        encoding = encoding_overrides.get(name, inferred_encoding)
        entry: dict[str, Any] = {"role": role}
        if role == "identifier":
            entry.update({"strategy": "uuid", "prefix": "syn"})
        if encoding and role not in {"identifier", "drop"}:
            entry["encoding"] = encoding
        columns[name] = entry
        findings.append(
            {
                "column": name,
                **profile,
                "role": role,
                "decision": "explicit" if explicit else "inferred",
                "reason": "explicit user assignment" if explicit else reason,
                "encoding": encoding,
                "encoding_decision": ("explicit" if name in encoding_overrides else "inferred" if encoding else None),
                "encoding_reason": ("explicit user assignment" if name in encoding_overrides else encoding_reason),
            }
        )

    paths = default_paths(input_path)
    inferred_columns = [item["column"] for item in findings if item["decision"] == "inferred"]
    public_columns = [item["column"] for item in findings if item["role"] == "public"]
    warnings = []
    if inferred_columns:
        warnings.append(f"Review inferred roles for: {', '.join(inferred_columns)}.")
    if public_columns:
        warnings.append(f"Public columns may replay exact source values: {', '.join(public_columns)}.")
    else:
        warnings.append("No columns are public; assign public explicitly only when exact replay is acceptable.")
    return {
        "version": 1,
        "dataset": {
            "input": str(input_path),
            "input_kind": input_kind,
            **paths,
            "rows": None,
            "seed": 42,
        },
        "quality": {
            "profile": "balanced",
            "max_epochs": 50,
            "max_training_minutes": 10,
            "sampling_temperature": 1.0,
        },
        "privacy": {
            "default_role": default_role,
            "rare_value_threshold": 5,
            "dp": {
                "enabled": True,
                "max_epsilon": 8.0,
                "delta": 0.00001,
                "noise_multiplier": 1.5,
                "max_grad_norm": 1.0,
                "value_protection_epsilon": 1.0,
            },
            "columns": columns,
        },
        "acceptance": {**ACCEPTANCE_DEFAULTS, "columns": {}},
        "planning": {
            "source_rows": int(len(frame)),
            "source_columns": int(len(frame.columns)),
            "findings": findings,
            "warnings": warnings,
        },
    }


def attach_input_provenance(policy: dict[str, Any], input_report: Path | None) -> None:
    input_kind = str(policy["dataset"].get("input_kind", "source"))
    if input_report is not None:
        if not input_report.is_file():
            raise FileNotFoundError(input_report)
        policy["dataset"]["input_report"] = str(input_report)
    if input_kind == "synthetic-reference":
        policy["planning"]["warnings"].append(
            "The input is already synthetic. Utility can be assessed against this reference, but original-source "
            "privacy and release claims require its original data, policy, and generation/evaluation evidence."
        )
    elif input_kind == "aggregate-proxy":
        policy["planning"]["warnings"].append(
            "The input contains rows materialized from aggregate constraints, not observed records. Evaluate the final "
            "dataset against those constraints and do not present proxy-row comparisons as real-source evidence."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a conservative column-level synthetic-data policy.")
    parser.add_argument("input", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--public")
    parser.add_argument("--protected")
    parser.add_argument("--private")
    parser.add_argument("--identifier")
    parser.add_argument("--drop")
    parser.add_argument("--default-role", choices=("protected", "private"), default="protected")
    parser.add_argument("--quality-profile", choices=tuple(QUALITY_DEFAULTS), default="balanced")
    parser.add_argument("--max-epochs", type=int)
    parser.add_argument("--max-training-minutes", type=float)
    parser.add_argument("--max-epsilon", type=float, default=8.0)
    parser.add_argument("--delta", type=float, default=0.00001)
    parser.add_argument("--noise-multiplier", type=float, default=1.5)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--value-protection-epsilon", type=float, default=1.0)
    parser.add_argument("--rare-value-threshold", type=int, default=5)
    parser.add_argument("--sampling-temperature", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--input-kind", choices=tuple(sorted(INPUT_KINDS)), default="source")
    parser.add_argument(
        "--input-report",
        type=Path,
        help="Optional provenance or generation report for synthetic-reference or aggregate-proxy input.",
    )
    parser.add_argument(
        "--encoding",
        action="append",
        metavar="COLUMN=TYPE",
        help="Override an engine encoding; may be repeated (for example birthdate=TABULAR_DATETIME).",
    )
    parser.add_argument(
        "--acceptance",
        action="append",
        metavar="NAME=VALUE",
        help="Override a global release threshold; may be repeated.",
    )
    parser.add_argument(
        "--column-requirement",
        action="append",
        metavar="COLUMN.METRIC=VALUE",
        help="Add a column-specific release threshold; may be repeated.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.is_file():
        raise FileNotFoundError(args.input)
    if args.policy.exists() and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite: {args.policy}")
    assignments = {role: parse_columns(getattr(args, role)) for role in ROLES}
    encoding_overrides = parse_encodings(args.encoding)
    string_columns = assignments["identifier"] | {
        name for name, encoding in encoding_overrides.items() if encoding in STRING_PRESERVING_ENCODINGS
    }
    frame = load_table(args.input, string_columns)
    if frame.empty:
        raise ValueError("input table has no rows")
    if frame.columns.duplicated().any():
        duplicates = sorted(set(frame.columns[frame.columns.duplicated()]))
        raise ValueError(f"duplicate column names: {', '.join(duplicates)}")
    policy = build_policy(
        frame,
        args.input,
        assignments,
        args.default_role,
        encoding_overrides,
        args.input_kind,
        args.input_report,
    )
    attach_input_provenance(policy, args.input_report)
    quality_defaults = QUALITY_DEFAULTS[args.quality_profile]
    policy["quality"].update(
        {
            "profile": args.quality_profile,
            "max_epochs": args.max_epochs if args.max_epochs is not None else quality_defaults["max_epochs"],
            "max_training_minutes": (
                args.max_training_minutes
                if args.max_training_minutes is not None
                else quality_defaults["max_training_minutes"]
            ),
        }
    )
    if (
        policy["quality"]["max_epochs"] <= 0
        or not math.isfinite(policy["quality"]["max_training_minutes"])
        or policy["quality"]["max_training_minutes"] <= 0
    ):
        raise ValueError("quality limits must be greater than zero")
    if not math.isfinite(args.sampling_temperature) or args.sampling_temperature <= 0:
        raise ValueError("sampling temperature must be greater than zero")
    policy["quality"]["sampling_temperature"] = args.sampling_temperature
    if (
        not math.isfinite(args.max_epsilon)
        or args.max_epsilon <= 0
        or not math.isfinite(args.delta)
        or not 0 < args.delta < 1
        or not math.isfinite(args.noise_multiplier)
        or args.noise_multiplier <= 0
        or not math.isfinite(args.max_grad_norm)
        or args.max_grad_norm <= 0
        or not math.isfinite(args.value_protection_epsilon)
        or args.value_protection_epsilon <= 0
    ):
        raise ValueError(
            "DP epsilon, noise, gradient norm, and value protection must be positive; delta must be in (0, 1)"
        )
    if args.rare_value_threshold < 0:
        raise ValueError("rare value threshold cannot be negative")
    policy["privacy"]["rare_value_threshold"] = args.rare_value_threshold
    policy["privacy"]["dp"].update(
        {
            "max_epsilon": args.max_epsilon,
            "delta": args.delta,
            "noise_multiplier": args.noise_multiplier,
            "max_grad_norm": args.max_grad_norm,
            "value_protection_epsilon": args.value_protection_epsilon,
        }
    )
    acceptance_overrides = parse_acceptance(args.acceptance)
    column_requirements = parse_column_requirements(args.column_requirement)
    unknown_requirement_columns = sorted(set(column_requirements) - set(frame.columns))
    if unknown_requirement_columns:
        raise ValueError(f"unknown column requirement columns: {', '.join(unknown_requirement_columns)}")
    policy["acceptance"].update(acceptance_overrides)
    policy["acceptance"]["columns"] = column_requirements
    if args.rows is not None and args.rows <= 0:
        raise ValueError("row count must be greater than zero")
    for key in ("output", "report", "workspace", "rows", "seed"):
        value = getattr(args, key)
        if value is not None:
            policy["dataset"][key] = str(value) if isinstance(value, Path) else value
    validate_artifact_paths(args.input, args.policy, policy["dataset"])
    args.policy.parent.mkdir(parents=True, exist_ok=True)
    args.policy.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    role_counts = pd.Series([entry["role"] for entry in policy["privacy"]["columns"].values()]).value_counts()
    print(json.dumps({"policy": str(args.policy), "rows": len(frame), "roles": role_counts.to_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

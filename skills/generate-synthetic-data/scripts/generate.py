# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = [
#   "fastavro==1.12.2",
#   "mostlyai-engine==2.6.2",
# ]
# ///

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import string
import time
import uuid
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pandas as pd
from fastavro import parse_schema
from fastavro import reader as avro_reader
from fastavro import writer as avro_writer
from mostlyai.engine import TabularARGN
from mostlyai.engine.domain import DifferentialPrivacyConfig

ROLES = {"public", "protected", "private", "identifier", "drop"}
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
PROFILE_DEFAULTS = {
    "fast": {"max_epochs": 10, "max_training_minutes": 2.0},
    "balanced": {"max_epochs": 50, "max_training_minutes": 10.0},
    "high": {"max_epochs": 100, "max_training_minutes": 60.0},
}
SUPPORTED_TABLE_SUFFIXES = {".csv", ".json", ".jsonl", ".ndjson", ".parquet", ".pq", ".avro"}
INPUT_KINDS = {"source", "synthetic-reference", "aggregate-proxy"}
STRING_PRESERVING_ENCODINGS = {"TABULAR_CATEGORICAL", "TABULAR_CHARACTER", "TABULAR_LAT_LONG"}


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
    raise ValueError(f"unsupported table format: {suffix or '<none>'}")


def string_columns_from_policy(policy: dict[str, Any]) -> set[str]:
    return {
        name
        for name, config in policy["privacy"]["columns"].items()
        if config.get("role") == "identifier" or str(config.get("encoding", "")).upper() in STRING_PRESERVING_ENCODINGS
    }


def json_safe(value: Any) -> Any:
    if value is None or value is pd.NA or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{column: json_safe(value) for column, value in row.items()} for row in frame.to_dict(orient="records")]


def avro_scalar_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "long"
    if pd.api.types.is_float_dtype(series):
        return "double"
    return "string"


def write_table(frame: pd.DataFrame, path: Path) -> None:
    suffix = path.suffix.lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".csv":
        frame.to_csv(path, index=False)
        return
    if suffix == ".json":
        path.write_text(json.dumps(records(frame), indent=2) + "\n", encoding="utf-8")
        return
    if suffix in {".jsonl", ".ndjson"}:
        with path.open("w", encoding="utf-8", newline="") as handle:
            for row in records(frame):
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        return
    if suffix in {".parquet", ".pq"}:
        frame.to_parquet(path, index=False)
        return
    if suffix == ".avro":
        fields = []
        output = frame.copy()
        for column in output.columns:
            avro_type = avro_scalar_type(output[column])
            if avro_type == "string":
                output[column] = output[column].map(lambda value: None if pd.isna(value) else str(value))
            fields.append({"name": column, "type": ["null", avro_type], "default": None})
        schema = parse_schema({"type": "record", "name": "SyntheticRow", "fields": fields})
        with path.open("wb") as handle:
            avro_writer(handle, schema, records(output))
        return
    raise ValueError(f"unsupported output format: {suffix or '<none>'}")


def load_policy(path: Path) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy.get("version") != 1:
        raise ValueError("policy version must be 1")
    dataset = policy.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("policy dataset must be an object")
    missing_dataset = [name for name in ("input", "output", "report", "workspace") if not dataset.get(name)]
    if missing_dataset:
        raise ValueError(f"policy dataset is missing: {', '.join(missing_dataset)}")
    privacy = policy.get("privacy")
    if not isinstance(privacy, dict) or not isinstance(privacy.get("columns"), dict):
        raise ValueError("policy privacy.columns must be an object")
    if not isinstance(privacy.get("dp", {}), dict):
        raise ValueError("policy privacy.dp must be an object")
    invalid_columns = [name for name, config in privacy["columns"].items() if not isinstance(config, dict)]
    if invalid_columns:
        raise ValueError(f"policy column configurations must be objects: {', '.join(invalid_columns)}")
    if not isinstance(policy.get("quality", {}), dict):
        raise ValueError("policy quality must be an object")
    return policy


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generation_policy_fingerprint(policy: dict[str, Any]) -> str:
    canonical = json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def input_provenance(policy: dict[str, Any]) -> dict[str, Any]:
    dataset = policy["dataset"]
    kind = str(dataset.get("input_kind", "source"))
    if kind not in INPUT_KINDS:
        raise ValueError(f"unsupported dataset.input_kind: {kind}")
    provenance: dict[str, Any] = {"kind": kind}
    for field in ("input_report", "aggregate_spec"):
        raw_path = dataset.get(field)
        if raw_path is None:
            continue
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        provenance[field] = str(path)
        provenance[f"{field}_sha256"] = sha256_file(path)
    if kind == "aggregate-proxy" and "aggregate_spec" not in provenance:
        raise ValueError("aggregate-proxy input requires dataset.aggregate_spec")
    return provenance


def validate_policy_parameters(
    policy: dict[str, Any], roles: dict[str, list[str]], source: pd.DataFrame | None = None
) -> None:
    privacy = policy["privacy"]
    rare_threshold = privacy.get("rare_value_threshold", 5)
    if not isinstance(rare_threshold, int) or rare_threshold < 0:
        raise ValueError("privacy.rare_value_threshold must be a non-negative integer")
    dp = privacy.get("dp", {})
    if not isinstance(dp.get("enabled", True), bool):
        raise ValueError("privacy.dp.enabled must be a boolean")
    numeric = {
        "max_epsilon": dp.get("max_epsilon", 8.0),
        "noise_multiplier": dp.get("noise_multiplier", 1.5),
        "max_grad_norm": dp.get("max_grad_norm", 1.0),
        "value_protection_epsilon": dp.get("value_protection_epsilon", 1.0),
    }
    for name, raw in numeric.items():
        value = float(raw)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"privacy.dp.{name} must be finite and greater than zero")
    delta = float(dp.get("delta", 0.00001))
    if not math.isfinite(delta) or not 0 < delta < 1:
        raise ValueError("privacy.dp.delta must be finite and between zero and one")
    for column in roles["identifier"]:
        config = privacy["columns"].get(column, {})
        strategy = str(config.get("strategy", "uuid")).lower()
        if strategy not in {"uuid", "sequential", "weighted_template"}:
            raise ValueError(f"unsupported identifier strategy for {column}: {strategy}")
        if strategy == "weighted_template":
            validate_weighted_template(column, config, roles, source)
    if source is not None:
        for column in roles["public"] + roles["protected"] + roles["private"] + roles["identifier"]:
            has_nested = source[column].dropna().map(lambda value: isinstance(value, (dict, list, tuple, set))).any()
            if has_nested:
                raise ValueError(f"nested column must be flattened or assigned drop: {column}")


def validate_artifact_paths(input_path: Path, output_path: Path, report_path: Path, workspace_root: Path) -> None:
    paths = {
        "input": input_path.resolve(),
        "output": output_path.resolve(),
        "report": report_path.resolve(),
        "workspace": workspace_root.resolve(),
    }
    names = list(paths)
    collisions: list[str] = []
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            if paths[left] == paths[right]:
                collisions.append(f"{left}={right}")
    if collisions:
        raise ValueError(f"artifact paths must be distinct: {', '.join(collisions)}")
    if output_path.suffix.lower() not in SUPPORTED_TABLE_SUFFIXES:
        raise ValueError(f"unsupported output format: {output_path.suffix or '<none>'}")


def resolve_roles(frame: pd.DataFrame, policy: dict[str, Any]) -> dict[str, list[str]]:
    privacy = policy["privacy"]
    default_role = privacy.get("default_role", "protected")
    if default_role not in {"protected", "private"}:
        raise ValueError("privacy.default_role must be protected or private")
    configured = privacy["columns"]
    unknown = sorted(set(configured) - set(frame.columns))
    if unknown:
        raise ValueError(f"policy references unknown columns: {', '.join(unknown)}")
    roles = {role: [] for role in ROLES}
    for column in frame.columns:
        config = configured.get(column, {})
        role = config.get("role", default_role)
        if role not in ROLES:
            raise ValueError(f"invalid role for {column}: {role}")
        roles[role].append(column)
    return roles


def quality_settings(policy: dict[str, Any]) -> dict[str, float | int]:
    quality = policy.get("quality", {})
    profile = quality.get("profile", "balanced")
    if profile not in PROFILE_DEFAULTS:
        raise ValueError(f"unknown quality profile: {profile}")
    defaults = PROFILE_DEFAULTS[profile]
    max_epochs = quality.get("max_epochs", defaults["max_epochs"])
    max_training_minutes = quality.get("max_training_minutes", defaults["max_training_minutes"])
    temperature = quality.get("sampling_temperature", 1.0)
    max_epochs_value = float(max_epochs)
    max_training_value = float(max_training_minutes)
    temperature_value = float(temperature)
    if (
        not math.isfinite(max_epochs_value)
        or not max_epochs_value.is_integer()
        or max_epochs_value <= 0
        or not math.isfinite(max_training_value)
        or max_training_value <= 0
        or not math.isfinite(temperature_value)
        or temperature_value <= 0
    ):
        raise ValueError(
            "quality.max_epochs must be a positive integer; training time and temperature must be finite and positive"
        )
    return {
        "max_epochs": int(max_epochs_value),
        "max_training_minutes": max_training_value,
        "sampling_temperature": temperature_value,
    }


def encoding_types(policy: dict[str, Any], columns: list[str]) -> dict[str, str]:
    selected: dict[str, str] = {}
    configurations = policy["privacy"]["columns"]
    for column in columns:
        encoding = configurations.get(column, {}).get("encoding")
        if encoding is None:
            continue
        encoding = str(encoding).upper()
        if encoding not in ENCODINGS:
            raise ValueError(f"invalid encoding for {column}: {encoding}")
        selected[column] = encoding
    return selected


def sample_model(model: TabularARGN, rows: int, seed_data: pd.DataFrame | None, temperature: float) -> pd.DataFrame:
    if seed_data is not None and len(seed_data.columns):
        if len(seed_data) != rows:
            raise ValueError("seed data row count does not match requested rows")
        return model.sample(seed_data=seed_data, sampling_temperature=temperature)
    return model.sample(n_samples=rows, sampling_temperature=temperature)


def read_dp_checkpoint(workspace: Path) -> dict[str, float] | None:
    progress_path = workspace / "ModelStore" / "model-data" / "progress-messages.csv"
    if not progress_path.is_file():
        return None
    progress = pd.read_csv(progress_path)
    if "dp_eps" not in progress or "dp_delta" not in progress:
        return None
    candidates = progress.dropna(subset=["dp_eps", "dp_delta"])
    if "is_checkpoint" in candidates:
        checkpoints = candidates[candidates["is_checkpoint"] == 1]
        if not checkpoints.empty:
            candidates = checkpoints
    if candidates.empty:
        return None
    row = candidates.iloc[-1]
    return {"epsilon": float(row["dp_eps"]), "delta": float(row["dp_delta"])}


def validate_dp_checkpoint(checkpoint: dict[str, Any] | None, configured: dict[str, Any]) -> dict[str, float]:
    if not checkpoint:
        raise RuntimeError("private stage produced no DP checkpoint evidence")
    try:
        epsilon = float(checkpoint["epsilon"])
        delta = float(checkpoint["delta"])
        max_epsilon = float(configured.get("max_epsilon", 8.0))
        max_delta = float(configured.get("delta", 0.00001))
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("private stage produced malformed DP checkpoint evidence") from error
    if not math.isfinite(epsilon) or not 0 <= epsilon <= max_epsilon:
        raise RuntimeError("private stage checkpoint epsilon is invalid or exceeds the configured ceiling")
    if not math.isfinite(delta) or not 0 <= delta <= max_delta < 1:
        raise RuntimeError("private stage checkpoint delta is invalid or exceeds the configured ceiling")
    return {"epsilon": epsilon, "delta": delta}


def stage_model(
    name: str,
    training_data: pd.DataFrame,
    seed_data: pd.DataFrame | None,
    generated_columns: list[str],
    output: pd.DataFrame,
    workspace: Path,
    settings: dict[str, float | int],
    seed: int,
    dp_config: DifferentialPrivacyConfig | None,
    encoding_types: dict[str, str],
    verbose: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    model = TabularARGN(
        max_training_time=settings["max_training_minutes"],
        max_epochs=settings["max_epochs"],
        value_protection=True,
        differential_privacy=dp_config,
        tgt_encoding_types=encoding_types or None,
        random_state=seed,
        workspace_dir=workspace,
        verbose=verbose,
    )
    try:
        model.fit(training_data)
        trained_seconds = time.perf_counter() - started
        sample_started = time.perf_counter()
        sampled = sample_model(model, len(output), seed_data, float(settings["sampling_temperature"]))
        sampled_seconds = time.perf_counter() - sample_started
    finally:
        model.close()
    missing = sorted(set(generated_columns) - set(sampled.columns))
    if missing:
        raise RuntimeError(f"{name} stage did not generate columns: {', '.join(missing)}")
    for column in generated_columns:
        output[column] = sampled[column].reset_index(drop=True)
    return {
        "stage": name,
        "training_columns": list(training_data.columns),
        "generated_columns": generated_columns,
        "workspace": str(workspace),
        "train_seconds": trained_seconds,
        "sample_seconds": sampled_seconds,
        "dp_checkpoint": read_dp_checkpoint(workspace),
    }


def surrogate_values(rows: int, seed: int, prefix: str, strategy: str) -> list[str]:
    if strategy == "sequential":
        width = max(6, len(str(rows)))
        return [f"{prefix}-{index + 1:0{width}d}" for index in range(rows)]
    if strategy != "uuid":
        raise ValueError(f"unsupported identifier strategy: {strategy}")
    rng = random.Random(seed)
    return [f"{prefix}-{uuid.UUID(int=rng.getrandbits(128), version=4)}" for _ in range(rows)]


def _nested_choices(raw: Any, label: str) -> tuple[list[str], list[float]]:
    if isinstance(raw, list) and raw:
        values = [str(value) for value in raw]
        weights = [1.0] * len(values)
    elif isinstance(raw, dict) and raw:
        values = [str(value) for value in raw]
        weights = [float(value) for value in raw.values()]
    else:
        raise ValueError(f"{label} must be a non-empty array or weighted object")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must not contain duplicates")
    if any(not math.isfinite(weight) or weight < 0 for weight in weights) or sum(weights) <= 0:
        raise ValueError(f"{label} weights must be finite, non-negative, and have a positive total")
    if any(not value or "\n" in value or "\r" in value for value in values):
        raise ValueError(f"{label} values must be non-empty single-line strings")
    return values, weights


def validate_weighted_template(
    column: str,
    config: dict[str, Any],
    roles: dict[str, list[str]],
    source: pd.DataFrame | None,
) -> dict[str, Any]:
    template = config.get("template")
    components = config.get("components")
    if not isinstance(template, str) or not template or "\n" in template or "\r" in template:
        raise ValueError(f"weighted template for {column} must be a non-empty single-line string")
    if not isinstance(components, dict) or not components:
        raise ValueError(f"weighted template for {column} requires components")
    fields: list[str] = []
    for _literal, field, format_spec, conversion in string.Formatter().parse(template):
        if field is None:
            continue
        if not field or format_spec or conversion or field in fields:
            raise ValueError(f"weighted template fields for {column} must be unique simple names")
        fields.append(field)
    if not fields or set(components) - set(fields):
        raise ValueError(f"weighted template for {column} has no fields or unused components")
    normalized: dict[str, dict[str, Any]] = {}
    for name, component in components.items():
        if not isinstance(component, dict):
            raise ValueError(f"weighted template component {column}.{name} must be an object")
        kind = str(component.get("kind", "choice" if "values" in component else "")).lower()
        if kind == "choice":
            values, weights = _nested_choices(component.get("values"), f"{column}.{name}.values")
            normalized[name] = {"kind": kind, "values": values, "weights": weights}
        elif kind == "integer":
            minimum = component.get("min")
            maximum = component.get("max")
            if (
                isinstance(minimum, bool)
                or isinstance(maximum, bool)
                or not isinstance(minimum, int)
                or not isinstance(maximum, int)
                or minimum > maximum
            ):
                raise ValueError(f"weighted template integer component {column}.{name} requires integer min <= max")
            normalized[name] = {"kind": kind, "min": minimum, "max": maximum}
        else:
            raise ValueError(f"unsupported weighted template component kind for {column}.{name}: {kind}")
    references = [field for field in fields if field not in normalized]
    if source is not None:
        missing_references = sorted(set(references) - set(source.columns))
        if missing_references:
            raise ValueError(f"weighted template for {column} references missing columns: {missing_references}")
    forbidden_references = sorted(set(references) & set(roles["identifier"] + roles["drop"]))
    if forbidden_references:
        raise ValueError(f"weighted template for {column} references identifier/drop columns: {forbidden_references}")
    return {
        "template": template,
        "fields": fields,
        "components": normalized,
        "references": references,
    }


def weighted_template_values(
    rows: int,
    seed: int,
    column: str,
    config: dict[str, Any],
    roles: dict[str, list[str]],
    context: pd.DataFrame,
) -> list[str]:
    contract = validate_weighted_template(column, config, roles, context)
    rng = random.Random(seed)
    used: set[str] = set()
    output: list[str] = []
    for index in range(rows):
        references = {name: str(context.iloc[index][name]) for name in contract["references"]}
        for _attempt in range(1000):
            values = dict(references)
            for name, component in contract["components"].items():
                if component["kind"] == "choice":
                    values[name] = rng.choices(component["values"], weights=component["weights"], k=1)[0]
                else:
                    values[name] = str(rng.randint(component["min"], component["max"]))
            candidate = contract["template"].format(**values).strip()
            if candidate and candidate not in used:
                used.add(candidate)
                output.append(candidate)
                break
        else:
            raise RuntimeError(
                f"weighted template for {column} could not produce {rows} unique values; increase its component space"
            )
    return output


def unique_run_workspace(root: Path) -> Path:
    run = root / time.strftime("run-%Y%m%d-%H%M%S")
    if run.exists():
        run = root / f"{run.name}-{uuid.uuid4().hex[:8]}"
    run.mkdir(parents=True, exist_ok=False)
    return run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a policy-driven synthetic tabular dataset.")
    parser.add_argument("policy", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    policy = load_policy(args.policy)
    dataset = policy["dataset"]
    input_path = args.input or Path(dataset["input"])
    output_path = args.output or Path(dataset["output"])
    report_path = args.report or Path(dataset["report"])
    workspace_root = args.workspace or Path(dataset["workspace"])
    seed = args.seed if args.seed is not None else int(dataset.get("seed", 42))
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    validate_artifact_paths(input_path, output_path, report_path, workspace_root)
    input_sha256 = sha256_file(input_path)
    policy_fingerprint = generation_policy_fingerprint(policy)
    provenance = input_provenance(policy)
    if not args.overwrite:
        existing = [path for path in (output_path, report_path) if path.exists()]
        if existing:
            raise FileExistsError(f"refusing to overwrite: {', '.join(map(str, existing))}")

    source = load_table(input_path, string_columns_from_policy(policy))
    if source.empty:
        raise ValueError("input table has no rows")
    if source.columns.duplicated().any():
        raise ValueError("input table contains duplicate column names")
    roles = resolve_roles(source, policy)
    settings = quality_settings(policy)
    validate_policy_parameters(policy, roles, source)
    rows = args.rows if args.rows is not None else dataset.get("rows") or len(source)
    if isinstance(rows, bool) or not isinstance(rows, int) or rows <= 0:
        raise ValueError("row count must be greater than zero")

    dp = policy["privacy"].get("dp", {})
    if roles["private"] and not dp.get("enabled", True):
        raise ValueError("private columns require privacy.dp.enabled=true")
    summary = {
        "input": str(input_path),
        "input_provenance": provenance,
        "output": str(output_path),
        "report": str(report_path),
        "rows": rows,
        "roles": roles,
        "quality": settings,
        "dp_enabled": bool(roles["private"]),
        "dp_configuration": dp if roles["private"] else None,
        "workspace_root": str(workspace_root),
        "planned_stages": [
            stage
            for stage, enabled in (
                ("public-resample", roles["public"]),
                ("protected-model", roles["protected"]),
                ("private-dp-model", roles["private"]),
                ("identifier-surrogates", roles["identifier"]),
                ("drop-projection", roles["drop"]),
            )
            if enabled
        ],
    }
    if args.dry_run:
        print(json.dumps({"dry_run": True, **summary}, indent=2))
        return 0

    run_workspace = unique_run_workspace(workspace_root)
    rng = random.Random(seed)
    public = roles["public"]
    if public:
        indexes = [rng.randrange(len(source)) for _ in range(rows)]
        output = source.iloc[indexes][public].reset_index(drop=True).copy()
    else:
        output = pd.DataFrame(index=range(rows))

    stages: list[dict[str, Any]] = []
    if roles["protected"]:
        protected_training = source[public + roles["protected"]].copy()
        protected_seed = output[public].copy() if public else None
        stages.append(
            stage_model(
                "protected",
                protected_training,
                protected_seed,
                roles["protected"],
                output,
                run_workspace / "protected",
                settings,
                seed,
                None,
                encoding_types(policy, public + roles["protected"]),
                int(args.verbose),
            )
        )

    if roles["private"]:
        condition_columns = public + roles["protected"]
        private_training = source[condition_columns + roles["private"]].copy()
        private_seed = output[condition_columns].copy() if condition_columns else None
        dp_config = DifferentialPrivacyConfig(
            maxEpsilon=float(dp.get("max_epsilon", 8.0)),
            delta=float(dp.get("delta", 0.00001)),
            noiseMultiplier=float(dp.get("noise_multiplier", 1.5)),
            maxGradNorm=float(dp.get("max_grad_norm", 1.0)),
            valueProtectionEpsilon=float(dp.get("value_protection_epsilon", 1.0)),
        )
        stage = stage_model(
            "private",
            private_training,
            private_seed,
            roles["private"],
            output,
            run_workspace / "private",
            settings,
            seed + 1,
            dp_config,
            encoding_types(policy, condition_columns + roles["private"]),
            int(args.verbose),
        )
        stage["dp_checkpoint"] = validate_dp_checkpoint(stage["dp_checkpoint"], dp)
        stages.append(stage)

    for offset, column in enumerate(roles["identifier"]):
        config = policy["privacy"]["columns"].get(column, {})
        strategy = str(config.get("strategy", "uuid")).lower()
        if strategy == "weighted_template":
            output[column] = weighted_template_values(
                rows,
                seed + 1000 + offset,
                column,
                config,
                roles,
                output,
            )
        else:
            output[column] = surrogate_values(
                rows,
                seed + 1000 + offset,
                str(config.get("prefix", "syn")),
                strategy,
            )

    released_columns = [column for column in source.columns if column not in roles["drop"]]
    output = output[released_columns]
    write_table(output, output_path)
    report = {
        "schema_version": 1,
        "method": "staged-column-privacy-tabular-argn",
        "engine": {"package": "mostlyai-engine", "version": version("mostlyai-engine"), "license": "Apache-2.0"},
        "input": str(input_path),
        "input_provenance": provenance,
        "output": str(output_path),
        "rows": rows,
        "seed": seed,
        "roles": roles,
        "quality": settings,
        "dp_configuration": dp if roles["private"] else None,
        "stages": stages,
        "workspace": str(run_workspace),
        "evidence": {
            "policy_fingerprint": policy_fingerprint,
            "input_sha256": input_sha256,
            "output_sha256": sha256_file(output_path),
        },
        "warnings": [
            "Public columns may replay exact source values by policy.",
            "Run the evaluate-synthetic-data skill before release.",
        ]
        + (
            [
                "The input is already synthetic; comparison to it does not establish original-source privacy or "
                "release fitness."
            ]
            if provenance["kind"] == "synthetic-reference"
            else []
        )
        + (
            [
                "The input rows were materialized from aggregate constraints; validate the final output against the "
                "declared constraints rather than treating proxy-row metrics as real-source evidence."
            ]
            if provenance["kind"] == "aggregate-proxy"
            else []
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "workspace": str(run_workspace), "stages": stages}, indent=2))
    return 0


def write_failed_generation_report(args: argparse.Namespace, error: Exception) -> Path | None:
    if args.dry_run:
        return None
    try:
        raw_policy = json.loads(args.policy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw_policy = {}
    dataset = raw_policy.get("dataset", {}) if isinstance(raw_policy, dict) else {}
    raw_report = args.report or (Path(dataset["report"]) if dataset.get("report") else None)
    if raw_report is None or raw_report.exists():
        return None
    raw_input = args.input or (Path(dataset["input"]) if dataset.get("input") else None)
    raw_output = args.output or (Path(dataset["output"]) if dataset.get("output") else None)
    forbidden = {args.policy.resolve()}
    forbidden.update(path.resolve() for path in (raw_input, raw_output) if path is not None)
    if raw_report.resolve() in forbidden:
        return None
    evidence: dict[str, str] = {}
    if args.policy.is_file():
        evidence["policy_sha256"] = sha256_file(args.policy)
    if raw_input is not None and raw_input.is_file():
        evidence["input_sha256"] = sha256_file(raw_input)
    if raw_output is not None and raw_output.is_file():
        evidence["partial_output_sha256"] = sha256_file(raw_output)
    error_message = str(error)
    report = {
        "schema_version": 1,
        "passed": False,
        "status": "generation-failed",
        "method": "staged-column-privacy-tabular-argn",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "policy": str(args.policy),
        "input": str(raw_input) if raw_input is not None else None,
        "output": str(raw_output) if raw_output is not None else None,
        "error": {
            "type": type(error).__name__,
            "message_sha256": hashlib.sha256(error_message.encode("utf-8")).hexdigest(),
            "message_length": len(error_message),
        },
        "evidence": evidence,
    }
    raw_report.parent.mkdir(parents=True, exist_ok=True)
    raw_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return raw_report


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except Exception as error:
        try:
            failure_report = write_failed_generation_report(args, error)
            if failure_report is not None:
                error.add_note(f"Generation failure report: {failure_report}")
        except Exception as report_error:
            error.add_note(f"Unable to write generation failure report: {report_error}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())

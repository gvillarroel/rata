# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = [
#   "fastavro==1.12.2",
#   "numpy==2.5.1",
#   "pandas==3.0.3",
#   "pyarrow==25.0.0",
#   "scikit-learn==1.9.0",
#   "scipy==1.18.0",
# ]
# ///

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastavro import reader as avro_reader
from scipy.stats import ks_2samp
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROLES = {"public", "protected", "private", "identifier", "drop"}
ACCEPTANCE_KEYS = {
    "max_exact_row_replay_ratio",
    "max_identifier_overlap_ratio",
    "max_private_rare_value_replay_ratio",
    "max_protected_rare_value_replay_ratio",
    "max_mean_numeric_ks",
    "max_column_numeric_ks",
    "max_mean_categorical_tv",
    "max_column_categorical_tv",
    "max_mean_text_length_ks",
    "max_column_text_length_ks",
    "max_mean_text_tfidf_distance",
    "max_column_text_tfidf_distance",
    "max_mean_missing_rate_delta",
    "max_column_missing_rate_delta",
    "max_mean_abs_correlation_delta",
    "max_correlation_delta",
    "max_propensity_auc",
}
COLUMN_ACCEPTANCE_KEYS = {
    "max_numeric_ks",
    "max_categorical_tv",
    "max_text_length_ks",
    "max_text_tfidf_distance",
    "max_missing_rate_delta",
    "max_rare_value_replay_ratio",
}


def load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(path: Path) -> dict[str, Any]:
    policy = load_json(path)
    if policy.get("version") != 1:
        raise ValueError("policy version must be 1")
    privacy = policy.get("privacy")
    if not isinstance(privacy, dict) or not isinstance(privacy.get("columns"), dict):
        raise ValueError("policy privacy.columns must be an object")
    invalid_columns = [name for name, config in privacy["columns"].items() if not isinstance(config, dict)]
    if invalid_columns:
        raise ValueError(f"policy column configurations must be objects: {', '.join(invalid_columns)}")
    if not isinstance(policy.get("dataset", {}), dict):
        raise ValueError("policy dataset must be an object")
    return policy


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generation_policy_fingerprint(policy: dict[str, Any]) -> str:
    payload = {
        "version": policy.get("version"),
        "quality": policy.get("quality"),
        "privacy": policy.get("privacy"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generation_report_binding(
    policy: dict[str, Any],
    generation_report: dict[str, Any] | None,
    original_path: Path,
    synthetic_path: Path,
    synthetic_rows: int,
    roles: dict[str, list[str]],
    required: bool,
) -> dict[str, Any]:
    if generation_report is None:
        return {
            "required": required,
            "valid": not required,
            "checks": {},
            "failures": ["generation report is missing"] if required else [],
        }
    evidence = generation_report.get("evidence", {})
    expected_provenance = policy.get("dataset", {})
    observed_provenance = generation_report.get("input_provenance", {})
    checks = {
        "schema_version": generation_report.get("schema_version") == 1,
        "method": generation_report.get("method") == "staged-column-privacy-tabular-argn",
        "engine": generation_report.get("engine", {}).get("package") == "mostlyai-engine",
        "policy_fingerprint": evidence.get("policy_fingerprint") == generation_policy_fingerprint(policy),
        "input_sha256": evidence.get("input_sha256") == sha256_file(original_path),
        "output_sha256": evidence.get("output_sha256") == sha256_file(synthetic_path),
        "row_count": generation_report.get("rows") == synthetic_rows,
        "roles": generation_report.get("roles") == roles,
        "input_kind": observed_provenance.get("kind", "source") == expected_provenance.get("input_kind", "source"),
    }
    for field in ("input_report", "aggregate_spec"):
        raw_path = expected_provenance.get(field)
        if raw_path is None:
            continue
        path = Path(raw_path)
        checks[f"{field}_sha256"] = path.is_file() and observed_provenance.get(f"{field}_sha256") == sha256_file(path)
    failures = [name for name, passed in checks.items() if not passed]
    return {"required": True, "valid": not failures, "checks": checks, "failures": failures}


def resolve_roles(original: pd.DataFrame, policy: dict[str, Any]) -> dict[str, list[str]]:
    privacy = policy["privacy"]
    default_role = privacy.get("default_role", "protected")
    if default_role not in {"protected", "private"}:
        raise ValueError("privacy.default_role must be protected or private")
    configured = privacy["columns"]
    unknown = sorted(set(configured) - set(original.columns))
    if unknown:
        raise ValueError(f"policy references unknown columns: {', '.join(unknown)}")
    roles = {role: [] for role in ROLES}
    for column in original.columns:
        role = configured.get(column, {}).get("role", default_role)
        if role not in ROLES:
            raise ValueError(f"invalid role for {column}: {role}")
        roles[role].append(column)
    return roles


def validate_acceptance(policy: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    acceptance = policy.get("acceptance", {})
    if not isinstance(acceptance, dict):
        raise ValueError("policy acceptance must be an object")
    unknown = sorted(set(acceptance) - ACCEPTANCE_KEYS - {"columns"})
    if unknown:
        raise ValueError(f"unknown acceptance thresholds: {', '.join(unknown)}")
    for name in ACCEPTANCE_KEYS & set(acceptance):
        value = float(acceptance[name])
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"acceptance.{name} must be finite and between zero and one")
    column_requirements = acceptance.get("columns", {})
    if not isinstance(column_requirements, dict):
        raise ValueError("acceptance.columns must be an object")
    unknown_columns = sorted(set(column_requirements) - set(columns))
    if unknown_columns:
        raise ValueError(f"unknown acceptance columns: {', '.join(unknown_columns)}")
    for column, requirements in column_requirements.items():
        if not isinstance(requirements, dict):
            raise ValueError(f"acceptance.columns.{column} must be an object")
        unknown_metrics = sorted(set(requirements) - COLUMN_ACCEPTANCE_KEYS)
        if unknown_metrics:
            raise ValueError(f"unknown requirements for {column}: {', '.join(unknown_metrics)}")
        for metric, raw in requirements.items():
            value = float(raw)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"acceptance.columns.{column}.{metric} must be in [0, 1]")
    return acceptance


def scalar_key(value: Any) -> str:
    if value is None or value is pd.NA or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return "<NA>"
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def row_key(row: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(scalar_key(value) for value in row)


def exact_row_replay(original: pd.DataFrame, synthetic: pd.DataFrame, columns: list[str]) -> float | None:
    if not columns:
        return None
    real = {row_key(row) for row in original[columns].itertuples(index=False, name=None)}
    matches = sum(row_key(row) in real for row in synthetic[columns].itertuples(index=False, name=None))
    return float(matches / max(len(synthetic), 1))


def value_overlap(original: pd.Series, synthetic: pd.Series) -> float:
    real_values = {scalar_key(value) for value in original.dropna()}
    values = [scalar_key(value) for value in synthetic.dropna()]
    return float(sum(value in real_values for value in values) / max(len(values), 1))


def rare_value_replay(
    original: pd.DataFrame, synthetic: pd.DataFrame, columns: list[str], threshold: int
) -> dict[str, Any]:
    per_column: dict[str, float] = {}
    replayed = 0
    considered = 0
    for column in columns:
        counts = original[column].dropna().map(scalar_key).value_counts()
        rare = set(counts[counts <= threshold].index)
        values = synthetic[column].dropna().map(scalar_key)
        matches = int(values.isin(rare).sum())
        per_column[column] = float(matches / max(len(values), 1))
        replayed += matches
        considered += len(values)
    return {
        "ratio": float(replayed / max(considered, 1)),
        "replayed_values": replayed,
        "considered_values": considered,
        "per_column": per_column,
    }


def total_variation(real: pd.Series, synthetic: pd.Series) -> float:
    real_freq = real.map(scalar_key).value_counts(normalize=True)
    synthetic_freq = synthetic.map(scalar_key).value_counts(normalize=True)
    categories = real_freq.index.union(synthetic_freq.index)
    return float(0.5 * sum(abs(real_freq.get(key, 0.0) - synthetic_freq.get(key, 0.0)) for key in categories))


def normalize_datetime_columns(frame: pd.DataFrame, columns: set[str]) -> pd.DataFrame:
    normalized = frame.copy()
    for column in columns & set(normalized.columns):
        parsed = pd.to_datetime(normalized[column], format="mixed", errors="coerce", utc=True)
        values = parsed.dt.as_unit("ns").astype("int64").astype(float) / 1_000_000_000
        normalized[column] = values.where(parsed.notna(), np.nan)
    return normalized


def distribution_metrics(
    original: pd.DataFrame,
    synthetic: pd.DataFrame,
    columns: list[str],
    excluded_categorical: set[str] | None = None,
) -> dict[str, Any]:
    excluded_categorical = excluded_categorical or set()
    numeric: dict[str, float] = {}
    categorical: dict[str, float] = {}
    missing_delta: dict[str, float] = {}
    for column in columns:
        missing_delta[column] = float(abs(original[column].isna().mean() - synthetic[column].isna().mean()))
        if pd.api.types.is_numeric_dtype(original[column]) and pd.api.types.is_numeric_dtype(synthetic[column]):
            real = pd.to_numeric(original[column], errors="coerce").dropna()
            synth = pd.to_numeric(synthetic[column], errors="coerce").dropna()
            if len(real) and len(synth):
                numeric[column] = float(ks_2samp(real, synth, method="asymp").statistic)
        elif column not in excluded_categorical:
            categorical[column] = total_variation(original[column], synthetic[column])
    return {
        "numeric_ks": numeric,
        "mean_numeric_ks": float(np.mean(list(numeric.values()))) if numeric else None,
        "categorical_tv": categorical,
        "mean_categorical_tv": float(np.mean(list(categorical.values()))) if categorical else None,
        "missing_rate_delta": missing_delta,
        "mean_missing_rate_delta": float(np.mean(list(missing_delta.values()))) if missing_delta else None,
    }


def text_metrics(original: pd.DataFrame, synthetic: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    per_column: dict[str, dict[str, Any]] = {}
    for column in columns:
        real = original[column].fillna("").astype(str)
        synth = synthetic[column].fillna("").astype(str)
        length_ks = float(ks_2samp(real.str.len(), synth.str.len(), method="asymp").statistic)
        exact_replay = value_overlap(real, synth)
        combined = [*real.tolist(), *synth.tolist()]
        try:
            vectors = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=5000).fit_transform(combined)
            real_vectors = vectors[: len(real)]
            synth_vectors = vectors[len(real) :]
            real_centroid = np.asarray(real_vectors.mean(axis=0)).ravel()
            synth_centroid = np.asarray(synth_vectors.mean(axis=0)).ravel()
            denominator = float(np.linalg.norm(real_centroid) * np.linalg.norm(synth_centroid))
            centroid_similarity = float(np.dot(real_centroid, synth_centroid) / denominator) if denominator else 1.0
            nearest = synth_vectors @ real_vectors.T
            nearest_similarity = np.asarray(nearest.max(axis=1).toarray()).ravel()
            median_nearest_similarity = float(np.median(nearest_similarity)) if len(nearest_similarity) else None
            max_nearest_similarity = float(np.max(nearest_similarity)) if len(nearest_similarity) else None
        except ValueError:
            centroid_similarity = 1.0
            median_nearest_similarity = None
            max_nearest_similarity = None
        per_column[column] = {
            "length_ks": length_ks,
            "tfidf_centroid_distance": float(1.0 - centroid_similarity),
            "exact_value_replay_ratio": exact_replay,
            "median_nearest_tfidf_similarity": median_nearest_similarity,
            "max_nearest_tfidf_similarity": max_nearest_similarity,
        }
    length_values = [item["length_ks"] for item in per_column.values()]
    tfidf_values = [item["tfidf_centroid_distance"] for item in per_column.values()]
    return {
        "columns": columns,
        "per_column": per_column,
        "mean_length_ks": float(np.mean(length_values)) if length_values else None,
        "max_length_ks": float(np.max(length_values)) if length_values else None,
        "mean_tfidf_centroid_distance": float(np.mean(tfidf_values)) if tfidf_values else None,
        "max_tfidf_centroid_distance": float(np.max(tfidf_values)) if tfidf_values else None,
    }


def correlation_metrics(original: pd.DataFrame, synthetic: pd.DataFrame, columns: list[str]) -> dict[str, Any]:
    numeric = [
        column
        for column in columns
        if pd.api.types.is_numeric_dtype(original[column]) and pd.api.types.is_numeric_dtype(synthetic[column])
    ]
    pairs: dict[str, float] = {}
    for index, left in enumerate(numeric):
        for right in numeric[index + 1 :]:
            real = original[[left, right]].dropna().corr().iloc[0, 1]
            synth = synthetic[[left, right]].dropna().corr().iloc[0, 1]
            if pd.notna(real) and pd.notna(synth):
                pairs[f"{left}/{right}"] = abs(float(real - synth))
    return {
        "pair_deltas": pairs,
        "mean_abs_delta": float(np.mean(list(pairs.values()))) if pairs else None,
        "max_abs_delta": float(np.max(list(pairs.values()))) if pairs else None,
    }


def propensity_auc(original: pd.DataFrame, synthetic: pd.DataFrame, columns: list[str], seed: int) -> float | None:
    if len(original) < 20 or len(synthetic) < 20 or not columns:
        return None
    count = min(len(original), len(synthetic), 5000)
    real = original[columns].sample(n=count, random_state=seed).copy()
    synth = synthetic[columns].sample(n=count, random_state=seed).copy()
    features = pd.concat([real, synth], ignore_index=True)
    labels = np.concatenate([np.zeros(count), np.ones(count)])
    numeric = [column for column in columns if pd.api.types.is_numeric_dtype(features[column])]
    categorical = [column for column in columns if column not in numeric]
    transformers = []
    if numeric:
        transformers.append(
            (
                "numeric",
                Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]),
                numeric,
            )
        )
    if categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("encode", OneHotEncoder(handle_unknown="ignore", min_frequency=2)),
                    ]
                ),
                categorical,
            )
        )
    pipeline = Pipeline(
        [
            ("preprocess", ColumnTransformer(transformers)),
            ("classifier", LogisticRegression(max_iter=500, random_state=seed)),
        ]
    )
    folds = min(5, count)
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    probabilities = cross_val_predict(pipeline, features, labels, cv=splitter, method="predict_proba")[:, 1]
    auc = float(roc_auc_score(labels, probabilities))
    return max(auc, 1.0 - auc)


def nearest_neighbor_metrics(
    original: pd.DataFrame, synthetic: pd.DataFrame, columns: list[str]
) -> dict[str, Any] | None:
    numeric = [
        column
        for column in columns
        if pd.api.types.is_numeric_dtype(original[column]) and pd.api.types.is_numeric_dtype(synthetic[column])
    ]
    if not numeric or len(original) < 2 or not len(synthetic):
        return None
    medians = original[numeric].apply(pd.to_numeric, errors="coerce").median(numeric_only=True)
    real = original[numeric].apply(pd.to_numeric, errors="coerce").fillna(medians).fillna(0.0)
    synth = synthetic[numeric].apply(pd.to_numeric, errors="coerce").fillna(medians).fillna(0.0)
    scaler = StandardScaler().fit(real)
    real_scaled = scaler.transform(real)
    synth_scaled = scaler.transform(synth)
    distances, _ = NearestNeighbors(n_neighbors=2).fit(real_scaled).kneighbors(synth_scaled)
    first = distances[:, 0]
    second = distances[:, 1]
    nndr = np.divide(first, second, out=np.ones_like(first), where=second > 0)
    return {
        "columns": numeric,
        "dcr_median": float(np.median(first)),
        "dcr_p5": float(np.percentile(first, 5)),
        "nndr_median": float(np.median(nndr)),
    }


def dp_evidence(policy: dict[str, Any], generation_report: dict[str, Any] | None, has_private: bool) -> dict[str, Any]:
    if not has_private:
        return {"required": False, "valid": True, "checkpoint": None}
    if not generation_report:
        return {"required": True, "valid": False, "reason": "generation report is missing", "checkpoint": None}
    stage = next((item for item in generation_report.get("stages", []) if item.get("stage") == "private"), None)
    checkpoint = stage.get("dp_checkpoint") if stage else None
    configured = policy["privacy"].get("dp", {})
    valid = bool(
        checkpoint
        and math.isfinite(float(checkpoint.get("epsilon", math.inf)))
        and math.isfinite(float(checkpoint.get("delta", math.inf)))
        and float(checkpoint["epsilon"]) <= float(configured.get("max_epsilon", math.inf))
        and float(checkpoint["delta"]) <= float(configured.get("delta", math.inf))
    )
    return {"required": True, "valid": valid, "checkpoint": checkpoint, "configured": configured}


def gate(
    name: str, value: float | bool | None, threshold: float | bool, comparator: str, required: bool = True
) -> dict[str, Any]:
    if value is None:
        passed = not required
    elif comparator == "lte":
        passed = float(value) <= float(threshold)
    elif comparator == "eq":
        passed = value == threshold
    else:
        raise ValueError(comparator)
    return {
        "name": name,
        "value": value,
        "threshold": threshold,
        "comparator": comparator,
        "required": required,
        "passed": bool(passed),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate synthetic tabular data against a column privacy policy.")
    parser.add_argument("original", type=Path)
    parser.add_argument("synthetic", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--generation-report", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def validate_evaluation_paths(args: argparse.Namespace) -> None:
    inputs = {
        "original": args.original.resolve(),
        "synthetic": args.synthetic.resolve(),
        "policy": args.policy.resolve(),
    }
    if args.generation_report is not None:
        inputs["generation_report"] = args.generation_report.resolve()
    output = args.output.resolve()
    collisions = [name for name, path in inputs.items() if path == output]
    if collisions:
        raise ValueError(f"evaluation output must not overwrite: {', '.join(collisions)}")


def main() -> int:
    args = parse_args()
    validate_evaluation_paths(args)
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite: {args.output}")
    original = load_table(args.original)
    synthetic = load_table(args.synthetic)
    if original.empty or synthetic.empty:
        raise ValueError("original and synthetic tables must contain rows")
    if original.columns.duplicated().any() or synthetic.columns.duplicated().any():
        raise ValueError("original and synthetic tables must have unique column names")
    policy = load_policy(args.policy)
    roles = resolve_roles(original, policy)
    acceptance = validate_acceptance(policy, list(original.columns))
    released = roles["public"] + roles["protected"] + roles["private"] + roles["identifier"]
    modeled = roles["public"] + roles["protected"] + roles["private"]
    configured_text = {
        column
        for column, config in policy["privacy"]["columns"].items()
        if str(config.get("encoding", "")).upper() == "TABULAR_CHARACTER"
    }
    for column, requirements in acceptance.get("columns", {}).items():
        if column not in modeled:
            raise ValueError(f"column acceptance requirements apply only to modeled columns: {column}")
        if "max_rare_value_replay_ratio" in requirements and column not in roles["protected"] + roles["private"]:
            raise ValueError(f"rare-value replay requirements apply only to protected/private columns: {column}")
        if "max_categorical_tv" in requirements and column in configured_text:
            raise ValueError(f"text columns require max_text_tfidf_distance instead of max_categorical_tv: {column}")
        text_requirements = {"max_text_length_ks", "max_text_tfidf_distance"} & set(requirements)
        if text_requirements and column not in configured_text:
            raise ValueError(f"text acceptance requirements require TABULAR_CHARACTER encoding: {column}")
    missing = sorted(set(released) - set(synthetic.columns))
    unexpected = sorted(set(synthetic.columns) - set(released))
    unexpected_drop = sorted(set(roles["drop"]) & set(synthetic.columns))
    available_modeled = [column for column in modeled if column in synthetic.columns]
    available_identifiers = [column for column in roles["identifier"] if column in synthetic.columns]
    available_text = [column for column in available_modeled if column in configured_text]
    available_tabular = [column for column in available_modeled if column not in configured_text]

    original_eval = original[available_modeled].copy()
    synthetic_eval = synthetic[available_modeled].copy()
    datetime_columns = {
        column
        for column, config in policy["privacy"]["columns"].items()
        if "DATETIME" in str(config.get("encoding", ""))
    }
    original_metrics = normalize_datetime_columns(original_eval, datetime_columns)
    synthetic_metrics = normalize_datetime_columns(synthetic_eval, datetime_columns)
    threshold = int(policy["privacy"].get("rare_value_threshold", 5))
    available_protected = [column for column in roles["protected"] if column in available_modeled]
    available_private = [column for column in roles["private"] if column in available_modeled]
    available_public = [column for column in roles["public"] if column in available_modeled]
    protected_replay = rare_value_replay(original_metrics, synthetic_metrics, available_protected, threshold)
    private_replay = rare_value_replay(original_metrics, synthetic_metrics, available_private, threshold)
    identifier_overlap = {
        column: value_overlap(original[column], synthetic[column]) for column in available_identifiers
    }
    identifier_overlap_ratio = max(identifier_overlap.values(), default=0.0)
    distributions = distribution_metrics(
        original_metrics,
        synthetic_metrics,
        available_modeled,
        excluded_categorical=set(available_text),
    )
    text = text_metrics(original_metrics, synthetic_metrics, available_text)
    correlations = correlation_metrics(original_metrics, synthetic_metrics, available_tabular)
    seed = int(policy.get("dataset", {}).get("seed", 42))
    auc = propensity_auc(original_metrics, synthetic_metrics, available_tabular, seed)
    neighbors = nearest_neighbor_metrics(
        original_metrics,
        synthetic_metrics,
        available_protected + available_private,
    )
    generation_path = args.generation_report
    if generation_path is None:
        candidate = Path(policy.get("dataset", {}).get("report", ""))
        generation_path = candidate if candidate.is_file() else None
    generation_report = load_json(generation_path) if generation_path and generation_path.is_file() else None
    binding = generation_report_binding(
        policy,
        generation_report,
        args.original,
        args.synthetic,
        len(synthetic),
        roles,
        required=bool(roles["private"]) or args.generation_report is not None,
    )
    dp = dp_evidence(policy, generation_report, bool(roles["private"]))
    if roles["private"] and not binding["valid"]:
        dp["valid"] = False
        dp["reason"] = "generation report is not bound to this policy/input/output"
    exact_replay = exact_row_replay(original_metrics, synthetic_metrics, available_modeled)
    quality_available = (
        distributions["mean_numeric_ks"] is not None
        or distributions["mean_categorical_tv"] is not None
        or text["mean_length_ks"] is not None
    )

    max_numeric_ks = max(distributions["numeric_ks"].values(), default=None)
    max_categorical_tv = max(distributions["categorical_tv"].values(), default=None)
    max_missing_delta = max(distributions["missing_rate_delta"].values(), default=None)

    gates = [
        gate("released_columns_present", not missing, True, "eq"),
        gate("unexpected_columns_absent", not unexpected, True, "eq"),
        gate("dropped_columns_absent", not unexpected_drop, True, "eq"),
        gate(
            "generation_report_binding",
            binding["valid"],
            True,
            "eq",
            required=binding["required"],
        ),
        gate(
            "exact_modeled_row_replay",
            exact_replay,
            acceptance.get("max_exact_row_replay_ratio", 0.0),
            "lte",
            required=bool(available_modeled),
        ),
        gate(
            "identifier_overlap", identifier_overlap_ratio, acceptance.get("max_identifier_overlap_ratio", 0.0), "lte"
        ),
        gate(
            "protected_rare_value_replay",
            protected_replay["ratio"],
            acceptance.get("max_protected_rare_value_replay_ratio", 0.05),
            "lte",
            required=bool(roles["protected"]),
        ),
        gate(
            "private_rare_value_replay",
            private_replay["ratio"],
            acceptance.get("max_private_rare_value_replay_ratio", 0.0),
            "lte",
            required=bool(roles["private"]),
        ),
        gate("dp_checkpoint_evidence", dp["valid"], True, "eq", required=bool(roles["private"])),
        gate("quality_evidence_available", quality_available, True, "eq", required=bool(modeled)),
        gate(
            "mean_numeric_ks",
            distributions["mean_numeric_ks"],
            acceptance.get("max_mean_numeric_ks", 0.2),
            "lte",
            required=distributions["mean_numeric_ks"] is not None,
        ),
        gate(
            "max_column_numeric_ks",
            max_numeric_ks,
            acceptance.get("max_column_numeric_ks", 0.3),
            "lte",
            required=max_numeric_ks is not None,
        ),
        gate(
            "mean_categorical_tv",
            distributions["mean_categorical_tv"],
            acceptance.get("max_mean_categorical_tv", 0.2),
            "lte",
            required=distributions["mean_categorical_tv"] is not None,
        ),
        gate(
            "max_column_categorical_tv",
            max_categorical_tv,
            acceptance.get("max_column_categorical_tv", 0.3),
            "lte",
            required=max_categorical_tv is not None,
        ),
        gate(
            "mean_text_length_ks",
            text["mean_length_ks"],
            acceptance.get("max_mean_text_length_ks", 0.2),
            "lte",
            required=text["mean_length_ks"] is not None,
        ),
        gate(
            "max_column_text_length_ks",
            text["max_length_ks"],
            acceptance.get("max_column_text_length_ks", 0.3),
            "lte",
            required=text["max_length_ks"] is not None,
        ),
        gate(
            "mean_text_tfidf_distance",
            text["mean_tfidf_centroid_distance"],
            acceptance.get("max_mean_text_tfidf_distance", 0.35),
            "lte",
            required=text["mean_tfidf_centroid_distance"] is not None,
        ),
        gate(
            "max_column_text_tfidf_distance",
            text["max_tfidf_centroid_distance"],
            acceptance.get("max_column_text_tfidf_distance", 0.5),
            "lte",
            required=text["max_tfidf_centroid_distance"] is not None,
        ),
        gate(
            "mean_missing_rate_delta",
            distributions["mean_missing_rate_delta"],
            acceptance.get("max_mean_missing_rate_delta", 0.1),
            "lte",
            required=distributions["mean_missing_rate_delta"] is not None,
        ),
        gate(
            "max_column_missing_rate_delta",
            max_missing_delta,
            acceptance.get("max_column_missing_rate_delta", 0.15),
            "lte",
            required=max_missing_delta is not None,
        ),
        gate(
            "mean_abs_correlation_delta",
            correlations["mean_abs_delta"],
            acceptance.get("max_mean_abs_correlation_delta", 0.25),
            "lte",
            required=correlations["mean_abs_delta"] is not None,
        ),
        gate(
            "max_correlation_delta",
            correlations["max_abs_delta"],
            acceptance.get("max_correlation_delta", 0.4),
            "lte",
            required=correlations["max_abs_delta"] is not None,
        ),
        gate(
            "propensity_auc",
            auc,
            acceptance.get("max_propensity_auc", 0.8),
            "lte",
            required=len(original) >= 20 and bool(modeled),
        ),
    ]
    for column, requirements in acceptance.get("columns", {}).items():
        values = {
            "max_numeric_ks": distributions["numeric_ks"].get(column),
            "max_categorical_tv": distributions["categorical_tv"].get(column),
            "max_text_length_ks": text["per_column"].get(column, {}).get("length_ks"),
            "max_text_tfidf_distance": text["per_column"].get(column, {}).get("tfidf_centroid_distance"),
            "max_missing_rate_delta": distributions["missing_rate_delta"].get(column),
            "max_rare_value_replay_ratio": (
                protected_replay["per_column"].get(column)
                if column in roles["protected"]
                else private_replay["per_column"].get(column)
            ),
        }
        for metric, threshold_value in requirements.items():
            gates.append(
                gate(
                    f"column.{column}.{metric}",
                    values[metric],
                    threshold_value,
                    "lte",
                    required=True,
                )
            )
    passed = all(item["passed"] for item in gates if item["required"])
    input_kind = str(policy.get("dataset", {}).get("input_kind", "source"))
    provenance_caveats = []
    if input_kind == "synthetic-reference":
        provenance_caveats.append(
            "Utility metrics compare against an already synthetic reference and do not establish original-source "
            "privacy or release fitness."
        )
    elif input_kind == "aggregate-proxy":
        provenance_caveats.append(
            "Utility metrics compare against materialized proxy rows; acceptance also requires separate validation "
            "against the declared aggregate constraints."
        )
    report = {
        "schema_version": 1,
        "passed": passed,
        "original": str(args.original),
        "synthetic": str(args.synthetic),
        "rows": {"original": len(original), "synthetic": len(synthetic)},
        "roles": roles,
        "input_provenance": {"kind": input_kind},
        "schema": {
            "missing_released_columns": missing,
            "unexpected_columns": unexpected,
            "unexpected_dropped_columns": unexpected_drop,
        },
        "generation_report_binding": binding,
        "quality": {
            "distributions": distributions,
            "text": text,
            "correlations": correlations,
            "propensity_auc": auc,
        },
        "privacy": {
            "exact_modeled_row_replay_ratio": exact_replay,
            "public_value_overlap": {
                column: value_overlap(original_metrics[column], synthetic_metrics[column])
                for column in available_public
            },
            "protected_rare_value_replay": protected_replay,
            "private_rare_value_replay": private_replay,
            "identifier_overlap": identifier_overlap,
            "nearest_neighbors": neighbors,
            "differential_privacy": dp,
        },
        "gates": gates,
        "failed_gates": [item["name"] for item in gates if item["required"] and not item["passed"]],
        "caveats": [
            "DCR and NNDR are proxy diagnostics, not formal privacy guarantees.",
            "TF-IDF text metrics measure lexical similarity, not semantic correctness or downstream utility.",
            "Public-column replay is allowed only because the policy explicitly declares those columns public.",
        ]
        + provenance_caveats,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "report": str(args.output), "failed_gates": report["failed_gates"]}, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

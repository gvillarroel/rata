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
import random
import re
import string
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import NormalDist
from typing import Any

ROLES = {"public", "protected", "private", "identifier", "drop"}
TYPES = {"number", "integer", "categorical", "boolean", "string", "datetime", "identifier"}
OUTPUT_SUFFIXES = {".csv", ".json", ".jsonl", ".ndjson"}
PROFILE_DEFAULTS = {
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def probability(value: Any, label: str) -> float:
    result = finite_number(value, label)
    if not 0 <= result <= 1:
        raise ValueError(f"{label} must be between zero and one")
    return result


def quality_contract(spec: dict[str, Any]) -> dict[str, Any]:
    raw = spec.get("quality", {})
    if not isinstance(raw, dict):
        raise ValueError("quality must be an object")
    profile = str(raw.get("profile", "balanced"))
    if profile not in PROFILE_DEFAULTS:
        raise ValueError(f"unsupported quality profile: {profile}")
    defaults = PROFILE_DEFAULTS[profile]
    max_epochs = finite_number(raw.get("max_epochs", defaults["max_epochs"]), "quality.max_epochs")
    max_training_minutes = finite_number(
        raw.get("max_training_minutes", defaults["max_training_minutes"]),
        "quality.max_training_minutes",
    )
    sampling_temperature = finite_number(raw.get("sampling_temperature", 1.0), "quality.sampling_temperature")
    if not max_epochs.is_integer() or max_epochs <= 0:
        raise ValueError("quality.max_epochs must be a positive integer")
    if max_training_minutes <= 0 or sampling_temperature <= 0:
        raise ValueError("quality training time and sampling temperature must be positive")
    return {
        "profile": profile,
        "max_epochs": int(max_epochs),
        "max_training_minutes": max_training_minutes,
        "sampling_temperature": sampling_temperature,
    }


def dp_contract(spec: dict[str, Any]) -> dict[str, Any]:
    privacy = spec.get("privacy", {})
    if not isinstance(privacy, dict):
        raise ValueError("privacy must be an object")
    raw = privacy.get("dp", {})
    if not isinstance(raw, dict):
        raise ValueError("privacy.dp must be an object")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("privacy.dp.enabled must be a boolean")
    contract = {
        "enabled": enabled,
        "max_epsilon": finite_number(raw.get("max_epsilon", 8.0), "privacy.dp.max_epsilon"),
        "delta": probability(raw.get("delta", 0.00001), "privacy.dp.delta"),
        "noise_multiplier": finite_number(raw.get("noise_multiplier", 1.5), "privacy.dp.noise_multiplier"),
        "max_grad_norm": finite_number(raw.get("max_grad_norm", 1.0), "privacy.dp.max_grad_norm"),
        "value_protection_epsilon": finite_number(
            raw.get("value_protection_epsilon", 1.0), "privacy.dp.value_protection_epsilon"
        ),
    }
    if contract["delta"] in {0.0, 1.0}:
        raise ValueError("privacy.dp.delta must be strictly between zero and one")
    for name in ("max_epsilon", "noise_multiplier", "max_grad_norm", "value_protection_epsilon"):
        if contract[name] <= 0:
            raise ValueError(f"privacy.dp.{name} must be positive")
    return contract


def normalize_columns(spec: dict[str, Any]) -> list[dict[str, Any]]:
    raw_columns = spec.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        raise ValueError("spec columns must be a non-empty array")
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_columns):
        if not isinstance(raw, dict):
            raise ValueError(f"columns[{index}] must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"columns[{index}].name must be a non-empty string")
        name = name.strip()
        if name in seen:
            raise ValueError(f"duplicate column name: {name}")
        seen.add(name)
        column_type = str(raw.get("type", "")).lower()
        if column_type not in TYPES:
            raise ValueError(f"unsupported type for {name}: {column_type or '<missing>'}")
        explicit_role = "role" in raw
        role = str(raw.get("role", "identifier" if column_type == "identifier" else "protected")).lower()
        if role not in ROLES:
            raise ValueError(f"unsupported role for {name}: {role}")
        if role == "public" and not explicit_role:
            raise ValueError(f"public role must be explicit: {name}")
        missing_rate = probability(raw.get("missing_rate", 0.0), f"{name}.missing_rate")
        if role == "identifier" and missing_rate:
            raise ValueError(f"identifier column cannot have missing values: {name}")
        pattern = raw.get("pattern")
        if pattern is not None:
            if column_type not in {"categorical", "string"} or not isinstance(pattern, str) or not pattern:
                raise ValueError(f"{name}.pattern is supported only for categorical or string columns")
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"{name}.pattern must be a valid regular expression") from error
        derived = raw.get("derived")
        if derived is not None:
            if column_type not in {"number", "integer"} or not isinstance(derived, dict):
                raise ValueError(f"{name}.derived is supported only for numeric columns")
            if "distribution" in raw:
                raise ValueError(f"{name} cannot declare both distribution and derived")
            if missing_rate:
                raise ValueError(f"derived column cannot have missing values: {name}")
        columns.append(
            {
                **raw,
                "name": name,
                "type": column_type,
                "role": role,
                "role_explicit": explicit_role,
                "missing_rate": missing_rate,
            }
        )
    by_name = {column["name"]: column for column in columns}
    for column in columns:
        if "generator" in column:
            text_generator_contract(column)
        if "surrogate" in column:
            identifier_surrogate_contract(column, by_name)
    return columns


def nested_weighted_values(raw: Any, label: str) -> tuple[list[str], list[float]]:
    if isinstance(raw, list) and raw:
        values = [str(value) for value in raw]
        if len(set(values)) != len(values):
            raise ValueError(f"{label} must not contain duplicates")
        return values, [1.0] * len(values)
    if isinstance(raw, dict) and raw:
        values = [str(value) for value in raw]
        weights = [finite_number(weight, f"{label}[{value}]") for value, weight in raw.items()]
        if any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ValueError(f"{label} weights must be non-negative with a positive total")
        return values, weights
    raise ValueError(f"{label} must be a non-empty array or weighted object")


def text_generator_contract(column: dict[str, Any]) -> dict[str, Any]:
    name = column["name"]
    raw = column.get("generator")
    if column["type"] != "string" or not isinstance(raw, dict):
        raise ValueError(f"{name}.generator is supported only for string columns")
    kind = str(raw.get("kind", "")).lower()
    if kind != "token_sequence":
        raise ValueError(f"unsupported string generator for {name}: {kind or '<missing>'}")
    tokens, token_weights = nested_weighted_values(raw.get("tokens"), f"{name}.generator.tokens")
    if any(not token.strip() or any(character.isspace() for character in token) for token in tokens):
        raise ValueError(f"{name}.generator.tokens must be non-empty single tokens")
    lengths, length_weights = nested_weighted_values(raw.get("lengths"), f"{name}.generator.lengths")
    try:
        numeric_lengths = [int(value) for value in lengths]
    except ValueError as error:
        raise ValueError(f"{name}.generator.lengths must contain integers") from error
    if any(
        length < 1 or length > 1000 or str(length) != raw_value
        for length, raw_value in zip(numeric_lengths, lengths, strict=True)
    ):
        raise ValueError(f"{name}.generator.lengths must contain canonical integers from 1 to 1000")
    separator = raw.get("separator", " ")
    terminal = raw.get("terminal", ".")
    capitalize = raw.get("capitalize", True)
    if not isinstance(separator, str) or not separator or len(separator) > 3 or "\n" in separator:
        raise ValueError(f"{name}.generator.separator must be one to three non-newline characters")
    if not isinstance(terminal, str) or len(terminal) > 3 or "\n" in terminal:
        raise ValueError(f"{name}.generator.terminal must be at most three non-newline characters")
    if not isinstance(capitalize, bool):
        raise ValueError(f"{name}.generator.capitalize must be a boolean")
    return {
        "kind": kind,
        "tokens": tokens,
        "token_weights": token_weights,
        "lengths": numeric_lengths,
        "length_weights": length_weights,
        "separator": separator,
        "terminal": terminal,
        "capitalize": capitalize,
    }


def identifier_surrogate_contract(
    column: dict[str, Any], columns: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    name = column["name"]
    raw = column.get("surrogate", {})
    if column["role"] != "identifier" or column["type"] != "identifier" or not isinstance(raw, dict):
        raise ValueError(f"{name}.surrogate requires an identifier column with role identifier")
    strategy = str(raw.get("strategy", "uuid")).lower()
    if strategy in {"uuid", "sequential"}:
        return {"strategy": strategy, "prefix": str(raw.get("prefix", column.get("prefix", "syn")))}
    if strategy != "weighted_template":
        raise ValueError(f"unsupported identifier surrogate strategy for {name}: {strategy}")
    template = raw.get("template")
    components = raw.get("components")
    if not isinstance(template, str) or not template or not isinstance(components, dict) or not components:
        raise ValueError(f"{name}.surrogate weighted_template requires template and components")
    fields: list[str] = []
    for _literal, field, format_spec, conversion in string.Formatter().parse(template):
        if field is None:
            continue
        if not field or format_spec or conversion or field in fields:
            raise ValueError(f"{name}.surrogate template fields must be unique simple names")
        fields.append(field)
    if not fields:
        raise ValueError(f"{name}.surrogate template must contain fields")
    unused_components = set(components) - set(fields)
    if unused_components:
        raise ValueError(f"{name}.surrogate has unused components: {sorted(unused_components)}")
    normalized_components: dict[str, dict[str, Any]] = {}
    for component_name, component in components.items():
        if not isinstance(component, dict):
            raise ValueError(f"{name}.surrogate.components.{component_name} must be an object")
        kind = str(component.get("kind", "choice" if "values" in component else "")).lower()
        if kind == "choice":
            values, weights = nested_weighted_values(
                component.get("values"), f"{name}.surrogate.components.{component_name}.values"
            )
            normalized_components[component_name] = {"kind": kind, "values": values, "weights": weights}
        elif kind == "integer":
            minimum = finite_number(component.get("min"), f"{name}.surrogate.components.{component_name}.min")
            maximum = finite_number(component.get("max"), f"{name}.surrogate.components.{component_name}.max")
            if not minimum.is_integer() or not maximum.is_integer() or minimum > maximum:
                raise ValueError(f"{name}.surrogate integer component requires integral min <= max")
            normalized_components[component_name] = {"kind": kind, "min": int(minimum), "max": int(maximum)}
        else:
            raise ValueError(f"unsupported component kind for {name}.{component_name}: {kind or '<missing>'}")
    references = [field for field in fields if field not in normalized_components]
    if columns is not None:
        for reference in references:
            target = columns.get(reference)
            if target is None:
                raise ValueError(f"{name}.surrogate references unknown column: {reference}")
            if target["role"] in {"identifier", "drop"}:
                raise ValueError(f"{name}.surrogate cannot reference {target['role']} column: {reference}")
    return {
        "strategy": strategy,
        "template": template,
        "fields": fields,
        "components": normalized_components,
        "references": references,
    }


def numeric_distribution(column: dict[str, Any]) -> dict[str, Any]:
    name = column["name"]
    distribution = column.get("distribution")
    if not isinstance(distribution, dict):
        raise ValueError(f"{name}.distribution must be an object")
    kind = str(distribution.get("kind", "")).lower()
    if kind == "normal":
        mean = finite_number(distribution.get("mean"), f"{name}.distribution.mean")
        std = finite_number(distribution.get("std"), f"{name}.distribution.std")
        if std <= 0:
            raise ValueError(f"{name}.distribution.std must be greater than zero")
        minimum = distribution.get("min")
        maximum = distribution.get("max")
        minimum = finite_number(minimum, f"{name}.distribution.min") if minimum is not None else None
        maximum = finite_number(maximum, f"{name}.distribution.max") if maximum is not None else None
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"{name}.distribution.min must not exceed max")
        return {"kind": kind, "mean": mean, "std": std, "min": minimum, "max": maximum}
    if kind == "uniform":
        minimum = finite_number(distribution.get("min"), f"{name}.distribution.min")
        maximum = finite_number(distribution.get("max"), f"{name}.distribution.max")
        if minimum >= maximum:
            raise ValueError(f"{name}.distribution.min must be less than max")
        return {"kind": kind, "min": minimum, "max": maximum}
    if kind == "constant":
        return {"kind": kind, "value": finite_number(distribution.get("value"), f"{name}.distribution.value")}
    if kind == "lognormal":
        mean = finite_number(distribution.get("mean"), f"{name}.distribution.mean")
        std = finite_number(distribution.get("std"), f"{name}.distribution.std")
        if mean <= 0 or std <= 0:
            raise ValueError(f"{name}.distribution lognormal mean and std must be positive")
        minimum = finite_number(distribution.get("min", 0.0), f"{name}.distribution.min")
        maximum_raw = distribution.get("max")
        maximum = finite_number(maximum_raw, f"{name}.distribution.max") if maximum_raw is not None else None
        if minimum < 0 or (maximum is not None and minimum >= maximum):
            raise ValueError(f"{name}.distribution lognormal bounds must satisfy 0 <= min < max")
        variance_ratio = (std / mean) ** 2
        normal_variance = math.log1p(variance_ratio)
        return {
            "kind": kind,
            "mean": mean,
            "std": std,
            "min": minimum,
            "max": maximum,
            "normal_mean": math.log(mean) - normal_variance / 2,
            "normal_std": math.sqrt(normal_variance),
        }
    raise ValueError(f"unsupported numeric distribution for {name}: {kind or '<missing>'}")


def weighted_values(column: dict[str, Any]) -> tuple[list[Any], list[float]]:
    name = column["name"]
    if column["type"] == "boolean" and "values" not in column:
        probability_true = probability(column.get("probability_true", 0.5), f"{name}.probability_true")
        return [False, True], [1 - probability_true, probability_true]
    raw = column.get("values")
    if isinstance(raw, list) and raw:
        if len({str(value) for value in raw}) != len(raw):
            raise ValueError(f"{name}.values must not contain duplicates")
        _validate_pattern_values(column, raw)
        return list(raw), [1.0] * len(raw)
    if isinstance(raw, dict) and raw:
        values = list(raw)
        weights = [finite_number(weight, f"{name}.values[{value}]") for value, weight in raw.items()]
        if any(weight < 0 for weight in weights) or sum(weights) <= 0:
            raise ValueError(f"{name}.values weights must be non-negative with a positive total")
        _validate_pattern_values(column, values)
        return values, weights
    raise ValueError(f"{name}.values must be a non-empty array or weighted object")


def _validate_pattern_values(column: dict[str, Any], values: list[Any]) -> None:
    pattern = column.get("pattern")
    if pattern is None:
        return
    invalid = [value for value in values if re.fullmatch(pattern, str(value)) is None]
    if invalid:
        raise ValueError(f"{column['name']}.values do not satisfy pattern: {invalid[:3]}")


def joint_distribution_contract(spec: dict[str, Any], columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_groups = spec.get("joint_distributions", [])
    if not isinstance(raw_groups, list):
        raise ValueError("joint_distributions must be an array")
    by_name = {column["name"]: column for column in columns}
    occupied: set[str] = set()
    group_names: set[str] = set()
    groups: list[dict[str, Any]] = []
    for group_index, raw_group in enumerate(raw_groups):
        if not isinstance(raw_group, dict):
            raise ValueError(f"joint_distributions[{group_index}] must be an object")
        group_name = str(raw_group.get("name", f"joint_{group_index + 1}")).strip()
        if not group_name or group_name in group_names:
            raise ValueError(f"joint distribution names must be non-empty and unique: {group_name or '<empty>'}")
        group_names.add(group_name)
        names = raw_group.get("columns")
        if not isinstance(names, list) or len(names) < 2 or len(set(names)) != len(names):
            raise ValueError(f"joint_distributions[{group_index}].columns must contain at least two unique names")
        for name in names:
            column = by_name.get(name)
            if column is None or column["type"] not in {"categorical", "boolean", "string"}:
                raise ValueError(f"joint distribution column must be categorical, boolean, or string: {name}")
            if column["role"] == "drop":
                raise ValueError(f"joint distribution column cannot be dropped: {name}")
            if column["missing_rate"]:
                raise ValueError(f"joint distribution column cannot have missing values: {name}")
            if name in occupied:
                raise ValueError(f"joint distribution columns cannot overlap: {name}")
        raw_rows = raw_group.get("rows")
        if not isinstance(raw_rows, list) or not raw_rows:
            raise ValueError(f"joint_distributions[{group_index}].rows must be a non-empty array")
        allowed = {name: {str(value) for value in weighted_values(by_name[name])[0]} for name in names}
        normalized_rows: list[dict[str, Any]] = []
        combinations: set[tuple[str, ...]] = set()
        for row_index, raw_row in enumerate(raw_rows):
            if not isinstance(raw_row, dict) or not isinstance(raw_row.get("values"), dict):
                raise ValueError(f"joint_distributions[{group_index}].rows[{row_index}].values must be an object")
            values = raw_row["values"]
            if set(values) != set(names):
                raise ValueError(f"joint_distributions[{group_index}].rows[{row_index}] must define every group column")
            combination = tuple(str(values[name]) for name in names)
            if combination in combinations:
                raise ValueError(f"duplicate joint distribution combination: {combination}")
            combinations.add(combination)
            for name, value in zip(names, combination, strict=True):
                if value not in allowed[name]:
                    raise ValueError(f"joint distribution value is not declared by {name}.values: {value}")
            weight = finite_number(raw_row.get("weight", 1.0), f"joint_distributions[{group_index}].weight")
            if weight < 0:
                raise ValueError("joint distribution weights must be non-negative")
            normalized_rows.append({"values": dict(values), "weight": weight, "key": combination})
        if sum(row["weight"] for row in normalized_rows) <= 0:
            raise ValueError("joint distribution weights must have a positive total")
        occupied.update(str(name) for name in names)
        groups.append(
            {
                "name": group_name,
                "columns": [str(name) for name in names],
                "rows": normalized_rows,
            }
        )
    return groups


def derived_contract(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {column["name"]: column for column in columns}
    derived = {column["name"]: column for column in columns if column.get("derived") is not None}
    for name, column in derived.items():
        contract = column["derived"]
        kind = str(contract.get("kind", "")).lower()
        dependencies = contract.get("columns")
        if kind not in {"sum", "difference", "product"}:
            raise ValueError(f"unsupported derived kind for {name}: {kind or '<missing>'}")
        minimum_columns = 1 if kind == "sum" else 2
        if (
            not isinstance(dependencies, list)
            or len(dependencies) < minimum_columns
            or len(set(dependencies)) != len(dependencies)
        ):
            raise ValueError(f"{name}.derived.columns are invalid for {kind}")
        if kind == "difference" and len(dependencies) != 2:
            raise ValueError(f"{name}.derived difference requires exactly two columns")
        for dependency in dependencies:
            source = by_name.get(dependency)
            if source is None or source["type"] not in {"number", "integer"}:
                raise ValueError(f"derived dependency must be numeric: {name} <- {dependency}")
            if source["missing_rate"]:
                raise ValueError(f"derived dependency cannot have missing values: {name} <- {dependency}")
            if column["role"] != "drop" and source["role"] == "drop":
                raise ValueError(f"released derived column cannot depend on dropped column: {name} <- {dependency}")
            if dependency == name:
                raise ValueError(f"derived column cannot depend on itself: {name}")
        tolerance = finite_number(contract.get("tolerance", 0.0), f"{name}.derived.tolerance")
        if tolerance < 0:
            raise ValueError(f"{name}.derived.tolerance must be non-negative")
        column["derived"] = {"kind": kind, "columns": [str(value) for value in dependencies], "tolerance": tolerance}

    order: list[dict[str, Any]] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise ValueError("derived columns must not contain a dependency cycle")
        visiting.add(name)
        for dependency in derived[name]["derived"]["columns"]:
            if dependency in derived:
                visit(dependency)
        visiting.remove(name)
        visited.add(name)
        order.append(derived[name])

    for name in derived:
        visit(name)
    return order


def derived_value(column: dict[str, Any], row: dict[str, Any]) -> int | float:
    contract = column["derived"]
    values = [float(row[name]) for name in contract["columns"]]
    if contract["kind"] == "sum":
        value = sum(values)
    elif contract["kind"] == "difference":
        value = values[0] - values[1]
    else:
        value = math.prod(values)
    return int(round(value)) if column["type"] == "integer" else round(value, 8)


def parse_datetime(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO-8601 string") from error


def cholesky(matrix: list[list[float]]) -> list[list[float]]:
    size = len(matrix)
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            subtotal = sum(lower[row][offset] * lower[column][offset] for offset in range(column))
            if row == column:
                diagonal = matrix[row][row] - subtotal
                if diagonal <= 1e-10:
                    raise ValueError("correlation matrix must be positive definite")
                lower[row][column] = math.sqrt(diagonal)
            else:
                lower[row][column] = (matrix[row][column] - subtotal) / lower[column][column]
    return lower


def correlation_contract(spec: dict[str, Any], columns: list[dict[str, Any]]) -> tuple[list[str], list[list[float]]]:
    raw = spec.get("correlations")
    if raw is None:
        return [], []
    if not isinstance(raw, dict):
        raise ValueError("correlations must be an object")
    names = raw.get("columns")
    matrix = raw.get("matrix")
    if not isinstance(names, list) or len(names) < 2 or len(set(names)) != len(names):
        raise ValueError("correlations.columns must contain at least two unique column names")
    by_name = {column["name"]: column for column in columns}
    for name in names:
        if name not in by_name or by_name[name]["type"] not in {"number", "integer"}:
            raise ValueError(f"correlation column must be numeric: {name}")
        if by_name[name].get("derived") is not None:
            raise ValueError(f"correlation column cannot be derived: {name}")
    if not isinstance(matrix, list) or len(matrix) != len(names):
        raise ValueError("correlations.matrix dimensions must match correlations.columns")
    normalized: list[list[float]] = []
    for row_index, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != len(names):
            raise ValueError("correlations.matrix must be square")
        normalized.append(
            [
                finite_number(value, f"correlations.matrix[{row_index}][{column_index}]")
                for column_index, value in enumerate(row)
            ]
        )
    for row in range(len(names)):
        if abs(normalized[row][row] - 1.0) > 1e-9:
            raise ValueError("correlation matrix diagonal must equal one")
        for column in range(len(names)):
            if abs(normalized[row][column]) > 1 or abs(normalized[row][column] - normalized[column][row]) > 1e-9:
                raise ValueError("correlation matrix must be symmetric with values between -1 and 1")
    return [str(name) for name in names], cholesky(normalized)


def numeric_value(distribution: dict[str, Any], z_score: float, integer: bool) -> int | float:
    kind = distribution["kind"]
    if kind == "normal":
        value = distribution["mean"] + distribution["std"] * z_score
        if distribution["min"] is not None:
            value = max(value, distribution["min"])
        if distribution["max"] is not None:
            value = min(value, distribution["max"])
    elif kind == "uniform":
        quantile = NormalDist().cdf(z_score)
        value = distribution["min"] + (distribution["max"] - distribution["min"]) * quantile
    elif kind == "lognormal":
        value = math.exp(distribution["normal_mean"] + distribution["normal_std"] * z_score)
        value = max(value, distribution["min"])
        if distribution["max"] is not None:
            value = min(value, distribution["max"])
    else:
        value = distribution["value"]
    return int(round(value)) if integer else round(float(value), 8)


def generate_rows(spec: dict[str, Any], columns: list[dict[str, Any]], rows: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    numeric = {
        column["name"]: numeric_distribution(column)
        for column in columns
        if column["type"] in {"number", "integer"} and column.get("derived") is None
    }
    weighted = {
        column["name"]: weighted_values(column)
        for column in columns
        if column["type"] in {"categorical", "boolean", "string"} and "generator" not in column
    }
    text_generators = {column["name"]: text_generator_contract(column) for column in columns if "generator" in column}
    datetimes: dict[str, tuple[datetime, datetime]] = {}
    for column in columns:
        if column["type"] != "datetime":
            continue
        start = parse_datetime(column.get("min"), f"{column['name']}.min")
        end = parse_datetime(column.get("max"), f"{column['name']}.max")
        if start >= end:
            raise ValueError(f"{column['name']}.min must be earlier than max")
        datetimes[column["name"]] = (start, end)
    correlation_names, lower = correlation_contract(spec, columns)
    joint_groups = joint_distribution_contract(spec, columns)
    joint_columns = {name for group in joint_groups for name in group["columns"]}
    derived_columns = derived_contract(columns)
    generated: list[dict[str, Any]] = []
    for _row_index in range(rows):
        independent = [rng.gauss(0, 1) for _ in correlation_names]
        correlated = {
            name: sum(lower[index][offset] * independent[offset] for offset in range(index + 1))
            for index, name in enumerate(correlation_names)
        }
        joint_values: dict[str, Any] = {}
        for group in joint_groups:
            selected = rng.choices(group["rows"], weights=[row["weight"] for row in group["rows"]], k=1)[0]
            joint_values.update(selected["values"])
        row: dict[str, Any] = {}
        for column in columns:
            name = column["name"]
            column_type = column["type"]
            if column.get("derived") is not None:
                continue
            if name in joint_columns:
                value = joint_values[name]
            elif column["missing_rate"] and rng.random() < column["missing_rate"]:
                value: Any = None
            elif column_type in {"number", "integer"}:
                z_score = correlated.get(name, rng.gauss(0, 1))
                value = numeric_value(numeric[name], z_score, column_type == "integer")
            elif column_type in {"categorical", "boolean", "string"}:
                if name in text_generators:
                    contract = text_generators[name]
                    length = rng.choices(contract["lengths"], weights=contract["length_weights"], k=1)[0]
                    tokens = rng.choices(contract["tokens"], weights=contract["token_weights"], k=length)
                    value = contract["separator"].join(tokens)
                    if contract["capitalize"]:
                        value = value[:1].upper() + value[1:]
                    value += contract["terminal"]
                else:
                    values, weights = weighted[name]
                    value = rng.choices(values, weights=weights, k=1)[0]
                    if column_type == "boolean" and isinstance(value, str):
                        value = value.strip().lower() in {"true", "1", "yes"}
                    elif column_type == "string":
                        value = str(value)
            elif column_type == "datetime":
                start, end = datetimes[name]
                value = (start + timedelta(seconds=rng.random() * (end - start).total_seconds())).isoformat()
            else:
                prefix = str(column.get("prefix", "proxy"))
                value = f"{prefix}-{uuid.UUID(int=rng.getrandbits(128), version=4)}"
            row[name] = value
        for column in derived_columns:
            row[column["name"]] = derived_value(column, row)
        generated.append(row)
    return generated


def write_rows(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        return
    if suffix == ".json":
        path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        return
    if suffix in {".jsonl", ".ndjson"}:
        with path.open("w", encoding="utf-8", newline="") as handle:
            for row in rows:
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        return
    raise ValueError(f"unsupported proxy format: {suffix or '<none>'}")


def policy_column(column: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"role": column["role"]}
    if column["role"] == "identifier":
        if "surrogate" in column:
            contract = identifier_surrogate_contract(column)
            if contract["strategy"] == "weighted_template":
                entry.update(
                    {
                        "strategy": contract["strategy"],
                        "template": contract["template"],
                        "components": column["surrogate"]["components"],
                    }
                )
            else:
                entry.update({"strategy": contract["strategy"], "prefix": contract["prefix"]})
        else:
            entry.update({"strategy": "uuid", "prefix": str(column.get("prefix", "syn"))})
    elif column["role"] != "drop":
        encoding = {
            "number": "TABULAR_NUMERIC_AUTO",
            "integer": "TABULAR_NUMERIC_DISCRETE",
            "categorical": "TABULAR_CATEGORICAL",
            "boolean": "TABULAR_CATEGORICAL",
            "string": "TABULAR_CHARACTER" if "generator" in column else "TABULAR_CATEGORICAL",
            "datetime": "TABULAR_DATETIME",
        }.get(column["type"])
        if encoding:
            entry["encoding"] = str(column.get("encoding", encoding)).upper()
    return entry


def build_policy(
    spec: dict[str, Any],
    spec_path: Path,
    proxy_path: Path,
    materialization_report: Path,
    output_path: Path,
    generation_report: Path,
    workspace: Path,
    columns: list[dict[str, Any]],
    rows: int,
    seed: int,
) -> dict[str, Any]:
    findings = [
        {
            "column": column["name"],
            "type": column["type"],
            "role": column["role"],
            "decision": "explicit" if column["role_explicit"] else "conservative-default",
        }
        for column in columns
    ]
    return {
        "version": 1,
        "dataset": {
            "input": str(proxy_path),
            "input_kind": "aggregate-proxy",
            "aggregate_spec": str(spec_path),
            "input_report": str(materialization_report),
            "output": str(output_path),
            "report": str(generation_report),
            "workspace": str(workspace),
            "rows": rows,
            "seed": seed,
        },
        "quality": quality_contract(spec),
        "privacy": {
            "default_role": "protected",
            "rare_value_threshold": 5,
            "dp": dp_contract(spec),
            "columns": {column["name"]: policy_column(column) for column in columns},
        },
        "acceptance": {**ACCEPTANCE_DEFAULTS, "columns": {}},
        "planning": {
            "source_rows": rows,
            "source_columns": len(columns),
            "findings": findings,
            "warnings": [
                "Rows were materialized from aggregate constraints and are not observed source records.",
                "Evaluate the final dataset against the declared schema, marginals, missingness, code patterns, "
                "joint distributions, derived constraints, and correlations; proxy-row comparison is not "
                "real-source validation.",
            ],
        },
    }


def validate_paths(paths: dict[str, Path]) -> None:
    resolved = {name: path.resolve() for name, path in paths.items()}
    collisions = [
        f"{left}={right}"
        for index, left in enumerate(resolved)
        for right in list(resolved)[index + 1 :]
        if resolved[left] == resolved[right]
    ]
    if collisions:
        raise ValueError(f"artifact paths must be distinct: {', '.join(collisions)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize aggregate schema/statistics as proxy rows and a Rata generation policy."
    )
    parser.add_argument("spec", type=Path)
    parser.add_argument("proxy", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--materialization-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    if not args.spec.is_file():
        raise FileNotFoundError(args.spec)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or spec.get("version") != 1:
        raise ValueError("spec version must be 1")
    columns = normalize_columns(spec)
    rows = args.rows if args.rows is not None else spec.get("rows")
    seed = args.seed if args.seed is not None else spec.get("seed", 42)
    if isinstance(rows, bool) or not isinstance(rows, int) or rows <= 0:
        raise ValueError("row count must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if args.proxy.suffix.lower() not in OUTPUT_SUFFIXES:
        raise ValueError("proxy rows must use CSV, JSON, JSONL, or NDJSON")
    validate_paths(
        {
            "spec": args.spec,
            "proxy": args.proxy,
            "policy": args.policy,
            "materialization_report": args.materialization_report,
            "output": args.output,
            "generation_report": args.report,
            "workspace": args.workspace,
        }
    )
    existing = [path for path in (args.proxy, args.policy, args.materialization_report) if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite: {', '.join(map(str, existing))}")
    generated = generate_rows(spec, columns, rows, seed)
    write_rows(args.proxy, [column["name"] for column in columns], generated)
    policy = build_policy(
        spec,
        args.spec,
        args.proxy,
        args.materialization_report,
        args.output,
        args.report,
        args.workspace,
        columns,
        rows,
        seed,
    )
    args.policy.parent.mkdir(parents=True, exist_ok=True)
    args.policy.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    materialization = {
        "schema_version": 1,
        "method": "aggregate-constraint-proxy-materialization",
        "spec": str(args.spec),
        "proxy": str(args.proxy),
        "policy": str(args.policy),
        "rows": rows,
        "seed": seed,
        "roles": {role: [column["name"] for column in columns if column["role"] == role] for role in sorted(ROLES)},
        "correlations_requested": bool(spec.get("correlations")),
        "joint_distributions_requested": len(joint_distribution_contract(spec, columns)),
        "derived_columns": [column["name"] for column in derived_contract(columns)],
        "evidence": {
            "spec_sha256": sha256_file(args.spec),
            "proxy_sha256": sha256_file(args.proxy),
        },
        "caveats": [
            "The proxy rows encode declared aggregates and assumptions; they are not original observations.",
            "A downstream model trained on these rows cannot recover relationships omitted from the specification.",
        ],
    }
    args.materialization_report.parent.mkdir(parents=True, exist_ok=True)
    args.materialization_report.write_text(json.dumps(materialization, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "proxy": str(args.proxy),
                "policy": str(args.policy),
                "materialization_report": str(args.materialization_report),
                "rows": rows,
            },
            indent=2,
        )
    )
    return 0


def write_failed_materialization_report(args: argparse.Namespace, error: Exception) -> Path | None:
    report_path = args.materialization_report
    if report_path.exists():
        return None
    inputs_and_outputs = (args.spec, args.proxy, args.policy, args.output, args.report, args.workspace)
    if report_path.resolve() in {path.resolve() for path in inputs_and_outputs}:
        return None
    evidence: dict[str, str] = {}
    for name, path in (("spec", args.spec), ("partial_proxy", args.proxy), ("partial_policy", args.policy)):
        if path.is_file():
            evidence[f"{name}_sha256"] = sha256_file(path)
    error_message = str(error)
    report = {
        "schema_version": 1,
        "passed": False,
        "status": "materialization-failed",
        "method": "aggregate-constraint-proxy-materialization",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "spec": str(args.spec),
        "proxy": str(args.proxy),
        "policy": str(args.policy),
        "error": {
            "type": type(error).__name__,
            "message_sha256": hashlib.sha256(error_message.encode("utf-8")).hexdigest(),
            "message_length": len(error_message),
        },
        "evidence": evidence,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except Exception as error:
        try:
            failure_report = write_failed_materialization_report(args, error)
            if failure_report is not None:
                error.add_note(f"Materialization failure report: {failure_report}")
        except Exception as report_error:
            error.add_note(f"Unable to write materialization failure report: {report_error}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())

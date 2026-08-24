from __future__ import annotations

import pandas as pd
import pytest
from conftest import load_skill_script

plan = load_skill_script("plan-synthetic-data", "plan.py")
generate = load_skill_script("generate-synthetic-data", "generate.py")
evaluate = load_skill_script("evaluate-synthetic-data", "evaluate.py")


@pytest.mark.parametrize("suffix", [".csv", ".json", ".jsonl", ".parquet", ".avro"])
def test_supported_table_formats_round_trip(tmp_path, suffix: str) -> None:
    frame = pd.DataFrame(
        {
            "row_id": [1, 2, 3],
            "score": [1.5, 2.5, 3.5],
            "category": ["a", "b", "a"],
            "active": [True, False, True],
        }
    )
    path = tmp_path / f"table{suffix}"

    generate.write_table(frame, path)

    for loaded in (generate.load_table(path), plan.load_table(path), evaluate.load_table(path)):
        assert list(loaded.columns) == list(frame.columns)
        assert len(loaded) == len(frame)


def test_generation_policy_fingerprint_matches_between_skills() -> None:
    policy = {
        "version": 1,
        "quality": {"profile": "fast", "max_epochs": 3},
        "privacy": {"default_role": "protected", "columns": {"value": {"role": "private"}}},
        "acceptance": {"max_propensity_auc": 0.7},
    }

    assert generate.generation_policy_fingerprint(policy) == evaluate.generation_policy_fingerprint(policy)
    modified = {**policy, "dataset": {"seed": 99}}
    assert generate.generation_policy_fingerprint(policy) != generate.generation_policy_fingerprint(modified)


def test_csv_loaders_preserve_leading_zero_categorical_and_identifier_values(tmp_path) -> None:
    path = tmp_path / "codes.csv"
    path.write_text("county_fips,entity_id,value\n01001,0007,12\n06037,0042,18\n", encoding="utf-8")

    for loader in (generate.load_table, plan.load_table, evaluate.load_table):
        loaded = loader(path, {"county_fips", "entity_id"})
        assert loaded["county_fips"].tolist() == ["01001", "06037"]
        assert loaded["entity_id"].tolist() == ["0007", "0042"]
        assert loaded["value"].tolist() == [12, 18]


def test_policy_marks_code_and_identifier_columns_for_string_preservation() -> None:
    policy = {
        "privacy": {
            "columns": {
                "county_fips": {"role": "public", "encoding": "TABULAR_CATEGORICAL"},
                "entity_id": {"role": "identifier"},
                "location": {"role": "protected", "encoding": "TABULAR_LAT_LONG"},
                "value": {"role": "public", "encoding": "TABULAR_NUMERIC_AUTO"},
            }
        }
    }

    assert generate.string_columns_from_policy(policy) == {"county_fips", "entity_id", "location"}
    assert evaluate.string_columns_from_policy(policy) == {"county_fips", "entity_id", "location"}

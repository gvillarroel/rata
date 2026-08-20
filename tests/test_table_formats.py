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

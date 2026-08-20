from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_evaluation_matrix.py"
SPEC = importlib.util.spec_from_file_location("run_evaluation_matrix", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"unable to load {SCRIPT}")
matrix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matrix)


def test_catalog_starts_with_required_ordered_modalities() -> None:
    catalog = matrix.load_catalog(ROOT / "evaluations" / "catalog.json")

    assert [(item["order"], item["modality"]) for item in catalog["scenarios"]] == [
        (1, "tabular"),
        (2, "tabular+text"),
    ]
    assert catalog["scenarios"][1]["encodings"]["message"] == "TABULAR_CHARACTER"


def test_catalog_rejects_reordered_required_scenarios(tmp_path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scenarios": [
                    {"order": 1, "id": "mixed", "modality": "tabular+text"},
                    {"order": 2, "id": "plain", "modality": "tabular"},
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        matrix.load_catalog(path)
    except ValueError as error:
        assert "tabular, tabular+text" in str(error)
    else:
        raise AssertionError("expected modality ordering failure")


def test_fixture_builders_include_real_tabular_and_text_rows() -> None:
    tabular_columns, tabular = matrix.source_rows("tabular", 12)
    mixed_columns, mixed = matrix.source_rows("tabular-text", 12)

    assert tabular_columns == ["customer_id", "region", "age_band", "monthly_spend", "account_tier"]
    assert len({row["customer_id"] for row in tabular}) == 12
    assert isinstance(tabular[0]["monthly_spend"], float)
    assert mixed_columns[-1] == "message"
    assert all(len(row["message"]) > 40 for row in mixed)

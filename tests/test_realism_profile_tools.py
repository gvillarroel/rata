from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from conftest import ROOT

SPEC = importlib.util.spec_from_file_location("build_realism_profile", ROOT / "tools" / "build_realism_profile.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load realism profile builder")
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def test_weighted_csv_aggregates_duplicate_values_before_top_k(tmp_path: Path) -> None:
    path = tmp_path / "weights.csv"
    path.write_text("token,records\nalpha,10\nbeta,9\nalpha,5\ngamma,12\n", encoding="utf-8")

    assert builder.weighted_csv(path, "token", limit=2) == {"alpha": 15, "gamma": 12}


def test_narrative_length_bands_are_capped_and_reconciled(tmp_path: Path) -> None:
    path = tmp_path / "lengths.csv"
    path.write_text(
        "word_count_band,records\n0001_0049,10\n0101_0149,8\n1000_PLUS,2\n",
        encoding="utf-8",
    )

    assert builder.length_distribution(path) == {"25": 10, "120": 10}

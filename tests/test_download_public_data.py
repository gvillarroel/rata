from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("download_public_data", ROOT / "tools" / "download_public_data.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load public-data downloader")
downloader = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = downloader
SPEC.loader.exec_module(downloader)


def test_classify_legal_suffix_removes_name_specificity() -> None:
    assert downloader.classify_legal_suffix("Example Holdings, Inc.") == "INCORPORATED"
    assert downloader.classify_legal_suffix("Example Logistics LLC") == "LLC"
    assert downloader.classify_legal_suffix("Exemple Québec Ltée") == "LIMITED"
    assert downloader.classify_legal_suffix("Unmarked Trade Name") == "OTHER/NONE"
    assert downloader.classify_legal_suffix(None) == "MISSING"


def test_bucket_numbers_handles_boundaries_and_missing() -> None:
    values = pd.Series([0, 4, 5, None, "invalid"])
    result = downloader.bucket_numbers(
        values,
        [-float("inf"), 1, 5, float("inf")],
        ["ZERO", "1_TO_4", "5_PLUS"],
    )
    assert result.tolist() == ["ZERO", "1_TO_4", "5_PLUS", "MISSING", "MISSING"]


def test_add_counts_aggregates_without_retaining_rows() -> None:
    frame = pd.DataFrame(
        {
            "state": ["IA", "IA", "NY"],
            "type": ["LLC", "LLC", "CORP"],
        }
    )
    counter: Counter[tuple[str, ...]] = Counter()
    downloader.add_counts(counter, frame, ["state", "type"])
    assert counter == Counter({("IA", "LLC"): 2, ("NY", "CORP"): 1})


def test_realism_profile_uses_reproducible_official_sources_and_stages_narratives() -> None:
    sources = {source.key: source for source in downloader.SOURCES}

    assert "nyc_popular_baby_names" in downloader.REALISM_KEYS
    assert "ssa_national_names" not in downloader.REALISM_KEYS
    assert sources["ssa_national_names"].optional is True
    assert sources["cfpb_complaints"].staged is True
    assert all(not sources[key].staged for key in downloader.TIGER_ROAD_KEYS)
    assert sources["census_surnames_2010"].landing_page.startswith("https://www.census.gov/")


def test_default_download_excludes_optional_blocked_source_but_explicit_retry_includes_it() -> None:
    assert "ssa_national_names" not in {source.key for source in downloader._select_sources(set())}
    assert [source.key for source in downloader._select_sources({"ssa_national_names"})] == ["ssa_national_names"]


def test_source_catalog_lists_stable_keys_and_official_metadata(capsys) -> None:
    sources = {source.key: source for source in downloader.SOURCES}
    downloader._print_source_catalog((sources["ssa_national_names"], sources["cfpb_complaints"]))
    output = capsys.readouterr().out

    assert "ssa_national_names [opt-in; retained official artifact]" in output
    assert f"download: {sources['ssa_national_names'].url}" in output
    assert f"publisher: {sources['ssa_national_names'].landing_page}" in output
    assert "cfpb_complaints [default; privacy-minimized after staging]" in output
    assert sources["cfpb_complaints"].purpose in output


def test_github_download_catalog_covers_every_registered_source() -> None:
    catalog = (ROOT / "docs" / "public-data-sources.md").read_text(encoding="utf-8")

    assert "Complete 32-source index" in catalog
    for source in downloader.SOURCES:
        assert f"`{source.key}`" in catalog
        assert source.url in catalog
        assert source.landing_page in catalog


def test_nyc_name_transform_aggregates_ethnicity_rows_and_applies_minimum_count(tmp_path, monkeypatch) -> None:
    source = tmp_path / "names.csv"
    source.write_text(
        "brth_yr,gndr,ethcty,nm,cnt,rnk\n"
        "2024,F,A,OLIVIA,20,1\n"
        "2024,F,A,OLIVIA,20,1\n"
        "2024,F,B,Olivia,10,2\n"
        "2024,M,A,Rare,24,9\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(downloader, "DERIVED_DIR", tmp_path / "derived")
    records = downloader._process_nyc_names(source)
    output = pd.read_csv(records[0]["path"])

    assert output.to_dict(orient="records") == [
        {"given_name": "Olivia", "sex": "F", "records": 30, "first_year": 2024, "last_year": 2024}
    ]

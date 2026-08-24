from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_public_data_coverage",
    ROOT / "tools" / "audit_public_data_coverage.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load public-data coverage auditor")
auditor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = auditor
SPEC.loader.exec_module(auditor)


def test_count_largest_zip_member_rows_excludes_header(tmp_path: Path) -> None:
    archive_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("data.csv", "a,b\n1,2\n3,4\n")
        archive.writestr("readme.txt", "small")
    assert auditor.count_largest_zip_member_rows(archive_path) == 2


def test_count_text_reference_rows_excludes_naics_and_sic_preambles(tmp_path: Path) -> None:
    path = tmp_path / "codes.txt"
    path.write_text(
        "NAICS   DESCRIPTION\n11\tAgriculture\n\nCODE\tSIC DESCRIPTION\n----  TOTAL\n0711  Soil preparation\n",
        encoding="utf-8",
    )

    assert auditor.count_text_reference_rows(path) == 2


def test_summarize_requires_local_records_and_source_families() -> None:
    results = [
        auditor.EvidenceResult(
            key=f"source_{index}",
            source_family=f"family_{index}",
            dataset=f"dataset_{index}",
            publisher="publisher",
            alignment_tier="core",
            aligned_fields="fields",
            record_count=1_000_000,
            record_unit="rows",
            locally_materialized_or_processed=True,
            counts_toward_target=True,
            count_method="test",
            evidence_file="test",
            source_url="https://example.com/data",
            landing_page="https://example.com",
        )
        for index in range(10)
    ]
    summary = auditor.summarize(results)
    assert summary["verified_local_core_records"] == 10_000_000
    assert summary["verified_local_core_source_families"] == 10
    assert summary["passed"] is True


def test_summarize_excludes_server_only_rows_from_local_gate() -> None:
    result = auditor.EvidenceResult(
        key="remote",
        source_family="remote family",
        dataset="remote dataset",
        publisher="publisher",
        alignment_tier="core",
        aligned_fields="fields",
        record_count=20_000_000,
        record_unit="rows",
        locally_materialized_or_processed=False,
        counts_toward_target=True,
        count_method="test",
        evidence_file="test",
        source_url="https://example.com/data",
        landing_page="https://example.com",
    )
    summary = auditor.summarize([result])
    assert summary["verified_local_core_records"] == 0
    assert summary["verified_all_core_records_including_server_aggregates"] == 20_000_000
    assert summary["passed"] is False

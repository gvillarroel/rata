"""Audit public-data coverage against explicit record and source-family targets."""

from __future__ import annotations

import argparse
import csv
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "datasets" / "public-data"
MANIFEST_PATH = BUNDLE_DIR / "manifest.csv"
CSV_REPORT_PATH = BUNDLE_DIR / "coverage-report.csv"
JSON_REPORT_PATH = BUNDLE_DIR / "coverage-report.json"
MARKDOWN_REPORT_PATH = BUNDLE_DIR / "coverage-report.md"

DEFAULT_MIN_RECORDS = 10_000_000
DEFAULT_MIN_SOURCES = 10


@dataclass(frozen=True)
class EvidenceSpec:
    key: str
    source_family: str
    dataset: str
    publisher: str
    alignment_tier: str
    aligned_fields: str
    record_unit: str
    evidence_path: str
    count_method: str
    locally_materialized_or_processed: bool
    counts_toward_target: bool = True


@dataclass(frozen=True)
class EvidenceResult:
    key: str
    source_family: str
    dataset: str
    publisher: str
    alignment_tier: str
    aligned_fields: str
    record_count: int
    record_unit: str
    locally_materialized_or_processed: bool
    counts_toward_target: bool
    count_method: str
    evidence_file: str
    source_url: str
    landing_page: str


SPECS = (
    EvidenceSpec(
        "census_cbp_state_2023",
        "Census County/ZIP Code Business Patterns",
        "County Business Patterns — state",
        "U.S. Census Bureau",
        "core",
        "NAICS, state, legal form, employment, payroll, establishments, size classes",
        "published aggregate rows",
        "datasets/public-data/raw/census_cbp_state_2023.zip",
        "largest_zip_member_rows_minus_header",
        True,
    ),
    EvidenceSpec(
        "census_cbp_county_2023",
        "Census County/ZIP Code Business Patterns",
        "County Business Patterns — county",
        "U.S. Census Bureau",
        "core",
        "NAICS, county, employment, payroll, establishments, size classes",
        "published aggregate rows",
        "datasets/public-data/raw/census_cbp_county_2023.zip",
        "largest_zip_member_rows_minus_header",
        True,
    ),
    EvidenceSpec(
        "census_zbp_detail_2023",
        "Census County/ZIP Code Business Patterns",
        "ZIP Code Business Patterns — industry detail",
        "U.S. Census Bureau",
        "core",
        "ZIP Code, NAICS, establishments, employment-size distribution",
        "published aggregate rows",
        "datasets/public-data/raw/census_zbp_industry_detail_2023.zip",
        "largest_zip_member_rows_minus_header",
        True,
    ),
    EvidenceSpec(
        "census_nes_state_2022",
        "Census Nonemployer Statistics",
        "Nonemployer Statistics — state",
        "U.S. Census Bureau",
        "core",
        "NAICS, state, legal form, establishments, receipts",
        "published aggregate rows",
        "datasets/public-data/raw/census_nes_state_2022.zip",
        "largest_zip_member_rows_minus_header",
        True,
    ),
    EvidenceSpec(
        "census_nes_county_2022",
        "Census Nonemployer Statistics",
        "Nonemployer Statistics — county",
        "U.S. Census Bureau",
        "core",
        "NAICS, county, establishments, receipts",
        "published aggregate rows",
        "datasets/public-data/raw/census_nes_county_2022.zip",
        "largest_zip_member_rows_minus_header",
        True,
    ),
    EvidenceSpec(
        "census_abs_company_summary_2023",
        "Census Annual Business Survey",
        "Annual Business Survey company summary",
        "U.S. Census Bureau",
        "core",
        "NAICS, geography, firm count, employment, payroll, receipts, owner-demographic aggregates",
        "published aggregate rows",
        "datasets/public-data/raw/census_abs_company_summary_2023.zip",
        "largest_zip_member_rows_minus_header",
        True,
    ),
    EvidenceSpec(
        "census_bds_state_firm_size_2023",
        "Census Business Dynamics Statistics",
        "Business Dynamics Statistics — state by firm size",
        "U.S. Census Bureau",
        "core",
        "state, firm size, firm age dynamics, job creation and destruction",
        "published aggregate rows",
        "datasets/public-data/raw/census_bds_state_by_firm_size_2023.csv",
        "csv_rows_minus_header",
        True,
    ),
    EvidenceSpec(
        "bls_qcew_annual_singlefile_2025",
        "BLS Quarterly Census of Employment and Wages",
        "QCEW annual single file",
        "U.S. Bureau of Labor Statistics",
        "core",
        "NAICS, geography, ownership, establishments, employment, payroll, wages",
        "published aggregate rows",
        "datasets/public-data/raw/bls_qcew_annual_singlefile_2025.zip",
        "largest_zip_member_rows_minus_header",
        True,
    ),
    EvidenceSpec(
        "iowa_business_registry_distribution",
        "Iowa Active Business Entities",
        "Active Iowa business entities",
        "Iowa Secretary of State",
        "core",
        "entity type, effective year, home-office geography",
        "source entity rows processed",
        "datasets/public-data/derived/iowa_business_registry_distribution.csv",
        "sum_records_column",
        True,
    ),
    EvidenceSpec(
        "colorado_business_entities_us_distribution",
        "Colorado Business Entities",
        "Business entities with U.S. principal addresses",
        "Colorado Department of State",
        "core",
        "entity type, status, formation year, jurisdiction, principal state/country",
        "published U.S.-only aggregate rows",
        "datasets/public-data/raw/colorado_business_entities_us_distribution.csv",
        "csv_rows_minus_header",
        True,
    ),
    EvidenceSpec(
        "cms_nppes_type2_weekly_distribution",
        "CMS NPPES Type-2 Organizations",
        "NPPES weekly Type-2 organization update",
        "Centers for Medicare & Medicaid Services",
        "core",
        "organization taxonomy, practice state, enumeration/update year, deactivation",
        "Type-2 source rows processed",
        "datasets/public-data/derived/cms_nppes_type2_weekly_distribution.csv",
        "sum_records_column",
        True,
    ),
    EvidenceSpec(
        "sba_ppp_by_state_naics_distribution",
        "SBA Paycheck Protection Program FOIA",
        "PPP loans above $150,000",
        "U.S. Small Business Administration",
        "core",
        "state, NAICS, jobs, business type/age, rural/urban, loan-size distribution",
        "source loan rows processed",
        "datasets/public-data/derived/sba_ppp_by_state_naics_distribution.csv",
        "sum_loans_column",
        True,
    ),
    EvidenceSpec(
        "sec_company_tickers_exchange",
        "SEC EDGAR Company Associations",
        "Company, CIK, ticker, and exchange associations",
        "U.S. Securities and Exchange Commission",
        "core",
        "public-company legal name, CIK, ticker, exchange",
        "published company association rows",
        "datasets/public-data/raw/sec_company_tickers_exchange.json",
        "sec_json_data_rows",
        True,
    ),
    EvidenceSpec(
        "fmcsa_company_census_distribution",
        "FMCSA Company Census",
        "Company Census privacy-minimized distribution",
        "Federal Motor Carrier Safety Administration",
        "core",
        "country/state, status, carrier operation, organization type, fleet-size class",
        "underlying company rows aggregated by the source API",
        "datasets/public-data/raw/fmcsa_company_census_distribution.csv",
        "sum_records_column",
        False,
    ),
    EvidenceSpec(
        "census_gazetteer_counties_2025",
        "Census Gazetteer",
        "Gazetteer counties",
        "U.S. Census Bureau",
        "supporting",
        "county/FIPS, land/water area, representative coordinates",
        "geographic reference rows",
        "datasets/public-data/raw/census_gazetteer_counties_2025.zip",
        "largest_zip_member_rows_minus_header",
        True,
        counts_toward_target=False,
    ),
    EvidenceSpec(
        "census_gazetteer_places_2025",
        "Census Gazetteer",
        "Gazetteer places",
        "U.S. Census Bureau",
        "supporting",
        "place/state, area, representative coordinates",
        "geographic reference rows",
        "datasets/public-data/raw/census_gazetteer_places_2025.zip",
        "largest_zip_member_rows_minus_header",
        True,
        counts_toward_target=False,
    ),
    EvidenceSpec(
        "census_gazetteer_zcta_2025",
        "Census Gazetteer",
        "Gazetteer ZIP Code Tabulation Areas",
        "U.S. Census Bureau",
        "supporting",
        "ZCTA, area, representative coordinates",
        "geographic reference rows",
        "datasets/public-data/raw/census_gazetteer_zcta_2025.zip",
        "largest_zip_member_rows_minus_header",
        True,
        counts_toward_target=False,
    ),
    EvidenceSpec(
        "census_naics_2022_descriptions",
        "Census Industry Classifications",
        "2022 NAICS descriptions",
        "U.S. Census Bureau",
        "supporting",
        "official NAICS codes and descriptions",
        "classification reference rows",
        "datasets/public-data/raw/census_naics_2022_descriptions.txt",
        "text_nonblank_rows_after_preamble",
        True,
        counts_toward_target=False,
    ),
    EvidenceSpec(
        "census_sic_descriptions",
        "Census Industry Classifications",
        "1987 SIC descriptions used by SUSB",
        "U.S. Census Bureau",
        "supporting",
        "official SIC hierarchy and descriptions",
        "classification reference rows",
        "datasets/public-data/raw/census_sic_descriptions_1988_1997.txt",
        "text_nonblank_rows_after_preamble",
        True,
        counts_toward_target=False,
    ),
)


def _count_stream_lines(stream: Any) -> int:
    lines = 0
    last_byte = b""
    while block := stream.read(1024 * 1024):
        lines += block.count(b"\n")
        last_byte = block[-1:]
    return lines + (1 if last_byte and last_byte != b"\n" else 0)


def count_largest_zip_member_rows(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if not members:
            raise ValueError(f"Archive has no members: {path}")
        member = max(members, key=lambda candidate: candidate.file_size)
        with archive.open(member) as stream:
            return max(_count_stream_lines(stream) - 1, 0)


def count_csv_rows(path: Path) -> int:
    with path.open("rb") as stream:
        return max(_count_stream_lines(stream) - 1, 0)


def sum_csv_column(path: Path, column: str) -> int:
    total = 0
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or column not in reader.fieldnames:
            raise ValueError(f"Missing {column!r} in {path}")
        for row in reader:
            value = row[column].strip()
            if value:
                total += int(float(value))
    return total


def count_sec_json_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise ValueError(f"Expected SEC JSON object with a data list: {path}")
    return len(data)


def count_text_reference_rows(path: Path) -> int:
    rows = 0
    with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
        for line in stream:
            stripped = line.strip()
            if not stripped or stripped.startswith(("NAICS", "CODE", "----", "1988-1997")):
                continue
            rows += 1
    return rows


def _load_manifest() -> dict[str, dict[str, str]]:
    with MANIFEST_PATH.open("r", encoding="utf-8", newline="") as stream:
        return {row["key"]: row for row in csv.DictReader(stream)}


def _count(spec: EvidenceSpec, path: Path) -> int:
    methods = {
        "largest_zip_member_rows_minus_header": lambda: count_largest_zip_member_rows(path),
        "csv_rows_minus_header": lambda: count_csv_rows(path),
        "sum_records_column": lambda: sum_csv_column(path, "records"),
        "sum_loans_column": lambda: sum_csv_column(path, "loans"),
        "sec_json_data_rows": lambda: count_sec_json_rows(path),
        "text_nonblank_rows_after_preamble": lambda: count_text_reference_rows(path),
    }
    return methods[spec.count_method]()


def collect_evidence() -> list[EvidenceResult]:
    manifest = _load_manifest()
    results: list[EvidenceResult] = []
    for spec in SPECS:
        path = ROOT / spec.evidence_path
        if not path.is_file():
            raise FileNotFoundError(f"Coverage evidence is missing: {path}")
        record_count = _count(spec, path)
        manifest_row = manifest.get(spec.key)
        if manifest_row is None:
            raise ValueError(f"Manifest entry is missing for {spec.key}")
        results.append(
            EvidenceResult(
                key=spec.key,
                source_family=spec.source_family,
                dataset=spec.dataset,
                publisher=spec.publisher,
                alignment_tier=spec.alignment_tier,
                aligned_fields=spec.aligned_fields,
                record_count=record_count,
                record_unit=spec.record_unit,
                locally_materialized_or_processed=spec.locally_materialized_or_processed,
                counts_toward_target=spec.counts_toward_target,
                count_method=spec.count_method,
                evidence_file=spec.evidence_path,
                source_url=manifest_row["source_url"],
                landing_page=manifest_row["landing_page"],
            )
        )
    return results


def summarize(
    results: list[EvidenceResult],
    min_records: int = DEFAULT_MIN_RECORDS,
    min_sources: int = DEFAULT_MIN_SOURCES,
) -> dict[str, Any]:
    local_core = [
        result
        for result in results
        if result.counts_toward_target and result.locally_materialized_or_processed and result.record_count > 0
    ]
    all_core = [result for result in results if result.counts_toward_target and result.record_count > 0]
    local_records = sum(result.record_count for result in local_core)
    all_records = sum(result.record_count for result in all_core)
    local_families = sorted({result.source_family for result in local_core})
    all_families = sorted({result.source_family for result in all_core})
    publishers = sorted({result.publisher for result in all_core})
    return {
        "minimum_records": min_records,
        "minimum_source_families": min_sources,
        "verified_local_core_records": local_records,
        "verified_local_core_source_families": len(local_families),
        "verified_all_core_records_including_server_aggregates": all_records,
        "verified_all_core_source_families": len(all_families),
        "distinct_core_publishers": len(publishers),
        "local_core_source_family_names": local_families,
        "all_core_source_family_names": all_families,
        "core_publisher_names": publishers,
        "records_target_passed": local_records >= min_records,
        "sources_target_passed": len(local_families) >= min_sources,
        "passed": local_records >= min_records and len(local_families) >= min_sources,
        "counting_note": (
            "Counts are source rows or published aggregate rows, not deduplicated businesses. "
            "Privacy-minimized input counts are reconciled from non-overlapping aggregate totals. "
            "FMCSA underlying rows are reported separately and excluded from the local threshold."
        ),
    }


def write_reports(results: list[EvidenceResult], summary: dict[str, Any]) -> None:
    rows = [asdict(result) for result in results]
    with CSV_REPORT_PATH.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with JSON_REPORT_PATH.open("w", encoding="utf-8") as stream:
        json.dump({"summary": summary, "sources": rows}, stream, indent=2)
        stream.write("\n")

    lines = [
        "# Public-data coverage audit",
        "",
        f"- Local aligned core records: **{summary['verified_local_core_records']:,}**",
        f"- Local core source families: **{summary['verified_local_core_source_families']}**",
        "- Core records including the U.S.-only FMCSA server-side source coverage: "
        f"**{summary['verified_all_core_records_including_server_aggregates']:,}**",
        f"- Core source families including FMCSA: **{summary['verified_all_core_source_families']}**",
        f"- Distinct official publishers: **{summary['distinct_core_publishers']}**",
        f"- Threshold result: **{'PASS' if summary['passed'] else 'FAIL'}**",
        "",
        summary["counting_note"],
        "",
        "| Source family | Dataset | Records | Local/process evidence |",
        "| --- | --- | ---: | --- |",
    ]
    for result in results:
        if not result.counts_toward_target:
            continue
        local = "yes" if result.locally_materialized_or_processed else "server aggregate only"
        lines.append(f"| {result.source_family} | {result.dataset} | {result.record_count:,} | {local} |")
    MARKDOWN_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-records", type=int, default=DEFAULT_MIN_RECORDS)
    parser.add_argument("--min-sources", type=int, default=DEFAULT_MIN_SOURCES)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.min_records < 1 or args.min_sources < 1:
        raise ValueError("coverage targets must be positive")
    results = collect_evidence()
    summary = summarize(results, min_records=args.min_records, min_sources=args.min_sources)
    write_reports(results, summary)
    print(f"Local aligned core records: {summary['verified_local_core_records']:,}")
    print(f"Local core source families: {summary['verified_local_core_source_families']}")
    print(
        "Core records including the U.S.-only FMCSA server aggregate: "
        f"{summary['verified_all_core_records_including_server_aggregates']:,}"
    )
    print(f"Coverage gate: {'PASS' if summary['passed'] else 'FAIL'}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

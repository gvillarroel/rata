"""Audit retained public calibration data for integrity, structure, and calibration fitness."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "datasets" / "public-data"
MANIFEST = BUNDLE / "manifest.csv"
COVERAGE = BUNDLE / "coverage-report.json"
EXAMPLE_COVERAGE = BUNDLE / "examples" / "coverage-report.json"
DEFAULT_JSON_REPORT = BUNDLE / "quality-report.json"
DEFAULT_MARKDOWN_REPORT = BUNDLE / "quality-report.md"

SUPPRESSION_MARKERS = {"", "N", "D", "S", "X", "(X)", "NA", "N/A", "NULL"}
FORBIDDEN_MINIMIZED_COLUMNS = {
    "address",
    "borrower_name",
    "cik",
    "company_name",
    "email",
    "legal_name",
    "loan_number",
    "npi",
    "phone",
    "provider_name",
    "recipient_name",
    "ssn",
    "tax_id",
    "ticker",
    "uei",
}

NAICS_PATTERN = r"[0-9/-]{2,6}"


@dataclass(frozen=True)
class DelimitedRule:
    required: tuple[str, ...]
    numeric: tuple[str, ...] = ()
    patterns: tuple[tuple[str, str], ...] = ()
    dimensions: tuple[str, ...] = ()
    weight: str | None = None
    delimiter: str = ","
    signed_numeric: tuple[str, ...] = ()
    allowed_values: tuple[tuple[str, tuple[str, ...]], ...] = ()
    duplicates_are_warning: bool = False


RULES: dict[str, DelimitedRule] = {
    "census_surnames_2010": DelimitedRule(
        ("name", "rank", "count"),
        ("rank", "count"),
        dimensions=("name",),
        weight="count",
    ),
    "nyc_popular_baby_names": DelimitedRule(
        ("brth_yr", "gndr", "ethcty", "nm", "cnt", "rnk"),
        ("brth_yr", "cnt", "rnk"),
        (("brth_yr", r"\d{4}"), ("gndr", r"[FM](?:EMALE|ALE)?")),
        ("brth_yr", "gndr", "ethcty", "nm"),
        "cnt",
        duplicates_are_warning=True,
    ),
    "census_cbp_state_2023": DelimitedRule(
        ("fipstate", "naics", "lfo", "emp", "ap", "est"),
        ("emp", "qp1", "ap", "est"),
        (("fipstate", r"\d{2}"), ("naics", NAICS_PATTERN)),
    ),
    "census_cbp_county_2023": DelimitedRule(
        ("fipstate", "fipscty", "naics", "emp", "ap", "est"),
        ("emp", "qp1", "ap", "est"),
        (("fipstate", r"\d{2}"), ("fipscty", r"\d{3}"), ("naics", NAICS_PATTERN)),
    ),
    "census_zbp_detail_2023": DelimitedRule(
        ("zip", "name", "naics", "est", "city", "stabbr", "cty_name"),
        ("est",),
        (("zip", r"\d{5}"), ("naics", NAICS_PATTERN), ("stabbr", r"[A-Z]{2}")),
    ),
    "census_nes_state_2022": DelimitedRule(
        ("ST", "NAICS", "LFO", "ESTAB", "RCPTOT"),
        ("ESTAB", "RCPTOT"),
        (("ST", r"\d{2}"), ("NAICS", NAICS_PATTERN)),
    ),
    "census_nes_county_2022": DelimitedRule(
        ("ST", "CTY", "NAICS", "ESTAB", "RCPTOT"),
        ("ESTAB", "RCPTOT"),
        (("ST", r"\d{2}"), ("CTY", r"\d{3}"), ("NAICS", NAICS_PATTERN)),
    ),
    "census_abs_company_summary_2023": DelimitedRule(
        ("#GEO_ID", "GEOTYPE", "ST", "NAICS2022", "YEAR", "FIRMPDEMP", "RCPPDEMP", "EMP", "PAYANN"),
        ("FIRMPDEMP", "RCPPDEMP", "EMP", "PAYANN"),
        (("ST", r"\d{2}"), ("NAICS2022", NAICS_PATTERN), ("YEAR", r"\d{4}")),
        delimiter="|",
    ),
    "census_bds_state_firm_size_2023": DelimitedRule(
        ("year", "st", "fsize", "firms", "estabs", "emp", "job_creation", "job_destruction"),
        ("firms", "estabs", "emp", "job_creation", "job_destruction"),
        (("year", r"\d{4}"), ("st", r"\d{2}")),
    ),
    "bls_qcew_annual_singlefile_2025": DelimitedRule(
        (
            "area_fips",
            "own_code",
            "industry_code",
            "year",
            "annual_avg_estabs",
            "annual_avg_emplvl",
            "total_annual_wages",
            "avg_annual_pay",
        ),
        ("annual_avg_estabs", "annual_avg_emplvl", "total_annual_wages", "avg_annual_pay"),
        (("area_fips", r"[A-Z0-9]{5}"), ("industry_code", r"[A-Z0-9-]{2,10}"), ("year", r"\d{4}")),
    ),
    "census_gazetteer_counties_2025": DelimitedRule(
        ("USPS", "GEOID", "NAME", "ALAND", "AWATER", "INTPTLAT", "INTPTLONG"),
        ("ALAND", "AWATER", "INTPTLAT", "INTPTLONG"),
        (("USPS", r"[A-Z]{2}"), ("GEOID", r"\d{5}")),
        delimiter="|",
        signed_numeric=("INTPTLAT", "INTPTLONG"),
    ),
    "census_gazetteer_places_2025": DelimitedRule(
        ("USPS", "GEOID", "NAME", "ALAND", "AWATER", "INTPTLAT", "INTPTLONG"),
        ("ALAND", "AWATER", "INTPTLAT", "INTPTLONG"),
        (("USPS", r"[A-Z]{2}"), ("GEOID", r"\d{7}")),
        delimiter="|",
        signed_numeric=("INTPTLAT", "INTPTLONG"),
    ),
    "census_gazetteer_zcta_2025": DelimitedRule(
        ("GEOID", "ALAND", "AWATER", "INTPTLAT", "INTPTLONG"),
        ("ALAND", "AWATER", "INTPTLAT", "INTPTLONG"),
        (("GEOID", r"\d{5}"),),
        delimiter="|",
        signed_numeric=("INTPTLAT", "INTPTLONG"),
    ),
    "fmcsa_company_census_distribution": DelimitedRule(
        ("phy_country", "phy_state", "status_code", "carrier_operation", "business_org_desc", "fleetsize", "records"),
        ("records",),
        (("phy_country", r"[A-Z]{2}"), ("phy_state", r"[A-Z]{2}")),
        ("phy_country", "phy_state", "status_code", "carrier_operation", "business_org_desc", "fleetsize"),
        "records",
        allowed_values=(("phy_country", ("US",)),),
    ),
    "iowa_business_registry_distribution": DelimitedRule(
        ("corporation_type", "effective_year", "home_office_state", "home_office_country", "records"),
        ("records",),
        (("effective_year", r"\d{4}"), ("home_office_country", r"US")),
        ("corporation_type", "effective_year", "home_office_state", "home_office_country"),
        "records",
        allowed_values=(("home_office_country", ("US",)),),
    ),
    "iowa_legal_name_pattern_distribution": DelimitedRule(
        ("corporation_type", "legal_suffix", "records"),
        ("records",),
        dimensions=("corporation_type", "legal_suffix"),
        weight="records",
    ),
    "colorado_business_entities_us_distribution": DelimitedRule(
        (
            "entitytype",
            "entitystatus",
            "jurisdictonofformation",
            "principalstate",
            "principalcountry",
            "formation_year",
            "records",
        ),
        ("records",),
        (("principalcountry", r"US"), ("formation_year", r"\d{4}")),
        (
            "entitytype",
            "entitystatus",
            "jurisdictonofformation",
            "principalstate",
            "principalcountry",
            "formation_year",
        ),
        "records",
        allowed_values=(("principalcountry", ("US",)),),
    ),
    "cms_nppes_type2_weekly_distribution": DelimitedRule(
        ("practice_state", "taxonomy_code", "enumeration_year", "last_update_year", "is_deactivated", "records"),
        ("records",),
        (
            ("practice_state", r"[A-Z .,'-]{2,30}"),
            ("taxonomy_code", r"[A-Z0-9]{10}"),
            ("enumeration_year", r"\d{4}"),
            ("last_update_year", r"\d{4}"),
            ("is_deactivated", r"[YN]"),
        ),
        ("practice_state", "taxonomy_code", "enumeration_year", "last_update_year", "is_deactivated"),
        "records",
    ),
    "sba_ppp_by_state_naics_distribution": DelimitedRule(
        ("borrower_state", "naics_code", "loans", "total_approval", "jobs_reported", "jobs_nonnull"),
        ("loans", "total_approval", "jobs_reported", "jobs_nonnull"),
        (("borrower_state", r"[A-Z]{2}"), ("naics_code", r"\d{6}")),
        ("borrower_state", "naics_code"),
        "loans",
    ),
    "sba_ppp_business_profile_distribution": DelimitedRule(
        ("business_type", "business_age", "rural_urban", "loan_size_band", "jobs_band", "loans", "total_approval"),
        ("loans", "total_approval"),
        (("rural_urban", r"[RU]"),),
        ("business_type", "business_age", "rural_urban", "loan_size_band", "jobs_band"),
        "loans",
    ),
    "census_surname_distribution": DelimitedRule(
        ("surname", "records", "rank"),
        ("records", "rank"),
        dimensions=("surname",),
        weight="records",
    ),
    "nyc_given_name_distribution": DelimitedRule(
        ("given_name", "sex", "records", "first_year", "last_year"),
        ("records", "first_year", "last_year"),
        (("sex", r"[FM]"), ("first_year", r"\d{4}"), ("last_year", r"\d{4}")),
        ("given_name", "sex"),
        "records",
    ),
    "usps_street_suffix_reference": DelimitedRule(
        ("source_suffix", "standard_suffix"),
        patterns=(("source_suffix", r"[A-Z]+"), ("standard_suffix", r"[A-Z]+")),
        dimensions=("source_suffix",),
    ),
    "tiger_street_name_distribution": DelimitedRule(
        ("street_name", "records"),
        ("records",),
        dimensions=("street_name",),
        weight="records",
    ),
    "tiger_street_suffix_distribution": DelimitedRule(
        ("standard_suffix", "records"),
        ("records",),
        (("standard_suffix", r"[A-Z]+"),),
        ("standard_suffix",),
        "records",
    ),
    "sec_business_name_token_distribution": DelimitedRule(
        ("token", "records", "document_frequency"),
        ("records", "document_frequency"),
        dimensions=("token",),
        weight="records",
    ),
    "cfpb_narrative_token_distribution": DelimitedRule(
        ("token", "records", "document_frequency"),
        ("records", "document_frequency"),
        dimensions=("token",),
        weight="records",
    ),
    "cfpb_narrative_length_distribution": DelimitedRule(
        ("word_count_band", "records"),
        ("records",),
        (("word_count_band", r"(?:\d{4}_\d{4}|1000_PLUS)"),),
        ("word_count_band",),
        "records",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path = MANIFEST) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("public-data manifest is empty")
    keys = [row.get("key", "") for row in rows]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("public-data manifest keys must be present and unique")
    return rows


def _number(value: str) -> float | None:
    normalized = value.strip().upper()
    if normalized in SUPPRESSION_MARKERS:
        return None
    try:
        result = float(normalized)
    except ValueError:
        return math.nan
    return result if math.isfinite(result) else math.nan


def profile_delimited(handle: TextIO, rule: DelimitedRule, full_scan: bool = True) -> dict[str, Any]:
    reader = csv.DictReader(handle, delimiter=rule.delimiter)
    columns = [str(column).lstrip("\ufeff") for column in reader.fieldnames or []]
    if reader.fieldnames:
        reader.fieldnames = columns
    missing_columns = sorted(set(rule.required) - set(columns))
    pattern_violations = {column: 0 for column, _pattern in rule.patterns}
    allowed_value_violations = {column: 0 for column, _values in rule.allowed_values}
    numeric_parse_violations = {column: 0 for column in rule.numeric}
    numeric_negative_values = {column: 0 for column in rule.numeric}
    missing_values = {column: 0 for column in columns}
    duplicates = 0
    seen: set[tuple[str, ...]] = set()
    weight_total = 0.0
    rows = 0
    malformed_rows = 0
    for row in reader:
        rows += 1
        if None in row:
            malformed_rows += 1
        for column in columns:
            if not str(row.get(column, "")).strip():
                missing_values[column] += 1
        for column, pattern in rule.patterns:
            value = str(row.get(column, "")).strip()
            if value and re.fullmatch(pattern, value) is None:
                pattern_violations[column] += 1
        for column, allowed_values in rule.allowed_values:
            value = str(row.get(column, "")).strip()
            if value and value not in allowed_values:
                allowed_value_violations[column] += 1
        for column in rule.numeric:
            raw = str(row.get(column, ""))
            value = _number(raw)
            if value is None:
                continue
            if math.isnan(value):
                numeric_parse_violations[column] += 1
            elif value < 0 and column not in rule.signed_numeric:
                numeric_negative_values[column] += 1
        if rule.dimensions:
            key = tuple(str(row.get(column, "")).strip() for column in rule.dimensions)
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)
        if rule.weight:
            value = _number(str(row.get(rule.weight, "")))
            if value is not None and not math.isnan(value):
                weight_total += value
        if not full_scan and rows >= 10_000:
            break
    return {
        "rows_scanned": rows,
        "scan_scope": "full" if full_scan else "first-10000",
        "columns": columns,
        "missing_required_columns": missing_columns,
        "malformed_rows": malformed_rows,
        "numeric_parse_violations": numeric_parse_violations,
        "numeric_negative_values": numeric_negative_values,
        "pattern_violations": pattern_violations,
        "allowed_value_violations": allowed_value_violations,
        "duplicate_dimension_rows": duplicates,
        "weight_total": weight_total if rule.weight else None,
        "missing_rates": {column: round(count / rows, 8) if rows else None for column, count in missing_values.items()},
    }


def _largest_data_member(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    candidates = [
        member
        for member in archive.infolist()
        if not member.is_dir() and Path(member.filename).suffix.lower() in {".csv", ".dat", ".txt"}
    ]
    if not candidates:
        raise ValueError("archive contains no delimited data member")
    return max(candidates, key=lambda member: member.file_size)


def profile_delimited_path(path: Path, rule: DelimitedRule, full_scan: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    archive_metrics: dict[str, Any] = {}
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            member = _largest_data_member(archive)
            archive_metrics = {
                "archive_crc_passed": bad_member is None,
                "archive_bad_member": bad_member,
                "archive_members": len([item for item in archive.infolist() if not item.is_dir()]),
                "data_member": member.filename,
                "uncompressed_bytes": member.file_size,
            }
            with (
                archive.open(member) as binary,
                io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline="") as text,
            ):
                return profile_delimited(text, rule, full_scan), archive_metrics
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        return profile_delimited(handle, rule, full_scan), archive_metrics


def profile_classification_text(path: Path, key: str) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if key == "census_naics_2022_descriptions":
        pattern = re.compile(r"^\s*([0-9-]{2,6})\s+(.+?)\s*$")
    else:
        pattern = re.compile(r"^\s*([0-9-]{2,4})\s{2,}(.+?)\s*$")
    parsed = [match.groups() for line in lines if (match := pattern.match(line))]
    codes = [code for code, _description in parsed]
    return {
        "rows_scanned": len(parsed),
        "columns": ["code", "description"],
        "duplicate_codes": len(codes) - len(set(codes)),
        "blank_descriptions": sum(not description.strip() for _code, description in parsed),
    }


def profile_sec_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    fields = payload.get("fields")
    rows = payload.get("data")
    required = ["cik", "name", "ticker", "exchange"]
    if not isinstance(fields, list) or not isinstance(rows, list):
        return {"rows_scanned": 0, "columns": [], "missing_required_columns": required, "malformed_rows": 1}
    malformed = sum(not isinstance(row, list) or len(row) != len(fields) for row in rows)
    indexes = {name: fields.index(name) for name in required if name in fields}
    missing = sorted(set(required) - set(indexes))
    cik_invalid = 0
    blank_values = {name: 0 for name in required}
    unique_rows: set[tuple[str, str, str, str]] = set()
    duplicates = 0
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields) or missing:
            continue
        values = tuple(str(row[indexes[name]]).strip() for name in required)
        for name, value in zip(required, values, strict=True):
            blank_values[name] += not value
        try:
            cik_invalid += int(int(values[0]) <= 0)
        except ValueError:
            cik_invalid += 1
        if values in unique_rows:
            duplicates += 1
        unique_rows.add(values)
    return {
        "rows_scanned": len(rows),
        "columns": fields,
        "missing_required_columns": missing,
        "malformed_rows": malformed,
        "invalid_cik_values": cik_invalid,
        "blank_values": blank_values,
        "duplicate_associations": duplicates,
    }


def profile_xlsx(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        names = set(archive.namelist())
    return {
        "archive_crc_passed": bad_member is None,
        "archive_bad_member": bad_member,
        "workbook_present": "xl/workbook.xml" in names,
        "rows_scanned": None,
    }


def profile_usps_html(path: Path) -> dict[str, Any]:
    document = path.read_text(encoding="utf-8", errors="replace")
    required = ["C1 Street Suffix Abbreviations", "Postal Service", "STREET", "AVENUE"]
    missing = [value for value in required if value.lower() not in document.lower()]
    return {
        "rows_scanned": len(re.findall(r"<tr\b", document, flags=re.IGNORECASE)),
        "columns": ["primary_suffix", "common_suffix", "standard_suffix"],
        "missing_required_columns": missing,
        "malformed_rows": 0,
    }


def profile_tiger_dbf(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        members = [name for name in archive.namelist() if name.lower().endswith(".dbf")]
        if not members:
            return {
                "rows_scanned": 0,
                "columns": [],
                "missing_required_columns": ["FULLNAME", "MTFCC"],
                "archive_crc_passed": bad_member is None,
            }
        with archive.open(members[0]) as source:
            header = source.read(32)
            record_count = int.from_bytes(header[4:8], "little")
            header_length = int.from_bytes(header[8:10], "little")
            descriptors = source.read(header_length - 33)
    fields = []
    for offset in range(0, len(descriptors), 32):
        descriptor = descriptors[offset : offset + 32]
        if len(descriptor) < 32 or descriptor[0] == 0x0D:
            break
        fields.append(descriptor[:11].split(b"\x00", 1)[0].decode("ascii", "replace").strip())
    return {
        "rows_scanned": record_count,
        "columns": fields,
        "missing_required_columns": sorted({"FULLNAME", "MTFCC"} - set(fields)),
        "archive_crc_passed": bad_member is None,
        "archive_bad_member": bad_member,
    }


def artifact_failures(metrics: dict[str, Any], rule: DelimitedRule | None = None) -> list[str]:
    failures = []
    for field in ("missing_required_columns",):
        if metrics.get(field):
            failures.append(field)
    for field in ("malformed_rows", "invalid_cik_values"):
        if metrics.get(field, 0):
            failures.append(field)
    if metrics.get("duplicate_dimension_rows", 0) and not (rule and rule.duplicates_are_warning):
        failures.append("duplicate_dimension_rows")
    for field in (
        "numeric_parse_violations",
        "numeric_negative_values",
        "pattern_violations",
        "allowed_value_violations",
    ):
        if any(metrics.get(field, {}).values()):
            failures.append(field)
    if metrics.get("archive_crc_passed") is False or metrics.get("workbook_present") is False:
        failures.append("archive_integrity")
    if rule and rule.weight and not metrics.get("weight_total", 0) > 0:
        failures.append("aggregate_weight_total")
    return failures


def audit_artifact(row: dict[str, str], full_scan: bool) -> dict[str, Any]:
    key = row["key"]
    path = ROOT / row["local_path"]
    result: dict[str, Any] = {
        "key": key,
        "title": row["title"],
        "artifact_type": row["artifact_type"],
        "geographic_scope": row.get("geographic_scope", ""),
        "path": row["local_path"],
        "exists": path.is_file(),
        "failures": [],
        "warnings": [],
    }
    if result["geographic_scope"] != "United States":
        result["failures"].append("non_us_geographic_scope")
    if not path.is_file():
        result["failures"].append("missing_file")
        result["status"] = "failed"
        return result
    expected_bytes = int(row["bytes"])
    actual_bytes = path.stat().st_size
    actual_sha = sha256_file(path)
    result["integrity"] = {
        "expected_bytes": expected_bytes,
        "actual_bytes": actual_bytes,
        "size_matches": actual_bytes == expected_bytes,
        "sha256_matches": actual_sha == row["sha256"],
        "sha256": actual_sha,
    }
    if actual_bytes != expected_bytes:
        result["failures"].append("size_mismatch")
    if actual_sha != row["sha256"]:
        result["failures"].append("sha256_mismatch")

    rule = RULES.get(key)
    archive: dict[str, Any] = {}
    if rule:
        metrics, archive = profile_delimited_path(path, rule, full_scan)
    elif key in {"census_naics_2022_descriptions", "census_sic_descriptions"}:
        metrics = profile_classification_text(path, key)
    elif key == "sec_company_tickers_exchange":
        metrics = profile_sec_json(path)
    elif key == "sba_ppp_data_dictionary":
        metrics = profile_xlsx(path)
    elif key == "usps_publication_28_suffixes":
        metrics = profile_usps_html(path)
    elif key.startswith("tiger_roads_"):
        metrics = profile_tiger_dbf(path)
    else:
        metrics = {"rows_scanned": None, "unsupported_profile": True}
        result["failures"].append("missing_quality_profile")
    metrics.update(archive)
    result["metrics"] = metrics
    result["failures"].extend(artifact_failures(metrics, rule))
    if rule and rule.duplicates_are_warning and metrics.get("duplicate_dimension_rows", 0):
        result["warnings"].append({"publisher_duplicate_dimension_rows": metrics["duplicate_dimension_rows"]})

    if row["artifact_type"] == "privacy_minimized_distribution":
        forbidden = sorted(set(metrics.get("columns", [])) & FORBIDDEN_MINIMIZED_COLUMNS)
        result["privacy"] = {"forbidden_columns": forbidden, "passed": not forbidden}
        if forbidden:
            result["failures"].append("privacy_forbidden_columns")
    high_missing = {
        column: rate
        for column, rate in metrics.get("missing_rates", {}).items()
        if rate is not None and rate > 0.1 and column in (rule.dimensions if rule else ())
    }
    if high_missing:
        result["warnings"].append({"high_dimension_missing_rates": high_missing})
    result["failures"] = sorted(set(result["failures"]))
    result["status"] = "failed" if result["failures"] else "passed_with_warnings" if result["warnings"] else "passed"
    return result


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Public-data quality audit",
        "",
        f"Captured: `{report['captured_utc']}`",
        "",
        f"Hard-gate status: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "## Summary",
        "",
        f"- Manifest artifacts: {summary['artifacts']}.",
        f"- Passed: {summary['passed_artifacts']}.",
        f"- Passed with warnings: {summary['warning_artifacts']}.",
        f"- Failed: {summary['failed_artifacts']}.",
        f"- Rows value-profiled: {summary['rows_scanned']:,}.",
        f"- Bundle bytes hash-checked: {summary['bytes_checked']:,}.",
        f"- Known scope limitations: {summary['known_scope_limitations']}.",
        "",
        "## Artifacts",
        "",
        "| Artifact | Status | Rows scanned | Failures | Warnings |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for artifact in report["artifacts"]:
        warning_text = "; ".join(
            ", ".join(item) if isinstance(item, dict) else str(item) for item in artifact["warnings"]
        )
        lines.append(
            f"| `{artifact['key']}` | {artifact['status']} | {artifact['metrics'].get('rows_scanned') or '-'} | "
            f"{', '.join(artifact['failures']) or '-'} | {warning_text or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A pass establishes file integrity, parseability, declared schema presence, critical numeric/code",
            "and U.S.-scope validity,",
            "aggregate-grain uniqueness, positive aggregate weights, and privacy-minimized column exclusion for this",
            "retained bundle. It does not remove the source-specific sampling and representativeness limitations",
            "below.",
            "",
            "## Known source limitations",
            "",
        ]
    )
    for limitation in report["known_limitations"]:
        lines.append(f"- **{limitation['category_title']}**: {limitation['limitation']}")
    lines.append("")
    return "\n".join(lines)


def audit(full_scan: bool = True) -> dict[str, Any]:
    manifest = load_manifest()
    coverage = json.loads(COVERAGE.read_text(encoding="utf-8"))
    example_coverage = json.loads(EXAMPLE_COVERAGE.read_text(encoding="utf-8"))
    artifacts = [audit_artifact(row, full_scan) for row in manifest]
    coverage_by_key = {item["key"]: item for item in coverage.get("sources", [])}
    for artifact in artifacts:
        coverage_row = coverage_by_key.get(artifact["key"])
        if coverage_row is None:
            continue
        expected = int(coverage_row["record_count"])
        metrics = artifact["metrics"]
        if coverage_row.get("count_method") == "csv_rows_minus_header":
            observed = metrics.get("rows_scanned")
        else:
            observed = metrics.get("weight_total")
            if observed is None:
                observed = metrics.get("rows_scanned")
        matches = observed is not None and int(observed) == expected
        metrics["coverage_record_count"] = expected
        metrics["record_count_matches_coverage"] = matches if full_scan else None
        if full_scan and not matches:
            artifact["failures"] = sorted({*artifact["failures"], "coverage_count_mismatch"})
            artifact["status"] = "failed"
    limitations = [
        {
            "category_key": item["category_key"],
            "category_title": item["category_title"],
            "limitation": item["limitation"],
        }
        for item in example_coverage["categories"]
    ]
    failed = [artifact for artifact in artifacts if artifact["status"] == "failed"]
    return {
        "schema_version": 1,
        "captured_utc": datetime.now(UTC).isoformat(),
        "passed": not failed
        and bool(coverage.get("summary", {}).get("passed"))
        and example_coverage.get("status") == "passed",
        "scan_scope": "full" if full_scan else "first-10000-per-delimited-artifact",
        "summary": {
            "artifacts": len(artifacts),
            "passed_artifacts": sum(item["status"] == "passed" for item in artifacts),
            "warning_artifacts": sum(item["status"] == "passed_with_warnings" for item in artifacts),
            "failed_artifacts": len(failed),
            "rows_scanned": sum(item["metrics"].get("rows_scanned") or 0 for item in artifacts),
            "bytes_checked": sum(item.get("integrity", {}).get("actual_bytes", 0) for item in artifacts),
            "coverage_gate_passed": bool(coverage.get("summary", {}).get("passed")),
            "example_gate_passed": example_coverage.get("status") == "passed",
            "known_scope_limitations": len(limitations),
        },
        "artifacts": artifacts,
        "known_limitations": limitations,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit retained public calibration data quality and fitness.")
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-report", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    parser.add_argument(
        "--sample", action="store_true", help="Scan at most the first 10,000 rows per delimited artifact."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit(full_scan=not args.sample)
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_report.write_text(markdown_report(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "artifacts": report["summary"]["artifacts"],
                "rows_scanned": report["summary"]["rows_scanned"],
                "failed_artifacts": report["summary"]["failed_artifacts"],
                "report": str(args.json_report),
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

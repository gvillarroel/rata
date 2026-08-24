"""Generate small, privacy-safe examples for every public-data source category.

The full bundle under ``datasets/public-data`` is ignored by Git. This script reads
the downloaded artifacts, requests two small official gap examples, writes one CSV
example per source, and verifies complete coverage of the source manifest and the
11 categories requested in the email ``public data to find``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "datasets" / "public-data"
SOURCE_MANIFEST = BUNDLE_DIR / "manifest.csv"
EXAMPLES_DIR = BUNDLE_DIR / "examples"
CATALOG_PATH = EXAMPLES_DIR / "catalog.csv"
CATEGORY_SUMMARY_PATH = EXAMPLES_DIR / "category-summary.csv"
COVERAGE_JSON_PATH = EXAMPLES_DIR / "coverage-report.json"
COVERAGE_MARKDOWN_PATH = EXAMPLES_DIR / "coverage-report.md"
LINKS_PATH = EXAMPLES_DIR / "download-links.txt"

EXAMPLE_LIMIT = 5
READ_CHUNK_SIZE = 100_000
USER_AGENT = "rata-public-data-research/1.0 (+https://github.com/gvillarroel/rata)"
USASPENDING_API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
USASPENDING_LANDING_PAGE = "https://api.usaspending.gov/docs/endpoints"
SAM_PUBLIC_EXTRACT_PAGE = "https://sam.gov/data-services/Entity%20Management/Public%20Extract"
USCOURTS_BANKRUPTCY_URL = "https://www.uscourts.gov/sites/default/files/document/stfj_f2_630.2026.xlsx"
USCOURTS_BANKRUPTCY_PAGE = "https://www.uscourts.gov/data-table-topics/bankruptcy"

XML_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DISALLOWED_EXAMPLE_COLUMNS = {
    "address",
    "address_line1",
    "borrower_name",
    "duns",
    "email",
    "guarantor",
    "lender_name",
    "loan_number",
    "npi",
    "owner",
    "phone",
    "ssn",
    "street",
    "tax_id",
    "uei",
}


@dataclass(frozen=True)
class Category:
    key: str
    title: str
    requested_scope: str
    limitation: str


CATEGORIES = (
    Category(
        "business_population",
        "Business population and distributions",
        "NAICS, employees, sales/receipts, geography, business size, births, and deaths.",
        "Published aggregates describe relationships, not identifiable establishments.",
    ),
    Category(
        "employment_wages",
        "Employment and wages",
        "Employment, establishments, payroll, and wages by industry and geography.",
        "QCEW suppression codes still apply to detailed cells.",
    ),
    Category(
        "industry_validity",
        "Industry-code validity",
        "Official NAICS and SIC code/description references.",
        "SIC is historical; NAICS should be the primary current classification.",
    ),
    Category(
        "addresses_geography",
        "Addresses and geography",
        "Valid state/county/place/ZCTA relationships and representative coordinates.",
        "Gazetteer coordinates are representative points, not street addresses.",
    ),
    Category(
        "business_names_formation",
        "Business names and formation",
        "Entity type, status, formation year, province/state, and legal-name patterns.",
        "Examples are aggregate Iowa/Canada distributions; names and identifiers were removed.",
    ),
    Category(
        "federal_contractors",
        "Federal contractors",
        "Public contractor name, NAICS, geography, agency, award type, and amount relationships.",
        "USAspending award examples partially cover the target; the complete SAM entity extract is separately linked.",
    ),
    Category(
        "public_companies",
        "Public companies",
        "SEC company, ticker, and exchange associations.",
        "The compact SEC ticker file is partial and is not a complete EDGAR issuer population.",
    ),
    Category(
        "historical_small_business",
        "Historical small-business program data",
        "PPP state, NAICS, jobs, business profile, rural/urban, and loan-size relationships.",
        "PPP above $150K is a biased historical program sample, not a current business population.",
    ),
    Category(
        "transportation",
        "Transportation businesses",
        "Carrier status, operation, organization type, geography, and fleet size.",
        "The retained FMCSA artifact is a server-side aggregate without carrier identifiers.",
    ),
    Category(
        "healthcare",
        "Healthcare organizations",
        "Type-2 organization taxonomy, state, enumeration year, and status.",
        "The retained NPPES distribution is a weekly incremental sample, not the full population.",
    ),
    Category(
        "public_records",
        "Public records",
        "Bankruptcy filing counts by district, business/nonbusiness nature, and chapter.",
        "This aggregate example covers bankruptcy only; liens, judgments, and UCC records remain state-specific.",
    ),
    Category(
        "realism_calibration",
        "Privacy-safe realism calibration",
        "Aggregate name, road-component, postal-suffix, business-token, and narrative-language distributions.",
        "Component distributions improve surface realism but do not preserve source pairings or establish semantics.",
    ),
)
CATEGORY_BY_KEY = {category.key: category for category in CATEGORIES}

SOURCE_CATEGORY = {
    "census_cbp_state_2023": "business_population",
    "census_cbp_county_2023": "business_population",
    "census_zbp_detail_2023": "business_population",
    "census_nes_state_2022": "business_population",
    "census_nes_county_2022": "business_population",
    "census_abs_company_summary_2023": "business_population",
    "census_bds_state_firm_size_2023": "business_population",
    "bls_qcew_annual_singlefile_2025": "employment_wages",
    "census_naics_2022_descriptions": "industry_validity",
    "census_sic_descriptions": "industry_validity",
    "census_gazetteer_counties_2025": "addresses_geography",
    "census_gazetteer_places_2025": "addresses_geography",
    "census_gazetteer_zcta_2025": "addresses_geography",
    "iowa_business_registry_distribution": "business_names_formation",
    "iowa_legal_name_pattern_distribution": "business_names_formation",
    "canada_corporations_distribution": "business_names_formation",
    "canada_legal_name_pattern_distribution": "business_names_formation",
    "usaspending_contract_awards_fy2025": "federal_contractors",
    "sec_company_tickers_exchange": "public_companies",
    "sba_ppp_data_dictionary": "historical_small_business",
    "sba_ppp_by_state_naics_distribution": "historical_small_business",
    "sba_ppp_business_profile_distribution": "historical_small_business",
    "fmcsa_company_census_distribution": "transportation",
    "cms_nppes_type2_weekly_distribution": "healthcare",
    "uscourts_bankruptcy_f2_2026_06": "public_records",
    "census_surnames_2010": "realism_calibration",
    "nyc_popular_baby_names": "realism_calibration",
    "usps_publication_28_suffixes": "realism_calibration",
    "tiger_roads_los_angeles_2025": "realism_calibration",
    "tiger_roads_cook_2025": "realism_calibration",
    "tiger_roads_suffolk_ma_2025": "realism_calibration",
    "tiger_roads_new_york_2025": "realism_calibration",
    "tiger_roads_harris_2025": "realism_calibration",
    "tiger_roads_king_2025": "realism_calibration",
    "census_surname_distribution": "realism_calibration",
    "nyc_given_name_distribution": "realism_calibration",
    "usps_street_suffix_reference": "realism_calibration",
    "tiger_street_name_distribution": "realism_calibration",
    "tiger_street_suffix_distribution": "realism_calibration",
    "sec_business_name_token_distribution": "realism_calibration",
    "cfpb_narrative_token_distribution": "realism_calibration",
    "cfpb_narrative_length_distribution": "realism_calibration",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _normalize(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _records(frame: pd.DataFrame, columns: list[str], limit: int = EXAMPLE_LIMIT) -> list[dict[str, str]]:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise RuntimeError(f"Example columns missing: {missing}")
    output = [
        {column: _normalize(value) for column, value in zip(columns, row, strict=True)}
        for row in frame.loc[:, columns].head(limit).itertuples(index=False, name=None)
    ]
    if not output:
        raise RuntimeError("Example selector returned no rows")
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write an empty example: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    if any(list(row) != fields for row in rows):
        raise RuntimeError(f"Inconsistent columns in {path.name}")
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_manifest() -> dict[str, dict[str, str]]:
    if not SOURCE_MANIFEST.exists():
        raise RuntimeError(f"Source manifest does not exist: {SOURCE_MANIFEST}")
    with SOURCE_MANIFEST.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise RuntimeError("Source manifest has no rows")
    return {row["key"]: row for row in rows}


def _zip_member(path: Path, suffix: str, excluded: tuple[str, ...] = ()) -> tuple[zipfile.ZipFile, Any]:
    archive = zipfile.ZipFile(path)
    candidates = [
        name
        for name in archive.namelist()
        if name.lower().endswith(suffix.lower()) and not any(token.lower() in name.lower() for token in excluded)
    ]
    if not candidates:
        archive.close()
        raise RuntimeError(f"No {suffix} member found in {path}")
    member_name = max(candidates, key=lambda name: archive.getinfo(name).file_size)
    return archive, archive.open(member_name)


def _read_zip_table(
    path: Path,
    *,
    suffix: str,
    sep: str = ",",
    encoding: str = "utf-8",
    nrows: int = READ_CHUNK_SIZE,
    excluded: tuple[str, ...] = (),
) -> pd.DataFrame:
    archive, member = _zip_member(path, suffix, excluded)
    try:
        return pd.read_csv(
            member,
            sep=sep,
            dtype="string",
            encoding=encoding,
            encoding_errors="replace",
            keep_default_na=False,
            nrows=nrows,
        )
    finally:
        member.close()
        archive.close()


def _sample_cbp_state(path: Path) -> list[dict[str, str]]:
    frame = _read_zip_table(path, suffix=".txt", encoding="latin-1")
    frame = frame.loc[frame["naics"].str.fullmatch(r"\d{6}") & frame["lfo"].eq("-")]
    return _records(frame, ["fipstate", "naics", "lfo", "emp", "qp1", "ap", "est", "n<5", "n5_9", "n10_19"])


def _sample_cbp_county(path: Path) -> list[dict[str, str]]:
    frame = _read_zip_table(path, suffix=".txt", encoding="latin-1")
    frame = frame.loc[frame["naics"].str.fullmatch(r"\d{6}")]
    return _records(
        frame,
        ["fipstate", "fipscty", "naics", "emp", "qp1", "ap", "est", "n<5", "n5_9", "n10_19"],
    )


def _sample_zbp(path: Path) -> list[dict[str, str]]:
    frame = _read_zip_table(path, suffix=".txt", encoding="latin-1")
    frame = frame.loc[frame["naics"].str.fullmatch(r"\d{6}")]
    return _records(
        frame,
        ["zip", "city", "stabbr", "cty_name", "naics", "est", "n<5", "n5_9", "n10_19", "n20_49"],
    )


def _sample_nes_state(path: Path) -> list[dict[str, str]]:
    frame = _read_zip_table(path, suffix=".txt", encoding="latin-1")
    frame = frame.loc[frame["NAICS"].str.fullmatch(r"\d{6}") & frame["LFO"].eq("-")]
    return _records(frame, ["ST", "NAICS", "LFO", "ESTAB", "RCPTOT"])


def _sample_nes_county(path: Path) -> list[dict[str, str]]:
    frame = _read_zip_table(path, suffix=".txt", encoding="latin-1")
    frame = frame.loc[frame["NAICS"].str.fullmatch(r"\d{6}")]
    return _records(frame, ["ST", "CTY", "NAICS", "ESTAB", "RCPTOT"])


def _sample_abs(path: Path) -> list[dict[str, str]]:
    frame = _read_zip_table(
        path,
        suffix=".dat",
        sep="|",
        encoding="latin-1",
        nrows=10_000,
        excluded=("fields", "readme"),
    )
    frame = frame.loc[frame["#GEO_ID"].eq("0100000US") & frame["NAICS2022"].eq("00") & frame["YEAR"].eq("2023")]
    return _records(
        frame,
        [
            "GEO_LABEL",
            "NAICS2022",
            "SEX_LABEL",
            "ETH_GROUP_LABEL",
            "RACE_GROUP_LABEL",
            "VET_GROUP_LABEL",
            "FIRMPDEMP",
            "RCPPDEMP",
            "EMP",
            "PAYANN",
        ],
    )


def _sample_bds(path: Path) -> list[dict[str, str]]:
    frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    latest_year = frame["year"].max()
    frame = frame.loc[frame["year"].eq(latest_year)]
    return _records(
        frame,
        [
            "year",
            "st",
            "fsize",
            "firms",
            "estabs",
            "emp",
            "estabs_entry",
            "estabs_exit",
            "job_creation",
            "job_destruction",
            "firmdeath_firms",
        ],
    )


def _sample_qcew(path: Path) -> list[dict[str, str]]:
    columns = [
        "area_fips",
        "own_code",
        "industry_code",
        "year",
        "annual_avg_estabs",
        "annual_avg_emplvl",
        "total_annual_wages",
        "annual_avg_wkly_wage",
        "avg_annual_pay",
        "disclosure_code",
    ]
    selected: list[pd.DataFrame] = []
    archive, member = _zip_member(path, ".csv")
    try:
        for chunk in pd.read_csv(
            member,
            usecols=columns,
            dtype="string",
            keep_default_na=False,
            chunksize=READ_CHUNK_SIZE,
        ):
            match = chunk.loc[
                chunk["own_code"].eq("5")
                & chunk["industry_code"].str.fullmatch(r"\d{6}")
                & chunk["disclosure_code"].eq("")
            ]
            if not match.empty:
                selected.append(match)
            if sum(len(part) for part in selected) >= EXAMPLE_LIMIT:
                break
    finally:
        member.close()
        archive.close()
    if not selected:
        raise RuntimeError("No unsuppressed private six-digit QCEW rows found")
    frame = pd.concat(selected, ignore_index=True)
    return _records(frame, [column for column in columns if column != "disclosure_code"])


def _sample_naics(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="latin-1", errors="replace").splitlines():
        match = re.match(r"^(\d{2,6})\s+(.+)$", line.strip())
        if match and match.group(1) != "00":
            rows.append({"naics_code": match.group(1), "description": match.group(2).strip()})
        if len(rows) == EXAMPLE_LIMIT:
            break
    if not rows:
        raise RuntimeError("No NAICS examples parsed")
    return rows


def _sample_sic(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="latin-1", errors="replace").splitlines():
        match = re.match(r"^\s*(\d{4})\s{2,}(.+)$", line)
        if match:
            rows.append({"sic_code": match.group(1), "description": match.group(2).strip()})
        if len(rows) == EXAMPLE_LIMIT:
            break
    if not rows:
        raise RuntimeError("No SIC examples parsed")
    return rows


def _sample_gazetteer(path: Path, columns: list[str]) -> list[dict[str, str]]:
    frame = _read_zip_table(path, suffix=".txt", sep="|", encoding="utf-8", nrows=EXAMPLE_LIMIT)
    frame.columns = [column.strip() for column in frame.columns]
    return _records(frame, columns)


def _sample_fmcsa(path: Path) -> list[dict[str, str]]:
    frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    frame["_records"] = pd.to_numeric(frame["records"], errors="coerce")
    frame = frame.sort_values("_records", ascending=False)
    return _records(
        frame,
        ["phy_country", "phy_state", "status_code", "carrier_operation", "business_org_desc", "fleetsize", "records"],
    )


def _sample_sec(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(payload["data"], columns=payload["fields"], dtype="string")
    return _records(frame, ["cik", "name", "ticker", "exchange"])


def _column_index(reference: str) -> int:
    match = re.match(r"^[A-Z]+", reference)
    if not match:
        raise ValueError(f"Invalid spreadsheet cell reference: {reference}")
    index = 0
    for character in match.group():
        index = index * 26 + ord(character) - ord("A") + 1
    return index - 1


def _read_xlsx_rows(data: bytes | Path, sheet_name: str = "xl/worksheets/sheet1.xml") -> list[list[str]]:
    source: io.BytesIO | Path = io.BytesIO(data) if isinstance(data, bytes) else data
    with zipfile.ZipFile(source) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(f"{XML_NAMESPACE}si"):
                shared_strings.append("".join(node.text or "" for node in item.iter(f"{XML_NAMESPACE}t")))

        sheet_root = ElementTree.fromstring(archive.read(sheet_name))
        output: list[list[str]] = []
        for row in sheet_root.iter(f"{XML_NAMESPACE}row"):
            values: dict[int, str] = {}
            for cell in row.findall(f"{XML_NAMESPACE}c"):
                reference = cell.get("r", "")
                index = _column_index(reference)
                cell_type = cell.get("t")
                value_node = cell.find(f"{XML_NAMESPACE}v")
                if cell_type == "inlineStr":
                    inline = cell.find(f"{XML_NAMESPACE}is")
                    value = (
                        "" if inline is None else "".join(node.text or "" for node in inline.iter(f"{XML_NAMESPACE}t"))
                    )
                elif value_node is None or value_node.text is None:
                    value = ""
                elif cell_type == "s":
                    value = shared_strings[int(value_node.text)]
                else:
                    value = value_node.text
                values[index] = value.strip()
            width = max(values, default=-1) + 1
            output.append([values.get(index, "") for index in range(width)])
    return output


def _sample_ppp_dictionary(path: Path) -> list[dict[str, str]]:
    rows = _read_xlsx_rows(path)
    table = {row[0]: row[1] for row in rows[1:] if len(row) >= 2 and row[0]}
    fields = ["NAICSCode", "BusinessType", "BusinessAgeDescription", "RuralUrbanIndicator", "JobsReported"]
    missing = sorted(set(fields) - set(table))
    if missing:
        raise RuntimeError(f"PPP dictionary fields missing: {missing}")
    return [{"field_name": field, "field_description": table[field]} for field in fields]


def _sample_distribution(
    path: Path,
    columns: list[str],
    metric: str,
    required_dimensions: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    for dimension in required_dimensions:
        frame = frame.loc[frame[dimension].str.strip().ne("")]
    frame["_metric"] = pd.to_numeric(frame[metric], errors="coerce")
    frame = frame.sort_values("_metric", ascending=False)
    return _records(frame, columns)


def _sample_census_surnames(path: Path) -> list[dict[str, str]]:
    frame = _read_zip_table(path, suffix=".csv", encoding="utf-8")
    frame.columns = [column.lower() for column in frame.columns]
    return _records(frame, ["name", "rank", "count"])


def _sample_nyc_names(path: Path) -> list[dict[str, str]]:
    frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    frame["_count"] = pd.to_numeric(frame["cnt"], errors="coerce")
    frame = frame.sort_values("_count", ascending=False)
    return _records(frame, ["brth_yr", "gndr", "ethcty", "nm", "cnt", "rnk"])


def _sample_usps_suffixes(path: Path) -> list[dict[str, str]]:
    document = path.read_text(encoding="utf-8", errors="replace")
    rows: list[dict[str, str]] = []
    for raw_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", document, flags=re.IGNORECASE | re.DOTALL):
        cells = [
            " ".join(html.unescape(re.sub(r"<[^>]+>", " ", cell)).split())
            for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", raw_row, flags=re.IGNORECASE | re.DOTALL)
        ]
        if len(cells) >= 3 and cells[0].isupper() and cells[-1].isupper():
            rows.append(
                {
                    "primary_suffix": cells[0],
                    "common_suffix": cells[-2],
                    "standard_suffix": cells[-1],
                }
            )
        if len(rows) == EXAMPLE_LIMIT:
            break
    if not rows:
        raise RuntimeError("No USPS suffix rows parsed")
    return rows


def _sample_tiger_roads(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".dbf")]
        if not members:
            raise RuntimeError(f"No DBF member found in {path}")
        with archive.open(members[0]) as source:
            header = source.read(32)
            record_count = int.from_bytes(header[4:8], "little")
            header_length = int.from_bytes(header[8:10], "little")
            record_length = int.from_bytes(header[10:12], "little")
            descriptors = source.read(header_length - 33)
            source.read(1)
            fields: list[tuple[str, int]] = []
            for offset in range(0, len(descriptors), 32):
                descriptor = descriptors[offset : offset + 32]
                if len(descriptor) < 32 or descriptor[0] == 0x0D:
                    break
                name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", "replace").strip()
                fields.append((name, descriptor[16]))
            rows: list[dict[str, str]] = []
            for _index in range(record_count):
                raw = source.read(record_length)
                if len(raw) != record_length:
                    break
                cursor = 1
                record: dict[str, str] = {}
                for name, length in fields:
                    record[name] = raw[cursor : cursor + length].decode("latin-1", "replace").strip()
                    cursor += length
                if raw[:1] != b"*" and record.get("FULLNAME"):
                    rows.append(
                        {
                            "road_feature_name": record["FULLNAME"],
                            "feature_class": record.get("MTFCC", ""),
                            "route_type": record.get("RTTYP", ""),
                        }
                    )
                if len(rows) == EXAMPLE_LIMIT:
                    break
    if not rows:
        raise RuntimeError("No named TIGER roads found")
    return rows


LOCAL_SAMPLERS: dict[str, Callable[[Path], list[dict[str, str]]]] = {
    "census_cbp_state_2023": _sample_cbp_state,
    "census_cbp_county_2023": _sample_cbp_county,
    "census_zbp_detail_2023": _sample_zbp,
    "census_nes_state_2022": _sample_nes_state,
    "census_nes_county_2022": _sample_nes_county,
    "census_abs_company_summary_2023": _sample_abs,
    "census_bds_state_firm_size_2023": _sample_bds,
    "bls_qcew_annual_singlefile_2025": _sample_qcew,
    "census_naics_2022_descriptions": _sample_naics,
    "census_sic_descriptions": _sample_sic,
    "census_gazetteer_counties_2025": lambda path: _sample_gazetteer(
        path, ["USPS", "GEOID", "NAME", "ALAND_SQMI", "AWATER_SQMI", "INTPTLAT", "INTPTLONG"]
    ),
    "census_gazetteer_places_2025": lambda path: _sample_gazetteer(
        path, ["USPS", "GEOID", "NAME", "LSAD", "FUNCSTAT", "INTPTLAT", "INTPTLONG"]
    ),
    "census_gazetteer_zcta_2025": lambda path: _sample_gazetteer(
        path, ["GEOID", "ALAND_SQMI", "AWATER_SQMI", "INTPTLAT", "INTPTLONG"]
    ),
    "fmcsa_company_census_distribution": _sample_fmcsa,
    "sec_company_tickers_exchange": _sample_sec,
    "sba_ppp_data_dictionary": _sample_ppp_dictionary,
    "iowa_business_registry_distribution": lambda path: _sample_distribution(
        path,
        ["corporation_type", "effective_year", "home_office_state", "home_office_country", "records"],
        "records",
        ("corporation_type", "effective_year", "home_office_state", "home_office_country"),
    ),
    "iowa_legal_name_pattern_distribution": lambda path: _sample_distribution(
        path, ["corporation_type", "legal_suffix", "records"], "records", ("corporation_type", "legal_suffix")
    ),
    "canada_corporations_distribution": lambda path: _sample_distribution(
        path,
        ["governing_legislation", "status", "status_detail", "effective_year", "province", "country", "records"],
        "records",
        ("status", "effective_year", "province", "country"),
    ),
    "canada_legal_name_pattern_distribution": lambda path: _sample_distribution(
        path, ["status", "legal_suffix", "records"], "records", ("status", "legal_suffix")
    ),
    "cms_nppes_type2_weekly_distribution": lambda path: _sample_distribution(
        path,
        ["practice_state", "taxonomy_code", "enumeration_year", "last_update_year", "is_deactivated", "records"],
        "records",
        ("practice_state", "taxonomy_code", "enumeration_year"),
    ),
    "sba_ppp_by_state_naics_distribution": lambda path: _sample_distribution(
        path,
        ["borrower_state", "naics_code", "loans", "total_approval", "jobs_reported", "jobs_nonnull"],
        "loans",
        ("borrower_state", "naics_code"),
    ),
    "sba_ppp_business_profile_distribution": lambda path: _sample_distribution(
        path,
        ["business_type", "business_age", "rural_urban", "loan_size_band", "jobs_band", "loans", "total_approval"],
        "loans",
        ("business_type", "business_age", "rural_urban", "loan_size_band", "jobs_band"),
    ),
    "census_surnames_2010": _sample_census_surnames,
    "nyc_popular_baby_names": _sample_nyc_names,
    "usps_publication_28_suffixes": _sample_usps_suffixes,
    "tiger_roads_los_angeles_2025": _sample_tiger_roads,
    "tiger_roads_cook_2025": _sample_tiger_roads,
    "tiger_roads_suffolk_ma_2025": _sample_tiger_roads,
    "tiger_roads_new_york_2025": _sample_tiger_roads,
    "tiger_roads_harris_2025": _sample_tiger_roads,
    "tiger_roads_king_2025": _sample_tiger_roads,
    "census_surname_distribution": lambda path: _sample_distribution(
        path, ["surname", "records", "rank"], "records", ("surname",)
    ),
    "nyc_given_name_distribution": lambda path: _sample_distribution(
        path,
        ["given_name", "sex", "records", "first_year", "last_year"],
        "records",
        ("given_name", "sex"),
    ),
    "usps_street_suffix_reference": lambda path: _sample_distribution(
        path, ["source_suffix", "standard_suffix"], "source_suffix", ("source_suffix", "standard_suffix")
    ),
    "tiger_street_name_distribution": lambda path: _sample_distribution(
        path, ["street_name", "records"], "records", ("street_name",)
    ),
    "tiger_street_suffix_distribution": lambda path: _sample_distribution(
        path, ["standard_suffix", "records"], "records", ("standard_suffix",)
    ),
    "sec_business_name_token_distribution": lambda path: _sample_distribution(
        path, ["token", "records", "document_frequency"], "records", ("token",)
    ),
    "cfpb_narrative_token_distribution": lambda path: _sample_distribution(
        path, ["token", "records", "document_frequency"], "records", ("token",)
    ),
    "cfpb_narrative_length_distribution": lambda path: _sample_distribution(
        path, ["word_count_band", "records"], "records", ("word_count_band",)
    ),
}


def _urlopen(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def _fetch_usaspending_examples() -> list[dict[str, str]]:
    payload = {
        "filters": {
            "time_period": [{"start_date": "2024-10-01", "end_date": "2025-09-30"}],
            "award_type_codes": ["A", "B", "C", "D"],
            "recipient_scope": "domestic",
        },
        "fields": [
            "Recipient Name",
            "Recipient Location",
            "NAICS",
            "Contract Award Type",
            "Award Amount",
            "Awarding Agency",
        ],
        "page": 1,
        "limit": 50,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }
    request = urllib.request.Request(
        USASPENDING_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    response = json.loads(_urlopen(request))

    return _extract_usaspending_examples(response.get("results", []))


def _extract_usaspending_examples(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    for row in results:
        location = row.get("Recipient Location") or {}
        naics = row.get("NAICS") or {}
        if not row.get("Recipient Name") or not naics.get("code") or not location.get("state_code"):
            continue
        examples.append(
            {
                "recipient_name": _normalize(row.get("Recipient Name")),
                "recipient_city": _normalize(location.get("city_name")),
                "recipient_state": _normalize(location.get("state_code")),
                "naics_code": _normalize(naics.get("code")),
                "naics_description": _normalize(naics.get("description")),
                "contract_award_type": _normalize(row.get("Contract Award Type")),
                "award_amount_usd": _normalize(row.get("Award Amount")),
                "awarding_agency": _normalize(row.get("Awarding Agency")),
            }
        )
        if len(examples) == EXAMPLE_LIMIT:
            break
    if len(examples) < EXAMPLE_LIMIT:
        raise RuntimeError(f"USAspending returned only {len(examples)} usable contract examples")
    return examples


def _extract_bankruptcy_examples(rows: list[list[str]]) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    for row in rows:
        if len(row) < 15:
            continue
        region = row[0].strip()
        is_district = bool(re.fullmatch(r"[A-Z]{2}(?:,[A-Z])?", region))
        if region != "Total" and not is_district:
            continue
        examples.append(
            {
                "circuit_or_district": region,
                "total_all_chapters": row[1],
                "business_all_chapters": row[6],
                "business_chapter_7": row[7],
                "business_chapter_11": row[8],
                "business_chapter_13": row[9],
                "nonbusiness_all_chapters": row[11],
            }
        )
        if len(examples) == EXAMPLE_LIMIT:
            break
    if len(examples) < EXAMPLE_LIMIT:
        raise RuntimeError(f"U.S. Courts workbook yielded only {len(examples)} usable rows")
    return examples


def _fetch_bankruptcy_examples() -> list[dict[str, str]]:
    request = urllib.request.Request(
        USCOURTS_BANKRUPTCY_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
    )
    return _extract_bankruptcy_examples(_read_xlsx_rows(_urlopen(request)))


def _read_example(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _external_rows(offline: bool) -> dict[str, list[dict[str, str]]]:
    paths = {
        "usaspending_contract_awards_fy2025": EXAMPLES_DIR / "usaspending_contract_awards_fy2025.csv",
        "uscourts_bankruptcy_f2_2026_06": EXAMPLES_DIR / "uscourts_bankruptcy_f2_2026_06.csv",
    }
    if offline:
        missing = [path for path in paths.values() if not path.exists()]
        if missing:
            raise RuntimeError(f"Offline mode requires cached external examples: {missing}")
        return {key: _read_example(path) for key, path in paths.items()}
    return {
        "usaspending_contract_awards_fy2025": _fetch_usaspending_examples(),
        "uscourts_bankruptcy_f2_2026_06": _fetch_bankruptcy_examples(),
    }


def _external_metadata(now: str) -> dict[str, dict[str, str]]:
    return {
        "usaspending_contract_awards_fy2025": {
            "key": "usaspending_contract_awards_fy2025",
            "title": "USAspending contract award examples — FY2025",
            "vintage": "FY2025 query",
            "source_url": USASPENDING_API_URL,
            "landing_page": USASPENDING_LANDING_PAGE,
            "privacy_transform": (
                "Kept public recipient business name, city/state, NAICS, award type/amount, and agency; removed award, "
                "recipient, street-address, UEI, DUNS, and contact identifiers."
            ),
            "accessed_at_utc": now,
        },
        "uscourts_bankruptcy_f2_2026_06": {
            "key": "uscourts_bankruptcy_f2_2026_06",
            "title": "U.S. Courts Table F-2 bankruptcy aggregates — June 2026",
            "vintage": "12 months ending 2026-06-30",
            "source_url": USCOURTS_BANKRUPTCY_URL,
            "landing_page": USCOURTS_BANKRUPTCY_PAGE,
            "privacy_transform": (
                "Kept district-level aggregate filing counts only; no case, debtor, business, or person identifiers."
            ),
            "accessed_at_utc": now,
        },
    }


def _coverage_note(category_key: str) -> str:
    if category_key == "federal_contractors":
        return "Partial proxy: public contract awards; SAM public entity extract linked separately."
    if category_key == "public_records":
        return "Partial aggregate: bankruptcy only; no liens, judgments, UCC records, or case-level data."
    if category_key == "business_names_formation":
        return "Partial geography: aggregate Iowa and federal-Canada corporate distributions."
    if category_key == "healthcare":
        return "Partial time window: weekly incremental Type-2 NPPES distribution."
    if category_key == "public_companies":
        return "Partial compact SEC ticker/exchange association file."
    if category_key == "historical_small_business":
        return "Biased historical PPP sample above $150K; calibration use only."
    return "Direct official aggregate/reference example."


def _catalog_row(metadata: dict[str, str], path: Path, rows: int, now: str) -> dict[str, Any]:
    source_key = metadata["key"]
    category = CATEGORY_BY_KEY[SOURCE_CATEGORY[source_key]]
    return {
        "category_key": category.key,
        "category_title": category.title,
        "source_key": source_key,
        "source_title": metadata["title"],
        "vintage": metadata["vintage"],
        "example_path": path.relative_to(ROOT).as_posix(),
        "example_rows": rows,
        "sha256": _sha256(path),
        "source_url": metadata["source_url"],
        "landing_page": metadata["landing_page"],
        "coverage_note": _coverage_note(category.key),
        "privacy_transform": metadata["privacy_transform"],
        "generated_at_utc": now,
    }


def _write_catalog(rows: list[dict[str, Any]]) -> None:
    with CATALOG_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _build_category_summary(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for category in CATEGORIES:
        matches = [row for row in catalog if row["category_key"] == category.key]
        summary.append(
            {
                "category_key": category.key,
                "category_title": category.title,
                "status": "covered" if matches else "missing",
                "example_sources": len(matches),
                "example_rows": sum(int(row["example_rows"]) for row in matches),
                "requested_scope": category.requested_scope,
                "limitation": category.limitation,
            }
        )
    return summary


def _write_summary(rows: list[dict[str, Any]]) -> None:
    with CATEGORY_SUMMARY_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_links(catalog: list[dict[str, Any]]) -> None:
    with LINKS_PATH.open("w", encoding="utf-8", newline="") as output:
        for row in catalog:
            output.write(f"{row['category_title']} — {row['source_title']}\n")
            output.write(f"Official source: {row['source_url']}\n")
            output.write(f"Local example: {row['example_path']}\n\n")
        output.write("Federal contractor registry — SAM.gov Public Entity Extract\n")
        output.write(f"Official landing page: {SAM_PUBLIC_EXTRACT_PAGE}\n")


def _validate_example_headers(path: Path) -> None:
    with path.open("r", encoding="utf-8", newline="") as source:
        header = next(csv.reader(source), [])
    normalized = {column.strip().lower() for column in header}
    forbidden = sorted(normalized & DISALLOWED_EXAMPLE_COLUMNS)
    if forbidden:
        raise RuntimeError(f"Privacy-forbidden example columns in {path.name}: {forbidden}")


def _validate_catalog(catalog: list[dict[str, Any]], source_manifest: dict[str, dict[str, str]]) -> dict[str, Any]:
    expected_local = set(source_manifest)
    configured_local = set(LOCAL_SAMPLERS)
    if expected_local != configured_local:
        raise RuntimeError(
            "Local example/source-manifest mismatch: "
            f"missing samplers={sorted(expected_local - configured_local)}, "
            f"unmanifested samplers={sorted(configured_local - expected_local)}"
        )

    expected_sources = expected_local | {"usaspending_contract_awards_fy2025", "uscourts_bankruptcy_f2_2026_06"}
    actual_sources = {row["source_key"] for row in catalog}
    if expected_sources != actual_sources:
        raise RuntimeError(
            f"Example catalog mismatch: missing={sorted(expected_sources - actual_sources)}, "
            f"unexpected={sorted(actual_sources - expected_sources)}"
        )
    if len(actual_sources) != len(catalog):
        raise RuntimeError("Example catalog contains duplicate source keys")

    expected_categories = set(CATEGORY_BY_KEY)
    actual_categories = {row["category_key"] for row in catalog}
    if expected_categories != actual_categories:
        raise RuntimeError(
            f"Category coverage mismatch: missing={sorted(expected_categories - actual_categories)}, "
            f"unexpected={sorted(actual_categories - expected_categories)}"
        )

    total_rows = 0
    for row in catalog:
        path = ROOT / row["example_path"]
        resolved = path.resolve()
        if not resolved.is_relative_to(EXAMPLES_DIR.resolve()):
            raise RuntimeError(f"Example path escapes examples directory: {path}")
        records = _read_example(path)
        if len(records) != int(row["example_rows"]):
            raise RuntimeError(f"Example row-count mismatch: {path}")
        if _sha256(path) != row["sha256"]:
            raise RuntimeError(f"Example checksum mismatch: {path}")
        _validate_example_headers(path)
        total_rows += len(records)

    return {
        "status": "passed",
        "categories_covered": len(actual_categories),
        "categories_expected": len(expected_categories),
        "local_manifest_sources_covered": len(expected_local),
        "local_manifest_sources_expected": len(expected_local),
        "gap_examples": 2,
        "example_files": len(catalog),
        "example_rows": total_rows,
        "privacy_forbidden_columns_found": 0,
    }


def _write_coverage_report(validation: dict[str, Any], category_summary: list[dict[str, Any]], now: str) -> None:
    payload = {"generated_at_utc": now, **validation, "categories": category_summary}
    COVERAGE_JSON_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Public-data example coverage",
        "",
        f"Generated: **{now}**",
        "",
        f"- Status: **{validation['status']}**",
        f"- Email categories covered: **{validation['categories_covered']}/{validation['categories_expected']}**",
        "- Local manifest artifacts covered: "
        f"**{validation['local_manifest_sources_covered']}/{validation['local_manifest_sources_expected']}**",
        f"- Official gap examples: **{validation['gap_examples']}**",
        f"- Example files / rows: **{validation['example_files']} / {validation['example_rows']}**",
        f"- Privacy-forbidden columns found: **{validation['privacy_forbidden_columns_found']}**",
        "",
        "| Category | Status | Sources | Rows | Limitation |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for row in category_summary:
        lines.append(
            f"| {row['category_title']} | {row['status']} | {row['example_sources']} | "
            f"{row['example_rows']} | {row['limitation']} |"
        )
    COVERAGE_MARKDOWN_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate(offline: bool = False) -> dict[str, Any]:
    source_manifest = _read_manifest()
    now = datetime.now(UTC).isoformat()
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    catalog: list[dict[str, Any]] = []

    expected_local = set(source_manifest)
    if expected_local != set(LOCAL_SAMPLERS):
        _validate_catalog([], source_manifest)

    for source_key in source_manifest:
        metadata = source_manifest[source_key]
        source_path = ROOT / metadata["local_path"]
        if not source_path.exists():
            raise RuntimeError(f"Downloaded source artifact is missing: {source_path}")
        rows = LOCAL_SAMPLERS[source_key](source_path)
        output_path = EXAMPLES_DIR / f"{source_key}.csv"
        _write_csv(output_path, rows)
        catalog.append(_catalog_row(metadata, output_path, len(rows), now))
        print(f"[{source_key}] {len(rows)} safe example rows")

    external_metadata = _external_metadata(now)
    for source_key, rows in _external_rows(offline).items():
        output_path = EXAMPLES_DIR / f"{source_key}.csv"
        _write_csv(output_path, rows)
        catalog.append(_catalog_row(external_metadata[source_key], output_path, len(rows), now))
        print(f"[{source_key}] {len(rows)} safe example rows")

    catalog.sort(key=lambda row: (row["category_key"], row["source_key"]))
    _write_catalog(catalog)
    category_summary = _build_category_summary(catalog)
    _write_summary(category_summary)
    _write_links(catalog)
    validation = _validate_catalog(catalog, source_manifest)
    _write_coverage_report(validation, category_summary, now)
    return validation


def check() -> dict[str, Any]:
    source_manifest = _read_manifest()
    if not CATALOG_PATH.exists():
        raise RuntimeError(f"Example catalog does not exist: {CATALOG_PATH}")
    with CATALOG_PATH.open("r", encoding="utf-8", newline="") as source:
        catalog = list(csv.DictReader(source))
    validation = _validate_catalog(catalog, source_manifest)
    category_summary = _build_category_summary(catalog)
    _write_coverage_report(validation, category_summary, datetime.now(UTC).isoformat())
    return validation


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Reuse the two cached external examples.")
    parser.add_argument("--check", action="store_true", help="Validate existing examples without regenerating them.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    validation = check() if args.check else generate(offline=args.offline)
    print(
        f"Validated {validation['categories_covered']}/{validation['categories_expected']} categories, "
        f"{validation['example_files']} example files, and {validation['example_rows']} example rows"
    )
    print(f"Catalog: {CATALOG_PATH}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise

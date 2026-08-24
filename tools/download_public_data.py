"""Download and privacy-minimize public business calibration datasets.

The retained bundle lives under ``datasets/public-data`` (ignored by Git). Official
aggregate datasets are retained verbatim. Row-level registry/provider/loan files are
downloaded only to a staging directory, converted to aggregate distributions, and
removed after successful processing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = ROOT / "datasets" / "public-data"
RAW_DIR = BUNDLE_DIR / "raw"
DERIVED_DIR = BUNDLE_DIR / "derived"
STAGING_DIR = BUNDLE_DIR / ".staging"
MANIFEST_PATH = BUNDLE_DIR / "manifest.csv"
LINKS_PATH = BUNDLE_DIR / "download-links.txt"

USER_AGENT = "rata-public-data-research/1.0 (+https://github.com/gvillarroel/rata)"
CHUNK_SIZE = 100_000
DOWNLOAD_BLOCK_SIZE = 1024 * 1024
PROGRESS_INTERVAL_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    url: str
    filename: str
    landing_page: str
    vintage: str
    purpose: str
    minimum_bytes: int
    staged: bool = False
    optional: bool = False


def _fmcsa_aggregate_url() -> str:
    dimensions = [
        "phy_country",
        "phy_state",
        "status_code",
        "carrier_operation",
        "business_org_desc",
        "fleetsize",
    ]
    query = {
        "$select": ",".join(dimensions) + ",count(*) as records",
        "$group": ",".join(dimensions),
        "$order": "records desc",
        "$limit": "500000",
    }
    return "https://data.transportation.gov/resource/az4n-8mr2.csv?" + urllib.parse.urlencode(query)


SOURCES = (
    Source(
        "census_cbp_state_2023",
        "Census County Business Patterns — state",
        "https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23st.zip",
        "census_cbp_state_2023.zip",
        "https://www.census.gov/data/datasets/2023/econ/cbp/2023-cbp.html",
        "2023",
        "State × NAICS establishments, employment, payroll, legal form, and size classes.",
        10_000_000,
    ),
    Source(
        "census_cbp_county_2023",
        "Census County Business Patterns — county",
        "https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23co.zip",
        "census_cbp_county_2023.zip",
        "https://www.census.gov/data/datasets/2023/econ/cbp/2023-cbp.html",
        "2023",
        "County × NAICS establishments, employment, and payroll relationships.",
        12_000_000,
    ),
    Source(
        "census_zbp_detail_2023",
        "Census ZIP Code Business Patterns — industry detail",
        "https://www2.census.gov/programs-surveys/cbp/datasets/2023/zbp23detail.zip",
        "census_zbp_industry_detail_2023.zip",
        "https://www.census.gov/data/datasets/2023/econ/cbp/2023-cbp.html",
        "2023",
        "ZIP Code × NAICS establishment counts and employment-size distributions.",
        14_000_000,
    ),
    Source(
        "census_nes_state_2022",
        "Census Nonemployer Statistics — state",
        "https://www2.census.gov/programs-surveys/nonemployer-statistics/datasets/2022/"
        "historical-datasets/nonemp22st.zip",
        "census_nes_state_2022.zip",
        "https://www.census.gov/data/datasets/2022/econ/nonemployer-statistics/2022-ns.html",
        "2022",
        "State × NAICS nonemployer establishments and receipts.",
        600_000,
    ),
    Source(
        "census_nes_county_2022",
        "Census Nonemployer Statistics — county",
        "https://www2.census.gov/programs-surveys/nonemployer-statistics/datasets/2022/"
        "historical-datasets/nonemp22co.zip",
        "census_nes_county_2022.zip",
        "https://www.census.gov/data/datasets/2022/econ/nonemployer-statistics/2022-ns.html",
        "2022",
        "County × NAICS nonemployer establishments and receipts.",
        4_000_000,
    ),
    Source(
        "census_abs_company_summary_2023",
        "Census Annual Business Survey company summary",
        "https://www2.census.gov/programs-surveys/abs/data/2023/AB2300CSA01.zip",
        "census_abs_company_summary_2023.zip",
        "https://api.census.gov/data/2023/abscs.html",
        "2023",
        "Employer-firm characteristics by industry and geography.",
        15_000_000,
    ),
    Source(
        "census_bds_state_firm_size_2023",
        "Census Business Dynamics Statistics — state by firm size",
        "https://www2.census.gov/programs-surveys/bds/tables/time-series/2023/bds2023_st_fz.csv",
        "census_bds_state_by_firm_size_2023.csv",
        "https://www.census.gov/data/datasets/time-series/econ/bds/bds-datasets.html",
        "1978–2023",
        "Firm births, deaths, job creation, and job destruction by state and firm size.",
        3_000_000,
    ),
    Source(
        "bls_qcew_annual_singlefile_2025",
        "BLS Quarterly Census of Employment and Wages — annual single file",
        "https://data.bls.gov/cew/data/files/2025/csv/2025_annual_singlefile.zip",
        "bls_qcew_annual_singlefile_2025.zip",
        "https://www.bls.gov/cew/downloadable-data-files.htm",
        "2025",
        "Employment, establishments, payroll, and wages by NAICS, ownership, and geography.",
        60_000_000,
    ),
    Source(
        "census_naics_2022_descriptions",
        "Census 2022 NAICS descriptions",
        "https://www2.census.gov/programs-surveys/nonemployer-statistics/technical-documentation/"
        "code-lists/nes_naics22.txt",
        "census_naics_2022_descriptions.txt",
        "https://www.census.gov/programs-surveys/nonemployer-statistics/technical-documentation/"
        "reference/naics-descriptions.html",
        "2022",
        "Official NAICS validation labels.",
        15_000,
    ),
    Source(
        "census_sic_descriptions",
        "Census SIC descriptions",
        "https://www2.census.gov/programs-surveys/susb/technical-documentation/sic_codes_1988_to_1997.txt",
        "census_sic_descriptions_1988_1997.txt",
        "https://www.census.gov/programs-surveys/susb/technical-documentation/"
        "reference-files/industry-reference-files.html",
        "1987 SIC used in 1988–1997 SUSB",
        "Official SIC validation labels.",
        40_000,
    ),
    Source(
        "census_gazetteer_counties_2025",
        "Census Gazetteer — counties",
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_counties_national.zip",
        "census_gazetteer_counties_2025.zip",
        "https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2025.html",
        "2025",
        "Valid county names, FIPS codes, land area, and representative coordinates.",
        100_000,
    ),
    Source(
        "census_gazetteer_places_2025",
        "Census Gazetteer — places",
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip",
        "census_gazetteer_places_2025.zip",
        "https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2025.html",
        "2025",
        "Valid place/state combinations and representative coordinates.",
        1_000_000,
    ),
    Source(
        "census_gazetteer_zcta_2025",
        "Census Gazetteer — ZIP Code Tabulation Areas",
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_zcta_national.zip",
        "census_gazetteer_zcta_2025.zip",
        "https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2025.html",
        "2025",
        "Valid ZCTAs and representative coordinates.",
        800_000,
    ),
    Source(
        "fmcsa_company_census_distribution",
        "FMCSA Company Census privacy-minimized distribution",
        _fmcsa_aggregate_url(),
        "fmcsa_company_census_distribution.csv",
        "https://data.transportation.gov/Trucking-and-Motorcoaches/Company-Census-File/az4n-8mr2/about_data",
        "Daily snapshot accessed at run time",
        "Carrier counts by country/state, status, operation, organization type, and fleet-size class.",
        1_000,
    ),
    Source(
        "sec_company_tickers_exchange",
        "SEC EDGAR company, CIK, ticker, and exchange associations",
        "https://www.sec.gov/files/company_tickers_exchange.json",
        "sec_company_tickers_exchange.json",
        "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
        "Continuously updated",
        "Partial public-company name and exchange coverage.",
        100_000,
    ),
    Source(
        "sba_ppp_data_dictionary",
        "SBA PPP data dictionary",
        "https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/ppp-data-dictionary.xlsx",
        "sba_ppp_data_dictionary.xlsx",
        "https://data.sba.gov/dataset/ppp-foia",
        "2024-09-30 release",
        "Definitions for the privacy-minimized PPP calibration tables.",
        10_000,
    ),
    Source(
        "census_surnames_2010",
        "Census frequently occurring surnames",
        "https://www2.census.gov/topics/genealogy/2010surnames/names.zip",
        "census_surnames_2010.zip",
        "https://www.census.gov/data/developers/data-sets/surnames/2010.html",
        "2010",
        "Surname frequencies for names occurring at least 100 times; no person-level records.",
        10_000_000,
    ),
    Source(
        "ssa_national_names",
        "SSA national given-name counts",
        "https://www.ssa.gov/oact/babynames/names.zip",
        "ssa_national_names.zip",
        "https://www.ssa.gov/oact/babynames/limits.html",
        "1880–2025",
        "Given-name, sex, year, and count distributions with cells below five suppressed by SSA.",
        5_000_000,
        optional=True,
    ),
    Source(
        "nyc_popular_baby_names",
        "NYC DOHMH popular baby names",
        "https://data.cityofnewyork.us/resource/25th-nujf.csv?%24limit=50000",
        "nyc_popular_baby_names.csv",
        "https://data.cityofnewyork.us/Health/Popular-Baby-Names/25th-nujf/data",
        "Updated annually; accessed at run time",
        "Given-name counts by year, sex, and broad maternal ethnicity from civil birth registration.",
        1_000_000,
    ),
    Source(
        "usps_publication_28_suffixes",
        "USPS Publication 28 street suffix standards",
        "https://pe.usps.com/text/pub28/28apc_002.htm",
        "usps_publication_28_street_suffixes.html",
        "https://pe.usps.com/text/pub28/28apc_002.htm",
        "Accessed at run time",
        "Authoritative street-suffix names and standard abbreviations.",
        20_000,
    ),
    Source(
        "tiger_roads_los_angeles_2025",
        "Census TIGER/Line roads — Los Angeles County, CA",
        "https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_06037_roads.zip",
        "tiger_roads_06037_2025.zip",
        "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html",
        "2025",
        "Regional road-name components for aggregate address-shape calibration.",
        1_000_000,
    ),
    Source(
        "tiger_roads_cook_2025",
        "Census TIGER/Line roads — Cook County, IL",
        "https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_17031_roads.zip",
        "tiger_roads_17031_2025.zip",
        "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html",
        "2025",
        "Regional road-name components for aggregate address-shape calibration.",
        1_000_000,
    ),
    Source(
        "tiger_roads_suffolk_ma_2025",
        "Census TIGER/Line roads — Suffolk County, MA",
        "https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_25025_roads.zip",
        "tiger_roads_25025_2025.zip",
        "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html",
        "2025",
        "Regional road-name components for aggregate address-shape calibration.",
        250_000,
    ),
    Source(
        "tiger_roads_new_york_2025",
        "Census TIGER/Line roads — New York County, NY",
        "https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_36061_roads.zip",
        "tiger_roads_36061_2025.zip",
        "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html",
        "2025",
        "Regional road-name components for aggregate address-shape calibration.",
        250_000,
    ),
    Source(
        "tiger_roads_harris_2025",
        "Census TIGER/Line roads — Harris County, TX",
        "https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_48201_roads.zip",
        "tiger_roads_48201_2025.zip",
        "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html",
        "2025",
        "Regional road-name components for aggregate address-shape calibration.",
        1_000_000,
    ),
    Source(
        "tiger_roads_king_2025",
        "Census TIGER/Line roads — King County, WA",
        "https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_53033_roads.zip",
        "tiger_roads_53033_2025.zip",
        "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html",
        "2025",
        "Regional road-name components for aggregate address-shape calibration.",
        1_000_000,
    ),
    Source(
        "cfpb_complaints",
        "CFPB Consumer Complaint Database",
        "https://files.consumerfinance.gov/ccdb/complaints.csv.zip",
        "cfpb_complaints.csv.zip",
        "https://www.consumerfinance.gov/data-research/consumer-complaints/",
        "Continuously updated; accessed at run time",
        "High-frequency unigram and narrative-length distributions; complaint rows and narratives are not retained.",
        100_000_000,
        staged=True,
    ),
    Source(
        "iowa_active_business_entities",
        "Iowa active business entities",
        "https://idh-be.iowa.gov/api/v1/datasets/554/rows.csv",
        "iowa_active_business_entities.zip",
        "https://data.iowa.gov/catalog/dataset/554",
        "Monthly; accessed at run time",
        "Formation, legal-structure, and geography distributions; source rows are not retained.",
        1_000_000,
        staged=True,
    ),
    Source(
        "canada_active_cbca",
        "Corporations Canada — active business corporations",
        "https://d4bf66bykfyaf.cloudfront.net/corporations-active-cbca-en.csv",
        "canada_active_cbca.csv",
        "https://open.canada.ca/data/en/dataset/0032ce54-c5dd-4b66-99a0-320a7b5e99f2",
        "Continuously updated; accessed at run time",
        "Status, formation-year, province, and legal-name-pattern distributions; source rows are not retained.",
        90_000_000,
        staged=True,
    ),
    Source(
        "canada_inactive_cbca",
        "Corporations Canada — inactive/dissolved business corporations",
        "https://d4bf66bykfyaf.cloudfront.net/corporations-inactive-or-dissolved-cbca-en.csv",
        "canada_inactive_cbca.csv",
        "https://open.canada.ca/data/en/dataset/0032ce54-c5dd-4b66-99a0-320a7b5e99f2",
        "Continuously updated; accessed at run time",
        "Status, formation-year, province, and legal-name-pattern distributions; source rows are not retained.",
        140_000_000,
        staged=True,
    ),
    Source(
        "cms_nppes_weekly_v2",
        "CMS NPPES weekly incremental V2",
        "https://download.cms.gov/nppes/NPPES_Data_Dissemination_081026_081626_Weekly_V2.zip",
        "cms_nppes_weekly_v2_2026-08-16.zip",
        "https://download.cms.gov/nppes/NPI_Files.html",
        "2026-08-10 through 2026-08-16",
        "Type-2 organization taxonomy/state distribution; source rows are not retained.",
        6_000_000,
        staged=True,
    ),
    Source(
        "sba_ppp_150k_plus",
        "SBA PPP loans above $150,000",
        "https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/public_150k_plus_240930.csv",
        "sba_ppp_150k_plus_2024-09-30.csv",
        "https://data.sba.gov/dataset/ppp-foia",
        "2024-09-30 release",
        "Biased historical NAICS/state/jobs/loan-size distributions; source rows are not retained.",
        400_000_000,
        staged=True,
    ),
)

TIGER_ROAD_KEYS = (
    "tiger_roads_los_angeles_2025",
    "tiger_roads_cook_2025",
    "tiger_roads_suffolk_ma_2025",
    "tiger_roads_new_york_2025",
    "tiger_roads_harris_2025",
    "tiger_roads_king_2025",
)
REALISM_KEYS = (
    "census_surnames_2010",
    "nyc_popular_baby_names",
    "usps_publication_28_suffixes",
    *TIGER_ROAD_KEYS,
    "cfpb_complaints",
    "sec_company_tickers_exchange",
    "census_zbp_detail_2023",
)


LEGAL_SUFFIXES = (
    ("LIMITED LIABILITY COMPANY", ("LIMITED LIABILITY COMPANY",)),
    ("PROFESSIONAL CORPORATION", ("PROFESSIONAL CORPORATION", "PROFESSIONAL CORP", "P C")),
    ("INCORPORATED", ("INCORPORATED", "INC")),
    ("CORPORATION", ("CORPORATION", "CORP")),
    ("LIMITED", ("LIMITED", "LTD", "LTEE", "LTÉE")),
    ("LLC", ("LLC", "L L C")),
    ("COMPANY", ("COMPANY", "CO")),
    ("ASSOCIATION", ("ASSOCIATION", "ASSN")),
    ("COOPERATIVE", ("COOPERATIVE", "COOP")),
    ("PARTNERSHIP", ("PARTNERSHIP", "LLP", "L P", "LP")),
)


def classify_legal_suffix(value: Any) -> str:
    """Return a coarse legal-designator class without retaining the source name."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "MISSING"
    normalized = re.sub(r"[^0-9A-ZÀ-ÖØ-Þ]+", " ", str(value).upper()).strip()
    if not normalized:
        return "MISSING"
    for label, variants in LEGAL_SUFFIXES:
        if any(normalized == variant or normalized.endswith(f" {variant}") for variant in variants):
            return label
    return "OTHER/NONE"


def bucket_numbers(values: pd.Series, bins: list[float], labels: list[str]) -> pd.Series:
    """Convert numeric values to stable string buckets, preserving missing values."""
    numeric = pd.to_numeric(values, errors="coerce")
    bucketed = pd.cut(numeric, bins=bins, labels=labels, include_lowest=True, right=False)
    return bucketed.astype("string").fillna("MISSING")


def _clean_dimension(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def add_counts(counter: Counter[tuple[str, ...]], frame: pd.DataFrame, dimensions: list[str]) -> None:
    if frame.empty:
        return
    normalized = frame[dimensions].copy()
    for column in dimensions:
        normalized[column] = normalized[column].map(_clean_dimension)
    grouped = normalized.groupby(dimensions, dropna=False, observed=True).size()
    for key, count in grouped.items():
        tuple_key = key if isinstance(key, tuple) else (key,)
        counter[tuple(str(value) for value in tuple_key)] += int(count)


def _write_counter(path: Path, dimensions: list[str], counter: Counter[tuple[str, ...]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow([*dimensions, "records"])
        for key, count in sorted(counter.items()):
            writer.writerow([*key, count])
    return sum(counter.values())


def _download(source: Source, force: bool) -> Path:
    directory = STAGING_DIR if source.staged else RAW_DIR
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / source.filename
    if destination.exists() and destination.stat().st_size >= source.minimum_bytes and not force:
        print(f"[{source.key}] reuse {destination.stat().st_size / 1024 / 1024:.1f} MiB")
        return destination

    partial = destination.with_suffix(destination.suffix + ".part")
    if force:
        destination.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)

    resume_at = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if resume_at:
        headers["Range"] = f"bytes={resume_at}-"
    request = urllib.request.Request(source.url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=180)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{source.key}: HTTP {error.code} for {source.url}") from error

    status = getattr(response, "status", response.getcode())
    append = resume_at > 0 and status == 206
    mode = "ab" if append else "wb"
    downloaded = resume_at if append else 0
    next_progress = ((downloaded // PROGRESS_INTERVAL_BYTES) + 1) * PROGRESS_INTERVAL_BYTES
    with response, partial.open(mode) as output:
        while block := response.read(DOWNLOAD_BLOCK_SIZE):
            output.write(block)
            downloaded += len(block)
            if downloaded >= next_progress:
                print(f"[{source.key}] {downloaded / 1024 / 1024:.0f} MiB")
                next_progress += PROGRESS_INTERVAL_BYTES
    partial.replace(destination)
    if destination.stat().st_size < source.minimum_bytes:
        raise RuntimeError(
            f"{source.key}: expected at least {source.minimum_bytes} bytes, got {destination.stat().st_size}"
        )
    print(f"[{source.key}] downloaded {destination.stat().st_size / 1024 / 1024:.1f} MiB")
    return destination


def _download_all(force: bool, workers: int, sources: tuple[Source, ...] = SOURCES) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_download, source, force): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            paths[source.key] = future.result()
    return paths


def _open_single_csv_from_zip(path: Path, preferred_fragment: str | None = None) -> tuple[zipfile.ZipFile, Any]:
    archive = zipfile.ZipFile(path)
    candidates = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if preferred_fragment:
        preferred = [name for name in candidates if preferred_fragment.lower() in name.lower()]
        if preferred:
            candidates = preferred
    if not candidates:
        archive.close()
        raise RuntimeError(f"No CSV member found in {path}")
    return archive, archive.open(max(candidates, key=lambda name: archive.getinfo(name).file_size))


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _process_census_surnames(path: Path) -> list[dict[str, Any]]:
    output_path = DERIVED_DIR / "census_surname_distribution.csv"
    with zipfile.ZipFile(path) as archive:
        candidates = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not candidates:
            raise RuntimeError(f"No surname CSV found in {path}")
        with archive.open(candidates[0]) as source, output_path.open("w", encoding="utf-8", newline="") as output:
            reader = csv.DictReader(line.decode("utf-8-sig", "replace") for line in source)
            writer = csv.DictWriter(output, fieldnames=["surname", "records", "rank"])
            writer.writeheader()
            retained = 0
            for row in reader:
                surname = str(row.get("name", row.get("NAME", ""))).strip().title()
                count = str(row.get("count", row.get("COUNT", ""))).strip()
                rank = str(row.get("rank", row.get("RANK", ""))).strip()
                if not surname or not count.isdigit() or int(count) < 100:
                    continue
                writer.writerow({"surname": surname, "records": count, "rank": rank})
                retained += 1
    return [
        _derived_record(
            "census_surname_distribution",
            output_path,
            "census_surnames_2010",
            retained,
            "Normalized publisher-provided surname counts; the source already excludes names occurring fewer "
            "than 100 times.",
        )
    ]


def _process_ssa_names(path: Path) -> list[dict[str, Any]]:
    totals: Counter[tuple[str, str]] = Counter()
    first_year: dict[tuple[str, str], int] = {}
    last_year: dict[tuple[str, str], int] = {}
    input_records = 0
    with zipfile.ZipFile(path) as archive:
        members = []
        for name in archive.namelist():
            match = re.fullmatch(r"yob(\d{4})\.txt", Path(name).name, flags=re.IGNORECASE)
            if match:
                members.append((int(match.group(1)), name))
        if not members:
            raise RuntimeError(f"No SSA year files found in {path}")
        maximum_year = max(year for year, _name in members)
        minimum_year = maximum_year - 9
        for year, name in members:
            if year < minimum_year:
                continue
            with archive.open(name) as source:
                reader = csv.reader(line.decode("utf-8", "replace") for line in source)
                for given_name, sex, count in reader:
                    key = (given_name.strip(), sex.strip().upper())
                    numeric_count = int(count)
                    totals[key] += numeric_count
                    first_year[key] = min(year, first_year.get(key, year))
                    last_year[key] = max(year, last_year.get(key, year))
                    input_records += 1
    output_path = DERIVED_DIR / "ssa_given_name_distribution.csv"
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["given_name", "sex", "records", "first_year", "last_year"])
        for key, count in totals.most_common():
            if count < 25:
                continue
            writer.writerow([key[0], key[1], count, first_year[key], last_year[key]])
    return [
        _derived_record(
            "ssa_given_name_distribution",
            output_path,
            "ssa_national_names",
            input_records,
            "Aggregated the latest ten national years by given name and sex; SSA suppresses cells below five and "
            "this output requires at least 25 occurrences.",
        )
    ]


def _process_nyc_names(path: Path) -> list[dict[str, Any]]:
    totals: Counter[tuple[str, str]] = Counter()
    first_year: dict[tuple[str, str], int] = {}
    last_year: dict[tuple[str, str], int] = {}
    input_records = 0
    seen: set[tuple[str, str, str, str, str, str]] = set()
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            name = str(row.get("nm", "")).strip().title()
            sex = str(row.get("gndr", "")).strip().upper()[:1]
            raw_count = str(row.get("cnt", "")).strip()
            raw_year = str(row.get("brth_yr", "")).strip()
            if not name or sex not in {"F", "M"} or not raw_count.isdigit() or not raw_year.isdigit():
                continue
            source_key = (
                raw_year,
                str(row.get("gndr", "")).strip(),
                str(row.get("ethcty", "")).strip(),
                str(row.get("nm", "")).strip(),
                raw_count,
                str(row.get("rnk", "")).strip(),
            )
            if source_key in seen:
                continue
            seen.add(source_key)
            key = (name, sex)
            year = int(raw_year)
            totals[key] += int(raw_count)
            first_year[key] = min(year, first_year.get(key, year))
            last_year[key] = max(year, last_year.get(key, year))
            input_records += 1
    output_path = DERIVED_DIR / "nyc_given_name_distribution.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["given_name", "sex", "records", "first_year", "last_year"])
        writer.writerows(
            (key[0], key[1], count, first_year[key], last_year[key])
            for key, count in totals.most_common()
            if count >= 25
        )
    return [
        _derived_record(
            "nyc_given_name_distribution",
            output_path,
            "nyc_popular_baby_names",
            input_records,
            "Removed exact duplicate publisher rows, aggregated civil-registration counts over years and broad "
            "ethnicity groups by given name and sex, and retained names with at least 25 published occurrences. "
            "Geographic bias is explicit.",
        )
    ]


def _process_usps_suffixes(path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    parser = _TableParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    suffixes: dict[str, str] = {}
    current_primary = ""
    current_standard = ""
    for cells in parser.rows:
        normalized = [re.sub(r"[^A-Z]", "", cell.upper()) for cell in cells if cell.strip()]
        if len(normalized) >= 3 and normalized[0] not in {"PRIMARYSTREETSUFFIXNAME", "PRIMARY"}:
            current_primary, current_standard = normalized[0], normalized[-1]
        elif len(normalized) == 1 and current_primary and current_standard:
            suffixes[normalized[0]] = current_standard
            continue
        else:
            continue
        for value in normalized:
            if value:
                suffixes[value] = current_standard
        suffixes[current_primary] = current_standard
    if len(set(suffixes.values())) < 50:
        raise RuntimeError(f"Unexpectedly parsed only {len(set(suffixes.values()))} USPS suffixes")
    output_path = DERIVED_DIR / "usps_street_suffix_reference.csv"
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["source_suffix", "standard_suffix"])
        writer.writerows(sorted(suffixes.items()))
    return (
        [
            _derived_record(
                "usps_street_suffix_reference",
                output_path,
                "usps_publication_28_suffixes",
                len(suffixes),
                "Parsed the official standards table into suffix-to-standard-abbreviation mappings; no address "
                "rows are present.",
            )
        ],
        suffixes,
    )


def _iter_dbf_records(path: Path) -> tuple[int, list[dict[str, str]]]:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".dbf")]
        if not members:
            raise RuntimeError(f"No DBF member found in {path}")
        with archive.open(members[0]) as source:
            header = source.read(32)
            record_count = int.from_bytes(header[4:8], "little")
            header_length = int.from_bytes(header[8:10], "little")
            record_length = int.from_bytes(header[10:12], "little")
            descriptor_bytes = source.read(header_length - 33)
            source.read(1)
            fields: list[tuple[str, int]] = []
            for offset in range(0, len(descriptor_bytes), 32):
                descriptor = descriptor_bytes[offset : offset + 32]
                if len(descriptor) < 32 or descriptor[0] == 0x0D:
                    break
                name = descriptor[:11].split(b"\x00", 1)[0].decode("ascii", "replace").strip()
                fields.append((name, descriptor[16]))
            records: list[dict[str, str]] = []
            for _index in range(record_count):
                raw = source.read(record_length)
                if len(raw) != record_length:
                    raise RuntimeError(f"Truncated DBF record in {path}")
                if raw[:1] == b"*":
                    continue
                cursor = 1
                record: dict[str, str] = {}
                for name, length in fields:
                    record[name] = raw[cursor : cursor + length].decode("latin-1", "replace").strip()
                    cursor += length
                records.append(record)
    return record_count, records


def _process_tiger_roads(paths: dict[str, Path], suffixes: dict[str, str]) -> list[dict[str, Any]]:
    names: Counter[str] = Counter()
    suffix_counts: Counter[str] = Counter()
    input_records = 0
    directionals = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
    for key in TIGER_ROAD_KEYS:
        if key not in paths:
            continue
        source_records, records = _iter_dbf_records(paths[key])
        input_records += source_records
        for record in records:
            full_name = re.sub(r"\s+", " ", record.get("FULLNAME", "").upper()).strip()
            if not full_name:
                continue
            tokens = re.findall(r"[A-Z0-9]+(?:[-'][A-Z0-9]+)?", full_name)
            if tokens and tokens[0] in directionals:
                tokens.pop(0)
            if tokens and tokens[-1] in directionals:
                tokens.pop()
            standard_suffix = ""
            if tokens and tokens[-1] in suffixes:
                standard_suffix = suffixes[tokens.pop()]
            base = " ".join(tokens).title()
            if base and len(base) <= 48 and not re.fullmatch(r"\d+", base):
                names[base] += 1
                if standard_suffix:
                    suffix_counts[standard_suffix] += 1
    name_path = DERIVED_DIR / "tiger_street_name_distribution.csv"
    suffix_path = DERIVED_DIR / "tiger_street_suffix_distribution.csv"
    with name_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["street_name", "records"])
        writer.writerows((name, count) for name, count in names.most_common(10_000) if count >= 5)
    with suffix_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["standard_suffix", "records"])
        writer.writerows(suffix_counts.most_common())
    source_keys = ";".join(key for key in TIGER_ROAD_KEYS if key in paths)
    transform = (
        "Extracted independent road-name and standardized-suffix frequency tables from a geographically diverse "
        "county sample; geometry and name/suffix pairings were discarded to prevent address-row replay."
    )
    return [
        _derived_record("tiger_street_name_distribution", name_path, source_keys, input_records, transform),
        _derived_record("tiger_street_suffix_distribution", suffix_path, source_keys, input_records, transform),
    ]


def _process_sec_name_tokens(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = payload.get("fields", [])
    data = payload.get("data", [])
    if "name" not in fields or not isinstance(data, list):
        raise RuntimeError("Unexpected SEC company-ticker payload")
    name_index = fields.index("name")
    tokens: Counter[str] = Counter()
    documents: Counter[str] = Counter()
    excluded = {variant for _label, variants in LEGAL_SUFFIXES for variant in variants}
    for row in data:
        name_tokens = {
            token.title()
            for token in re.findall(r"[A-Z][A-Z&'-]{2,30}", str(row[name_index]).upper())
            if token not in excluded
        }
        for token in name_tokens:
            tokens[token] += 1
            documents[token] += 1
    output_path = DERIVED_DIR / "sec_business_name_token_distribution.csv"
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["token", "records", "document_frequency"])
        writer.writerows((token, count, documents[token]) for token, count in tokens.most_common() if count >= 5)
    return [
        _derived_record(
            "sec_business_name_token_distribution",
            output_path,
            "sec_company_tickers_exchange",
            len(data),
            "Retained only tokens occurring in at least five public-company names; complete names, CIKs, tickers, "
            "and token order were discarded.",
        )
    ]


def _process_cfpb(path: Path) -> list[dict[str, Any]]:
    token_counts: Counter[str] = Counter()
    document_counts: Counter[str] = Counter()
    length_counts: Counter[str] = Counter()
    input_records = 0
    archive, member = _open_single_csv_from_zip(path, "complaints")
    try:
        header = pd.read_csv(member, nrows=0)
        narrative_column = next(
            (column for column in header.columns if "complaint narrative" in str(column).lower()),
            None,
        )
        if narrative_column is None:
            raise RuntimeError("CFPB download has no consumer complaint narrative column")
        member.seek(0)
        for chunk in pd.read_csv(member, usecols=[narrative_column], dtype="string", chunksize=CHUNK_SIZE):
            for narrative in chunk[narrative_column].dropna():
                tokens = [
                    token.lower()
                    for token in re.findall(r"[A-Za-z][A-Za-z'-]{1,30}", str(narrative))
                    if token.lower() not in {"xx", "xxx", "xxxx", "xxxxx"}
                ]
                if not tokens:
                    continue
                input_records += 1
                token_counts.update(tokens)
                document_counts.update(set(tokens))
                length = len(tokens)
                upper = min(((length // 50) + 1) * 50 - 1, 999)
                label = "1000_PLUS" if length >= 1000 else f"{upper - 49:04d}_{upper:04d}"
                length_counts[label] += 1
    finally:
        member.close()
        archive.close()
    token_path = DERIVED_DIR / "cfpb_narrative_token_distribution.csv"
    length_path = DERIVED_DIR / "cfpb_narrative_length_distribution.csv"
    with token_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["token", "records", "document_frequency"])
        writer.writerows(
            (token, count, document_counts[token])
            for token, count in token_counts.most_common(10_000)
            if document_counts[token] >= 100
        )
    with length_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["word_count_band", "records"])
        writer.writerows(sorted(length_counts.items()))
    transform = (
        "Retained only unigrams appearing in at least 100 different opt-in, CFPB-scrubbed narratives plus 50-word "
        "length bands; narratives, IDs, companies, locations, token order, and rare terms were discarded."
    )
    return [
        _derived_record("cfpb_narrative_token_distribution", token_path, "cfpb_complaints", input_records, transform),
        _derived_record("cfpb_narrative_length_distribution", length_path, "cfpb_complaints", input_records, transform),
    ]


def _process_iowa(path: Path) -> list[dict[str, Any]]:
    distribution: Counter[tuple[str, ...]] = Counter()
    name_profile: Counter[tuple[str, ...]] = Counter()
    archive, member = _open_single_csv_from_zip(path, "active_iowa_business_entities")
    usecols = ["legal_name", "corporation_type", "effective_date", "ho_state", "ho_country"]
    try:
        for chunk in pd.read_csv(member, usecols=usecols, dtype="string", chunksize=CHUNK_SIZE):
            effective = pd.to_datetime(chunk["effective_date"], errors="coerce")
            chunk["effective_year"] = effective.dt.year.astype("Int64").astype("string")
            add_counts(
                distribution,
                chunk,
                ["corporation_type", "effective_year", "ho_state", "ho_country"],
            )
            chunk["legal_suffix"] = chunk["legal_name"].map(classify_legal_suffix)
            add_counts(name_profile, chunk, ["corporation_type", "legal_suffix"])
    finally:
        member.close()
        archive.close()

    dist_path = DERIVED_DIR / "iowa_business_registry_distribution.csv"
    name_path = DERIVED_DIR / "iowa_legal_name_pattern_distribution.csv"
    records = _write_counter(
        dist_path,
        ["corporation_type", "effective_year", "home_office_state", "home_office_country"],
        distribution,
    )
    _write_counter(name_path, ["corporation_type", "legal_suffix"], name_profile)
    return [
        _derived_record(
            "iowa_business_registry_distribution",
            dist_path,
            "iowa_active_business_entities",
            records,
            "Grouped by entity type, effective year, and home-office geography; identifiers and addresses removed.",
        ),
        _derived_record(
            "iowa_legal_name_pattern_distribution",
            name_path,
            "iowa_active_business_entities",
            records,
            "Grouped legal-designator patterns only; legal names and identifiers removed.",
        ),
    ]


def _process_canada(active_path: Path, inactive_path: Path) -> list[dict[str, Any]]:
    distribution: Counter[tuple[str, ...]] = Counter()
    name_profile: Counter[tuple[str, ...]] = Counter()
    usecols = [
        "Corporate name - form 1",
        "Governing legislation",
        "Status",
        "Status Detail",
        "Anniversary date",
        "Province/territory",
        "Country",
    ]
    for path in (active_path, inactive_path):
        for chunk in pd.read_csv(path, usecols=usecols, dtype="string", chunksize=CHUNK_SIZE, encoding="utf-8-sig"):
            anniversary = pd.to_datetime(chunk["Anniversary date"], errors="coerce")
            chunk["effective_year"] = anniversary.dt.year.astype("Int64").astype("string")
            add_counts(
                distribution,
                chunk,
                [
                    "Governing legislation",
                    "Status",
                    "Status Detail",
                    "effective_year",
                    "Province/territory",
                    "Country",
                ],
            )
            chunk["legal_suffix"] = chunk["Corporate name - form 1"].map(classify_legal_suffix)
            add_counts(name_profile, chunk, ["Status", "legal_suffix"])

    dist_path = DERIVED_DIR / "canada_corporations_distribution.csv"
    name_path = DERIVED_DIR / "canada_legal_name_pattern_distribution.csv"
    records = _write_counter(
        dist_path,
        ["governing_legislation", "status", "status_detail", "effective_year", "province", "country"],
        distribution,
    )
    _write_counter(name_path, ["status", "legal_suffix"], name_profile)
    source_keys = "canada_active_cbca;canada_inactive_cbca"
    return [
        _derived_record(
            "canada_corporations_distribution",
            dist_path,
            source_keys,
            records,
            "Grouped by legislation, status, effective year, and province; names, tax IDs, and addresses removed.",
        ),
        _derived_record(
            "canada_legal_name_pattern_distribution",
            name_path,
            source_keys,
            records,
            "Grouped legal-designator patterns only; names, tax IDs, and addresses removed.",
        ),
    ]


def _process_nppes(path: Path) -> list[dict[str, Any]]:
    distribution: Counter[tuple[str, ...]] = Counter()
    archive, member = _open_single_csv_from_zip(path, "npidata_pfile")
    desired = [
        "Entity Type Code",
        "Provider Business Practice Location Address State Name",
        "Healthcare Provider Taxonomy Code_1",
        "Provider Enumeration Date",
        "Last Update Date",
        "NPI Deactivation Date",
    ]
    try:
        header = pd.read_csv(member, nrows=0).columns.tolist()
        missing = sorted(set(desired) - set(header))
        if missing:
            raise RuntimeError(f"NPPES columns missing: {missing}")
        member.close()
        archive.close()
        archive, member = _open_single_csv_from_zip(path, "npidata_pfile")
        for chunk in pd.read_csv(member, usecols=desired, dtype="string", chunksize=CHUNK_SIZE):
            chunk = chunk.loc[chunk["Entity Type Code"].str.strip() == "2"].copy()
            if chunk.empty:
                continue
            enumeration = pd.to_datetime(chunk["Provider Enumeration Date"], errors="coerce")
            last_update = pd.to_datetime(chunk["Last Update Date"], errors="coerce")
            chunk["enumeration_year"] = enumeration.dt.year.astype("Int64").astype("string")
            chunk["last_update_year"] = last_update.dt.year.astype("Int64").astype("string")
            chunk["is_deactivated"] = chunk["NPI Deactivation Date"].notna().map({True: "Y", False: "N"})
            add_counts(
                distribution,
                chunk,
                [
                    "Provider Business Practice Location Address State Name",
                    "Healthcare Provider Taxonomy Code_1",
                    "enumeration_year",
                    "last_update_year",
                    "is_deactivated",
                ],
            )
    finally:
        member.close()
        archive.close()

    output_path = DERIVED_DIR / "cms_nppes_type2_weekly_distribution.csv"
    records = _write_counter(
        output_path,
        ["practice_state", "taxonomy_code", "enumeration_year", "last_update_year", "is_deactivated"],
        distribution,
    )
    return [
        _derived_record(
            "cms_nppes_type2_weekly_distribution",
            output_path,
            "cms_nppes_weekly_v2",
            records,
            "Type-2 organizations grouped by state/taxonomy/year; NPIs, names, addresses, and contacts removed.",
        )
    ]


def _add_metric_sums(
    accumulator: defaultdict[tuple[str, ...], list[float]],
    grouped: pd.DataFrame,
    dimensions: list[str],
    metrics: list[str],
) -> None:
    for row in grouped.reset_index().itertuples(index=False, name=None):
        key = tuple(_clean_dimension(value) for value in row[: len(dimensions)])
        values = row[len(dimensions) :]
        for index, value in enumerate(values):
            if pd.notna(value):
                accumulator[key][index] += float(value)


def _write_metrics(
    path: Path,
    dimensions: list[str],
    metrics: list[str],
    accumulator: defaultdict[tuple[str, ...], list[float]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow([*dimensions, *metrics])
        for key, values in sorted(accumulator.items()):
            writer.writerow([*key, *[int(value) if value.is_integer() else round(value, 2) for value in values]])


def _process_ppp(path: Path) -> list[dict[str, Any]]:
    by_industry: defaultdict[tuple[str, ...], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    by_profile: defaultdict[tuple[str, ...], list[float]] = defaultdict(lambda: [0.0, 0.0])
    usecols = [
        "BorrowerState",
        "NAICSCode",
        "BusinessType",
        "BusinessAgeDescription",
        "RuralUrbanIndicator",
        "JobsReported",
        "CurrentApprovalAmount",
    ]
    total_rows = 0
    for chunk in pd.read_csv(
        path,
        usecols=usecols,
        dtype="string",
        chunksize=CHUNK_SIZE,
        low_memory=False,
        encoding="cp1252",
        encoding_errors="replace",
    ):
        total_rows += len(chunk)
        chunk["approval"] = pd.to_numeric(chunk["CurrentApprovalAmount"], errors="coerce")
        chunk["jobs"] = pd.to_numeric(chunk["JobsReported"], errors="coerce")
        chunk["loan_row"] = 1
        chunk["jobs_nonnull"] = chunk["jobs"].notna().astype(int)

        industry_dims = ["BorrowerState", "NAICSCode"]
        industry = chunk.groupby(industry_dims, dropna=False, observed=True).agg(
            loans=("loan_row", "sum"),
            total_approval=("approval", "sum"),
            jobs_reported=("jobs", "sum"),
            jobs_nonnull=("jobs_nonnull", "sum"),
        )
        _add_metric_sums(
            by_industry,
            industry,
            industry_dims,
            ["loans", "total_approval", "jobs_reported", "jobs_nonnull"],
        )

        chunk["loan_size_band"] = bucket_numbers(
            chunk["approval"],
            [-math.inf, 150_000, 350_000, 1_000_000, 2_000_000, math.inf],
            ["UNDER_150K", "150K_TO_350K", "350K_TO_1M", "1M_TO_2M", "2M_PLUS"],
        )
        chunk["jobs_band"] = bucket_numbers(
            chunk["jobs"],
            [-math.inf, 1, 5, 10, 25, 50, 100, 250, 500, math.inf],
            ["ZERO", "1_TO_4", "5_TO_9", "10_TO_24", "25_TO_49", "50_TO_99", "100_TO_249", "250_TO_499", "500_PLUS"],
        )
        profile_dims = [
            "BusinessType",
            "BusinessAgeDescription",
            "RuralUrbanIndicator",
            "loan_size_band",
            "jobs_band",
        ]
        profile = chunk.groupby(profile_dims, dropna=False, observed=True).agg(
            loans=("loan_row", "sum"),
            total_approval=("approval", "sum"),
        )
        _add_metric_sums(by_profile, profile, profile_dims, ["loans", "total_approval"])

    industry_path = DERIVED_DIR / "sba_ppp_by_state_naics_distribution.csv"
    profile_path = DERIVED_DIR / "sba_ppp_business_profile_distribution.csv"
    _write_metrics(
        industry_path,
        ["borrower_state", "naics_code"],
        ["loans", "total_approval", "jobs_reported", "jobs_nonnull"],
        by_industry,
    )
    _write_metrics(
        profile_path,
        ["business_type", "business_age", "rural_urban", "loan_size_band", "jobs_band"],
        ["loans", "total_approval"],
        by_profile,
    )
    note = (
        "Aggregated historical PPP sample above $150K; borrower/lender names, addresses, IDs, and demographics removed."
    )
    return [
        _derived_record("sba_ppp_by_state_naics_distribution", industry_path, "sba_ppp_150k_plus", total_rows, note),
        _derived_record("sba_ppp_business_profile_distribution", profile_path, "sba_ppp_150k_plus", total_rows, note),
    ]


def _safe_remove_staged(paths: list[Path]) -> None:
    staging_root = STAGING_DIR.resolve()
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(staging_root):
            raise RuntimeError(f"Refusing to remove non-staging path: {resolved}")
        resolved.unlink(missing_ok=True)
    if STAGING_DIR.exists() and not any(STAGING_DIR.iterdir()):
        STAGING_DIR.rmdir()


def _process_reference_sources(paths: dict[str, Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if "census_surnames_2010" in paths:
        records.extend(_process_census_surnames(paths["census_surnames_2010"]))
    if "ssa_national_names" in paths:
        records.extend(_process_ssa_names(paths["ssa_national_names"]))
    if "nyc_popular_baby_names" in paths:
        records.extend(_process_nyc_names(paths["nyc_popular_baby_names"]))
    suffixes: dict[str, str] = {}
    if "usps_publication_28_suffixes" in paths:
        suffix_records, suffixes = _process_usps_suffixes(paths["usps_publication_28_suffixes"])
        records.extend(suffix_records)
    if any(key in paths for key in TIGER_ROAD_KEYS):
        if not suffixes:
            reference_path = DERIVED_DIR / "usps_street_suffix_reference.csv"
            if not reference_path.is_file():
                raise RuntimeError(
                    "TIGER road processing requires the USPS suffix source or existing derived reference"
                )
            with reference_path.open(encoding="utf-8", newline="") as source:
                suffixes = {
                    row["source_suffix"]: row["standard_suffix"]
                    for row in csv.DictReader(source)
                    if row.get("source_suffix") and row.get("standard_suffix")
                }
        records.extend(_process_tiger_roads(paths, suffixes))
    if "sec_company_tickers_exchange" in paths:
        records.extend(_process_sec_name_tokens(paths["sec_company_tickers_exchange"]))
    return records


def _process_staged(paths: dict[str, Path], keep_staging: bool) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if "iowa_active_business_entities" in paths:
        records.extend(_process_iowa(paths["iowa_active_business_entities"]))
    canada_keys = {"canada_active_cbca", "canada_inactive_cbca"}
    if canada_keys & paths.keys():
        if not canada_keys <= paths.keys():
            raise RuntimeError("Canada distribution processing requires both active and inactive sources")
        records.extend(_process_canada(paths["canada_active_cbca"], paths["canada_inactive_cbca"]))
    if "cms_nppes_weekly_v2" in paths:
        records.extend(_process_nppes(paths["cms_nppes_weekly_v2"]))
    if "sba_ppp_150k_plus" in paths:
        records.extend(_process_ppp(paths["sba_ppp_150k_plus"]))
    if "cfpb_complaints" in paths:
        records.extend(_process_cfpb(paths["cfpb_complaints"]))
    if not keep_staging:
        _safe_remove_staged([paths[source.key] for source in SOURCES if source.staged and source.key in paths])
    return records


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(DOWNLOAD_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def _csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as source:
        return max(sum(1 for _ in source) - 1, 0)


def _validate_file(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix in {".zip", ".xlsx"}:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise RuntimeError(f"Corrupt archive member {bad_member} in {path}")
    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as source:
            json.load(source)
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8", errors="replace", newline="") as source:
            header = next(csv.reader(source), None)
            if not header:
                raise RuntimeError(f"CSV has no header: {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"Empty file: {path}")


def _derived_record(
    key: str,
    path: Path,
    source_keys: str,
    input_records: int,
    transform: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "path": path,
        "source_keys": source_keys,
        "input_records": input_records,
        "transform": transform,
    }


def _write_manifest(
    paths: dict[str, Path], derived_records: list[dict[str, Any]], *, merge_existing: bool = False
) -> None:
    source_by_key = {source.key: source for source in SOURCES}
    now = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for source in SOURCES:
        if source.staged or source.key not in paths:
            continue
        path = paths[source.key]
        _validate_file(path)
        rows.append(
            {
                "key": source.key,
                "title": source.title,
                "vintage": source.vintage,
                "artifact_type": "official_download",
                "local_path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "records": _csv_rows(path) if path.suffix.lower() == ".csv" else "",
                "source_url": source.url,
                "landing_page": source.landing_page,
                "purpose": source.purpose,
                "privacy_transform": "None; publisher-provided aggregate/reference file.",
                "accessed_at_utc": now,
            }
        )
    for record in derived_records:
        path = record["path"]
        _validate_file(path)
        keys = record["source_keys"].split(";")
        source_urls = [source_by_key[key].url for key in keys]
        landing_pages = sorted({source_by_key[key].landing_page for key in keys})
        rows.append(
            {
                "key": record["key"],
                "title": record["key"].replace("_", " ").title(),
                "vintage": "; ".join(source_by_key[key].vintage for key in keys),
                "artifact_type": "privacy_minimized_distribution",
                "local_path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "records": _csv_rows(path),
                "source_url": "; ".join(source_urls),
                "landing_page": "; ".join(landing_pages),
                "purpose": "Calibration-only aggregate derived from the cited public source.",
                "privacy_transform": record["transform"],
                "accessed_at_utc": now,
            }
        )

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    if merge_existing and MANIFEST_PATH.is_file():
        with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as source:
            existing = list(csv.DictReader(source))
        merged = {row["key"]: row for row in existing}
        merged.update({row["key"]: row for row in rows})
        rows = list(merged.values())
    if not rows:
        raise RuntimeError("No manifest rows were produced")
    fields = list(rows[0])
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with LINKS_PATH.open("w", encoding="utf-8", newline="") as output:
        for source in SOURCES:
            output.write(f"{source.title}\n{source.url}\n\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Redownload completed files.")
    parser.add_argument("--keep-staging", action="store_true", help="Keep privacy-sensitive source rows.")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent download count (default: 4).")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="KEY",
        help="Download only a source key; use repeatedly, comma-separate keys, or pass 'realism'.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print source keys and official download metadata without downloading.",
    )
    return parser.parse_args()


def _print_source_catalog(sources: tuple[Source, ...] = SOURCES) -> None:
    for source in sources:
        availability = "opt-in" if source.optional else "default"
        handling = "privacy-minimized after staging" if source.staged else "retained official artifact"
        print(f"{source.key} [{availability}; {handling}]")
        print(f"  {source.title} ({source.vintage})")
        print(f"  download: {source.url}")
        print(f"  publisher: {source.landing_page}")
        print(f"  purpose: {source.purpose}")


def _select_sources(selected_keys: set[str]) -> tuple[Source, ...]:
    """Keep optional sources opt-in while allowing an explicit single-source retry."""
    return tuple(
        source for source in SOURCES if source.key in selected_keys or (not selected_keys and not source.optional)
    )


def main() -> int:
    args = _parse_args()
    if args.list:
        _print_source_catalog()
        return 0
    if args.workers < 1 or args.workers > 8:
        raise ValueError("--workers must be between 1 and 8")
    selected_keys = {key.strip() for item in args.only for key in item.split(",") if key.strip()}
    if "realism" in selected_keys:
        selected_keys.remove("realism")
        selected_keys.update(REALISM_KEYS)
    known_keys = {source.key for source in SOURCES}
    unknown = sorted(selected_keys - known_keys)
    if unknown:
        raise ValueError(f"unknown --only source keys: {', '.join(unknown)}")
    selected_sources = _select_sources(selected_keys)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    paths = _download_all(force=args.force, workers=args.workers, sources=selected_sources)
    derived_records = _process_reference_sources(paths)
    derived_records.extend(_process_staged(paths, keep_staging=args.keep_staging))
    _write_manifest(paths, derived_records, merge_existing=bool(selected_keys))
    print(f"Validated {sum(not source.staged for source in selected_sources)} official downloads")
    print(f"Created {len(derived_records)} privacy-minimized distributions")
    print(f"Manifest: {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise

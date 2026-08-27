from __future__ import annotations

import csv
import importlib.util
import io
import sys
import zipfile
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


def _csv_text(header: list[str], rows: list[list[object]], delimiter: str = ",") -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue()


def test_classify_legal_suffix_removes_name_specificity() -> None:
    assert downloader.classify_legal_suffix("Example Holdings, Inc.") == "INCORPORATED"
    assert downloader.classify_legal_suffix("Example Logistics LLC") == "LLC"
    assert downloader.classify_legal_suffix("Example Industries Ltd.") == "LIMITED"
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


def test_iowa_transform_retains_only_us_home_offices(tmp_path, monkeypatch) -> None:
    source = tmp_path / "iowa.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "active_iowa_business_entities.csv",
            "legal_name,corporation_type,effective_date,ho_state,ho_country\n"
            "Example Iowa LLC,LLC,2020-01-01,IA,USA\n"
            "Example Foreign Ltd.,CORP,2021-01-01,ON,CAN\n"
            "Example Missing Inc.,CORP,2022-01-01,IA,\n",
        )
    monkeypatch.setattr(downloader, "DERIVED_DIR", tmp_path / "derived")

    records = downloader._process_iowa(source)
    distribution = pd.read_csv(records[0]["path"])
    names = pd.read_csv(records[1]["path"])

    assert distribution["records"].sum() == 1
    assert distribution["home_office_country"].tolist() == ["US"]
    assert names["records"].sum() == 1
    assert names["legal_suffix"].tolist() == ["LLC"]


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
    assert "geography: United States" in output
    assert "cfpb_complaints [default; privacy-minimized after staging]" in output
    assert sources["cfpb_complaints"].purpose in output


def test_source_catalog_is_us_only_and_country_scoped_queries_fail_closed() -> None:
    sources = {source.key: source for source in downloader.SOURCES}

    downloader._validate_us_source_catalog()
    assert all(source.geographic_scope == "United States" for source in sources.values())
    assert "canada_active_cbca" not in sources
    assert "canada_inactive_cbca" not in sources
    assert "colorado_business_entities_us_distribution" in sources
    assert "%24where=phy_country+%3D+%27US%27" in sources["fmcsa_company_census_distribution"].url
    assert "%24where=principalcountry+%3D+%27US%27" in sources["colorado_business_entities_us_distribution"].url


def test_github_download_catalog_covers_every_registered_source() -> None:
    catalog = (ROOT / "docs" / "public-data-sources.md").read_text(encoding="utf-8")

    assert "Complete 35-source index" in catalog
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


def test_capability_profile_expands_paired_acs_sources() -> None:
    sources = {source.key: source for source in downloader.SOURCES}
    expanded = downloader._expand_selected_keys({"capability"})

    assert expanded == set(downloader.CAPABILITY_KEYS)
    assert downloader._expand_selected_keys({"acs_pums_nc_person_2024"}) >= set(downloader.ACS_PUMS_KEYS)
    assert sources["acs_pums_nc_person_2024"].staged is True
    assert sources["acs_pums_nc_housing_2024"].staged is True
    assert sources["nhtsa_complaints_2020_2024"].staged is True
    assert sources["usda_fooddata_foundation_2026_04"].staged is False


def test_acs_pums_transform_suppresses_rows_and_discards_serials(tmp_path, monkeypatch) -> None:
    housing = tmp_path / "housing.zip"
    person = tmp_path / "person.zip"
    serials = [f"H{index:03d}" for index in range(25)]
    with zipfile.ZipFile(housing, "w") as archive:
        archive.writestr(
            "psam_h37.csv",
            _csv_text(
                ["SERIALNO", "TYPEHUGQ", "NP", "TEN", "BDSP", "VEH", "HINCP", "ACCESSINET", "FS", "WGTP"],
                [[serial, 1, 2, 3, 2, 1, 50_000, 1, 2, 2] for serial in serials],
            ),
        )
    with zipfile.ZipFile(person, "w") as archive:
        archive.writestr(
            "psam_p37.csv",
            _csv_text(
                ["SERIALNO", "AGEP", "SEX", "SCHL", "ESR", "DIS", "HICOV", "PINCP", "RELSHIPP", "PWGTP"],
                [[serial, 40, 2, 21, 1, 2, 1, 60_000, 20, 3] for serial in serials],
            ),
        )
    monkeypatch.setattr(downloader, "DERIVED_DIR", tmp_path / "derived")

    records = downloader._process_acs_pums(person, housing)
    outputs = {record["key"]: pd.read_csv(record["path"]) for record in records}

    assert outputs["acs_pums_nc_person_distribution"]["records"].sum() == 25
    assert outputs["acs_pums_nc_person_distribution"]["weighted_people"].sum() == 75
    assert outputs["acs_pums_nc_household_distribution"]["records"].sum() == 25
    assert outputs["acs_pums_nc_household_distribution"]["weighted_households"].sum() == 50
    assert outputs["acs_pums_nc_relationship_distribution"]["relationship"].tolist() == ["REFERENCE_PERSON"]
    assert all("SERIALNO" not in frame.columns for frame in outputs.values())


def test_nhtsa_transform_never_retains_identifying_fields(tmp_path, monkeypatch) -> None:
    source = tmp_path / "nhtsa.zip"
    rows = []
    for index in range(25):
        row = {column: "" for column in downloader.NHTSA_COMPLAINT_COLUMNS}
        row.update(
            {
                "CMPLID": f"COMP-{index}",
                "ODINO": f"ODI-{index}",
                "MAKETXT": "EXAMPLE MAKE",
                "YEARTXT": "2022",
                "CRASH": "N",
                "FIRE": "N",
                "INJURED": "0",
                "DEATHS": "0",
                "COMPDESC": "ENGINE",
                "CITY": f"PRIVATE CITY {index}",
                "STATE": "NC",
                "VIN": f"PRIVATEVIN{index}",
                "DATEA": "20240115",
                "MILES": "10000",
                "CDESCR": "The vehicle engine stopped while driving on the road",
                "CMPL_TYPE": "VOQ",
                "VEH_SPEED": "30",
                "PROD_TYPE": "VEHICLE",
                "MEDICAL_ATTN": "N",
                "VEHICLES_TOWED_YN": "Y",
                "DEALER_NAME": f"PRIVATE DEALER {index}",
                "VEHICLE_OPERATOR": f"PRIVATE PERSON {index}",
            }
        )
        rows.append([row[column] for column in downloader.NHTSA_COMPLAINT_COLUMNS])
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("COMPLAINTS_RECEIVED_2020-2024.txt", _csv_text([], rows, delimiter="\t").lstrip("\n"))
    monkeypatch.setattr(downloader, "DERIVED_DIR", tmp_path / "derived")
    monkeypatch.setattr(downloader, "NHTSA_NARRATIVE_MIN_DOCUMENTS", 2)

    records = downloader._process_nhtsa_complaints(source)
    outputs = {record["key"]: pd.read_csv(record["path"]) for record in records}

    assert outputs["nhtsa_vehicle_component_distribution"]["records"].sum() == 25
    assert outputs["nhtsa_incident_profile_distribution"]["records"].sum() == 25
    assert outputs["nhtsa_narrative_length_distribution"]["records"].sum() == 25
    assert not outputs["nhtsa_narrative_token_distribution"].empty
    forbidden = {"CMPLID", "ODINO", "CITY", "STATE", "VIN", "DEALER_NAME", "VEHICLE_OPERATOR"}
    assert all(not forbidden.intersection(frame.columns) for frame in outputs.values())
    assert "PRIVATE" not in " ".join(frame.to_csv(index=False) for frame in outputs.values())


def test_fooddata_transform_aggregates_relational_nutrients(tmp_path, monkeypatch) -> None:
    source = tmp_path / "fooddata.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "bundle/food.csv",
            _csv_text(
                ["fdc_id", "data_type", "description", "food_category_id"],
                [[index, "foundation_food", f"Food {index}", 1] for index in range(1, 6)],
            ),
        )
        archive.writestr("bundle/foundation_food.csv", _csv_text(["fdc_id"], [[index] for index in range(1, 6)]))
        archive.writestr("bundle/food_category.csv", _csv_text(["id", "description"], [[1, "Fruit"]]))
        archive.writestr("bundle/nutrient.csv", _csv_text(["id", "name", "unit_name"], [[100, "Protein", "g"]]))
        archive.writestr(
            "bundle/food_nutrient.csv",
            _csv_text(
                ["fdc_id", "nutrient_id", "amount"],
                [[index, 100, index] for index in range(1, 6)],
            ),
        )
    monkeypatch.setattr(downloader, "DERIVED_DIR", tmp_path / "derived")

    records = downloader._process_fooddata_foundation(source)
    output = pd.read_csv(records[0]["path"])

    assert output.to_dict(orient="records") == [
        {
            "food_category": "Fruit",
            "nutrient_name": "Protein",
            "unit_name": "g",
            "observations": 5,
            "distinct_foods": 5,
            "mean_amount": 3.0,
            "median_amount": 3.0,
            "minimum_amount": 1,
            "maximum_amount": 5,
        }
    ]

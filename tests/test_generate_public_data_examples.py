from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generate_public_data_examples", ROOT / "tools" / "generate_public_data_examples.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load public-data example generator")
examples = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = examples
SPEC.loader.exec_module(examples)


def test_every_requested_category_and_local_artifact_has_a_sampler() -> None:
    expected_categories = {
        "business_population",
        "employment_wages",
        "industry_validity",
        "addresses_geography",
        "business_names_formation",
        "federal_contractors",
        "public_companies",
        "historical_small_business",
        "transportation",
        "healthcare",
        "public_records",
        "realism_calibration",
    }
    assert set(examples.CATEGORY_BY_KEY) == expected_categories
    assert set(examples.SOURCE_CATEGORY.values()) == expected_categories
    assert len(examples.LOCAL_SAMPLERS) == 40
    assert set(examples.LOCAL_SAMPLERS) < set(examples.SOURCE_CATEGORY)


def test_spreadsheet_column_index_supports_single_and_multiple_letters() -> None:
    assert examples._column_index("A1") == 0
    assert examples._column_index("Z42") == 25
    assert examples._column_index("AA7") == 26
    assert examples._column_index("AZ99") == 51
    with pytest.raises(ValueError, match="Invalid spreadsheet cell reference"):
        examples._column_index("12")


def test_usaspending_example_drops_street_and_external_identifiers() -> None:
    source_row = {
        "Recipient Name": "EXAMPLE BUSINESS LLC",
        "Recipient Location": {
            "city_name": "EXAMPLE CITY",
            "state_code": "NY",
            "address_line1": "123 PRIVATE LINKAGE STREET",
            "zip4": "1234",
        },
        "NAICS": {"code": "541511", "description": "CUSTOM COMPUTER PROGRAMMING SERVICES"},
        "Contract Award Type": "DEFINITIVE CONTRACT",
        "Award Amount": 123456.78,
        "Awarding Agency": "Example Agency",
        "Recipient UEI": "DO-NOT-RETAIN",
        "Recipient DUNS Number": "DO-NOT-RETAIN",
        "Award ID": "DO-NOT-RETAIN",
    }
    rows = examples._extract_usaspending_examples([source_row] * examples.EXAMPLE_LIMIT)
    assert len(rows) == examples.EXAMPLE_LIMIT
    assert rows[0] == {
        "recipient_name": "EXAMPLE BUSINESS LLC",
        "recipient_city": "EXAMPLE CITY",
        "recipient_state": "NY",
        "naics_code": "541511",
        "naics_description": "CUSTOM COMPUTER PROGRAMMING SERVICES",
        "contract_award_type": "DEFINITIVE CONTRACT",
        "award_amount_usd": "123456.78",
        "awarding_agency": "Example Agency",
    }
    serialized = str(rows)
    assert "PRIVATE LINKAGE" not in serialized
    assert "DO-NOT-RETAIN" not in serialized


def test_bankruptcy_example_keeps_only_aggregate_district_rows() -> None:
    rows = [
        ["Heading"],
        ["Total", "100", "70", "10", "20", "0", "30", "20", "5", "5", "0", "70", "50", "5", "15"],
        ["     1st", "90", "60", "10", "20", "0", "25", "15", "5", "5", "0", "65", "45", "5", "15"],
        ["ME", "10", "7", "1", "2", "0", "3", "2", "1", "0", "0", "7", "5", "0", "2"],
        ["MA", "20", "14", "2", "4", "0", "6", "4", "1", "1", "0", "14", "10", "1", "3"],
        ["NH", "30", "21", "3", "6", "0", "9", "6", "2", "1", "0", "21", "15", "1", "5"],
        ["RI", "40", "28", "4", "8", "0", "12", "8", "3", "1", "0", "28", "20", "1", "7"],
    ]
    result = examples._extract_bankruptcy_examples(rows)
    assert [row["circuit_or_district"] for row in result] == ["Total", "ME", "MA", "NH", "RI"]
    assert result[0]["business_all_chapters"] == "30"
    assert result[0]["nonbusiness_all_chapters"] == "70"


def test_privacy_header_gate_rejects_forbidden_columns(tmp_path: Path) -> None:
    acceptable = tmp_path / "acceptable.csv"
    with acceptable.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["business_type", "records"])
        writer.writerow(["LLC", "1"])
    examples._validate_example_headers(acceptable)

    forbidden = tmp_path / "forbidden.csv"
    with forbidden.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["business_type", "phone"])
        writer.writerow(["LLC", "555-0100"])
    with pytest.raises(RuntimeError, match="Privacy-forbidden example columns"):
        examples._validate_example_headers(forbidden)

from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_public_data_quality",
    ROOT / "tools" / "audit_public_data_quality.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load public-data quality auditor")
quality = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = quality
SPEC.loader.exec_module(quality)


def test_fooddata_archive_profile_validates_required_relationships(tmp_path: Path) -> None:
    archive_path = tmp_path / "fooddata.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("bundle/food.csv", "fdc_id,food_category_id\n1,10\n")
        archive.writestr("bundle/food_category.csv", "id,description\n10,Fruit\n")
        archive.writestr("bundle/foundation_food.csv", "fdc_id\n1\n")
        archive.writestr("bundle/nutrient.csv", "id,name\n20,Protein\n")
        archive.writestr("bundle/food_nutrient.csv", "fdc_id,nutrient_id,amount\n1,20,3\n")
        archive.writestr("bundle/measure_unit.csv", "id,name\n30,cup\n")
        archive.writestr("bundle/food_portion.csv", "fdc_id,measure_unit_id\n1,30\n")

    metrics = quality.profile_fooddata_archive(archive_path)

    assert metrics["archive_crc_passed"] is True
    assert metrics["missing_required_members"] == []
    assert metrics["relationship_orphans"] == {
        "food_category": 0,
        "foundation_food": 0,
        "food_nutrient_food": 0,
        "food_nutrient_nutrient": 0,
        "food_portion_food": 0,
        "food_portion_measure": 0,
    }
    assert quality.artifact_failures(metrics) == []


def test_fooddata_archive_profile_fails_orphaned_relationships(tmp_path: Path) -> None:
    archive_path = tmp_path / "fooddata.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("food.csv", "fdc_id,food_category_id\n1,10\n")
        archive.writestr("food_category.csv", "id,description\n10,Fruit\n")
        archive.writestr("foundation_food.csv", "fdc_id\n1\n")
        archive.writestr("nutrient.csv", "id,name\n20,Protein\n")
        archive.writestr("food_nutrient.csv", "fdc_id,nutrient_id,amount\n1,999,3\n")
        archive.writestr("measure_unit.csv", "id,name\n30,cup\n")
        archive.writestr("food_portion.csv", "fdc_id,measure_unit_id\n1,30\n")

    metrics = quality.profile_fooddata_archive(archive_path)

    assert metrics["relationship_orphans"]["food_nutrient_nutrient"] == 1
    assert "relationship_orphans" in quality.artifact_failures(metrics)

from __future__ import annotations

import pandas as pd
import pytest
from conftest import load_skill_script

plan = load_skill_script("plan-synthetic-data", "plan.py")


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country": ["US", "CA", "US", "MX"],
            "age": [31, 42, 27, 36],
            "diagnosis": ["A", "B", "A", "C"],
            "email": ["a@example.test", "b@example.test", "c@example.test", "d@example.test"],
            "comments": ["short", "small", "brief", "tiny"],
        }
    )


def empty_assignments() -> dict[str, set[str]]:
    return {role: set() for role in plan.ROLES}


def test_policy_requires_public_columns_to_be_explicit(tmp_path) -> None:
    policy = plan.build_policy(sample_frame(), tmp_path / "data.csv", empty_assignments(), "protected")

    assert policy["privacy"]["columns"]["country"]["role"] == "protected"
    assert policy["privacy"]["columns"]["email"]["role"] == "identifier"
    assert policy["privacy"]["columns"]["diagnosis"]["role"] == "private"
    assert all(item["role"] != "public" for item in policy["planning"]["findings"])
    assert "country" in policy["planning"]["warnings"][0]


def test_explicit_roles_override_inference(tmp_path) -> None:
    assignments = empty_assignments()
    assignments["public"] = {"country"}
    assignments["private"] = {"age"}
    assignments["drop"] = {"comments"}

    policy = plan.build_policy(sample_frame(), tmp_path / "data.csv", assignments, "protected")

    assert policy["privacy"]["columns"]["country"]["role"] == "public"
    assert policy["privacy"]["columns"]["age"]["role"] == "private"
    assert policy["privacy"]["columns"]["comments"]["role"] == "drop"
    assert any("country" in warning for warning in policy["planning"]["warnings"])


def test_conflicting_explicit_roles_are_rejected(tmp_path) -> None:
    assignments = empty_assignments()
    assignments["public"] = {"country"}
    assignments["private"] = {"country"}

    with pytest.raises(ValueError, match="multiple roles"):
        plan.build_policy(sample_frame(), tmp_path / "data.csv", assignments, "protected")


def test_date_like_strings_receive_datetime_encoding(tmp_path) -> None:
    frame = pd.DataFrame({"birthdate": [f"2024-01-{day:02d}" for day in range(1, 25)]})

    policy = plan.build_policy(frame, tmp_path / "data.csv", empty_assignments(), "private")

    column = policy["privacy"]["columns"]["birthdate"]
    assert column == {"role": "private", "encoding": "TABULAR_DATETIME"}
    assert policy["planning"]["findings"][0]["encoding_decision"] == "inferred"


def test_encoding_overrides_are_validated() -> None:
    assert plan.parse_encodings(["birthdate=tabular_datetime"]) == {"birthdate": "TABULAR_DATETIME"}
    with pytest.raises(ValueError, match="unsupported encoding"):
        plan.parse_encodings(["birthdate=NOT_REAL"])


def test_user_defined_acceptance_requirements_are_parsed() -> None:
    assert plan.parse_acceptance(["max_propensity_auc=0.72"]) == {"max_propensity_auc": 0.72}
    assert plan.parse_column_requirements(["salary.max_numeric_ks=0.12"]) == {"salary": {"max_numeric_ks": 0.12}}
    assert plan.parse_acceptance(["max_mean_text_tfidf_distance=0.25"]) == {"max_mean_text_tfidf_distance": 0.25}
    assert plan.parse_column_requirements(["message.max_text_length_ks=0.2"]) == {
        "message": {"max_text_length_ks": 0.2}
    }

    with pytest.raises(ValueError, match="unsupported acceptance"):
        plan.parse_acceptance(["not_a_gate=0.5"])
    with pytest.raises(ValueError, match="between zero and one"):
        plan.parse_acceptance(["max_propensity_auc=1.5"])


def test_artifact_paths_must_not_collide(tmp_path) -> None:
    source = tmp_path / "source.csv"
    dataset = {
        "output": str(source),
        "report": str(tmp_path / "report.json"),
        "workspace": str(tmp_path / "workspace"),
    }

    with pytest.raises(ValueError, match="input=output"):
        plan.validate_artifact_paths(source, tmp_path / "policy.json", dataset)


def test_nested_json_values_are_dropped_or_rejected(tmp_path) -> None:
    frame = pd.DataFrame({"name": ["a", "b"], "metadata": [{"x": 1}, {"x": 2}]})
    policy = plan.build_policy(frame, tmp_path / "data.json", empty_assignments(), "protected")
    assert policy["privacy"]["columns"]["metadata"]["role"] == "drop"

    assignments = empty_assignments()
    assignments["private"] = {"metadata"}
    with pytest.raises(ValueError, match="flattened or assigned drop"):
        plan.build_policy(frame, tmp_path / "data.json", assignments, "protected")


def test_synthetic_reference_policy_preserves_provenance_and_warning(tmp_path) -> None:
    provenance = tmp_path / "generation.json"
    provenance.write_text("{}", encoding="utf-8")
    policy = plan.build_policy(
        sample_frame(),
        tmp_path / "synthetic.csv",
        empty_assignments(),
        "protected",
        input_kind="synthetic-reference",
    )
    plan.attach_input_provenance(policy, provenance)

    assert policy["dataset"]["input_kind"] == "synthetic-reference"
    assert policy["dataset"]["input_report"] == str(provenance)
    assert any("already synthetic" in warning for warning in policy["planning"]["warnings"])

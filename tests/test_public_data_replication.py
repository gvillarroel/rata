from __future__ import annotations

import copy
import json
import sys

import pytest
from conftest import ROOT, load_skill_script

materialize = load_skill_script("generate-synthetic-data", "materialize_spec.py")
sys.modules["materialize_spec"] = materialize
evaluate_spec = load_skill_script("generate-synthetic-data", "evaluate_spec.py")
generate = load_skill_script("generate-synthetic-data", "generate.py")

CATALOG_PATH = ROOT / "tests" / "fixtures" / "public_data_replication_specs.json"
PROFILES = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
PROFILE_BY_CATEGORY = {profile["category"]: profile for profile in PROFILES}
EXPECTED_CATEGORIES = {
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
}


def materialized_rows(category: str) -> tuple[dict, list[dict]]:
    spec = copy.deepcopy(PROFILE_BY_CATEGORY[category]["spec"])
    columns = materialize.normalize_columns(spec)
    rows = materialize.generate_rows(spec, columns, spec["rows"], spec["seed"])
    return spec, rows


def test_replication_catalog_covers_every_requested_public_data_family() -> None:
    assert len(PROFILES) == 11
    assert set(PROFILE_BY_CATEGORY) == EXPECTED_CATEGORIES
    assert all(profile["sources"] for profile in PROFILES)
    assert all(profile["spec"]["rows"] >= 2000 for profile in PROFILES)


@pytest.mark.parametrize("profile", PROFILES, ids=lambda profile: profile["category"])
def test_public_data_profile_materializes_and_passes_every_declared_constraint(profile: dict) -> None:
    spec = copy.deepcopy(profile["spec"])
    columns = materialize.normalize_columns(spec)
    rows = materialize.generate_rows(spec, columns, spec["rows"], spec["seed"])
    report = evaluate_spec.evaluate(spec, rows)

    assert report["passed"] is True, report["failed_gates"]
    assert report["failed_gates"] == []
    assert all(column["role_explicit"] for column in columns if column["role"] == "public")
    assert all(value == 0.0 for value in report["metrics"]["integer_violation_ratio"].values())
    assert all(value == 0.0 for value in report["metrics"]["numeric_type_violation_ratio"].values())
    assert all(value == 0.0 for value in report["metrics"]["pattern_violation_ratio"].values())
    assert all(value == 0.0 for value in report["metrics"]["undeclared_categorical_value_ratio"].values())
    assert all(value["invalid_combination_ratio"] == 0.0 for value in report["metrics"]["joint_distributions"].values())
    assert all(value["violation_ratio"] == 0.0 for value in report["metrics"]["derived_constraints"].values())


def test_joint_distribution_gate_rejects_valid_codes_in_invalid_combinations() -> None:
    spec, rows = materialized_rows("industry_validity")
    rows[0]["industry_description"] = "Offices of physicians"

    report = evaluate_spec.evaluate(spec, rows)

    assert report["passed"] is False
    assert "joint.classification_code_label.invalid_combination_ratio" in report["failed_gates"]
    assert report["metrics"]["joint_distributions"]["classification_code_label"]["invalid_combination_ratio"] > 0


def test_derived_constraint_gate_rejects_broken_bankruptcy_totals() -> None:
    spec, rows = materialized_rows("public_records")
    rows[0]["total_all_chapters"] += 1

    report = evaluate_spec.evaluate(spec, rows)

    assert report["passed"] is False
    assert "derived.total_all_chapters.violation_ratio" in report["failed_gates"]
    assert report["metrics"]["derived_constraints"]["total_all_chapters"]["violation_ratio"] > 0


def test_integer_and_code_pattern_gates_reject_schema_shape_drift() -> None:
    spec, rows = materialized_rows("business_population")
    rows[0]["employees"] = 12.5
    rows[0]["state_fips"] = "1"

    report = evaluate_spec.evaluate(spec, rows)

    assert report["passed"] is False
    assert "column.employees.integer_violation_ratio" in report["failed_gates"]
    assert "column.state_fips.pattern_violation_ratio" in report["failed_gates"]


def test_numeric_type_and_declared_domain_gates_reject_schema_value_drift() -> None:
    categorical_spec, categorical_rows = materialized_rows("public_companies")
    categorical_rows[0]["exchange"] = "UNKNOWN EXCHANGE"
    numeric_spec, numeric_rows = materialized_rows("transportation")
    numeric_rows[0]["records"] = "not-a-number"

    categorical_report = evaluate_spec.evaluate(categorical_spec, categorical_rows)
    numeric_report = evaluate_spec.evaluate(numeric_spec, numeric_rows)

    assert categorical_report["passed"] is False
    assert "column.exchange.undeclared_categorical_value_ratio" in categorical_report["failed_gates"]
    assert numeric_report["passed"] is False
    assert "column.records.numeric_type_violation_ratio" in numeric_report["failed_gates"]


def test_constraint_cli_preserves_a_failed_public_data_report(tmp_path, monkeypatch, capsys) -> None:
    spec, rows = materialized_rows("industry_validity")
    rows[0]["industry_description"] = "Invalid description"
    spec_path = tmp_path / "spec.json"
    candidate_path = tmp_path / "candidate.csv"
    report_path = tmp_path / "failed-constraint-report.json"
    spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    materialize.write_rows(candidate_path, list(rows[0]), rows)
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_spec.py", str(spec_path), str(candidate_path), str(report_path)],
    )

    assert evaluate_spec.main() == 2
    capsys.readouterr()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["passed"] is False
    assert report["evidence"]["spec_sha256"] == materialize.sha256_file(spec_path)
    assert "joint.classification_code_label.invalid_combination_ratio" in report["failed_gates"]


def test_constraint_cli_preserves_runtime_failure_evidence(tmp_path, monkeypatch) -> None:
    spec_path = tmp_path / "invalid-spec.json"
    candidate_path = tmp_path / "candidate.csv"
    report_path = tmp_path / "failed-runtime-report.json"
    spec_path.write_text('{"version": 2}\n', encoding="utf-8")
    candidate_path.write_text("value\n1\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_spec.py", str(spec_path), str(candidate_path), str(report_path)],
    )

    with pytest.raises(ValueError, match="spec version"):
        evaluate_spec.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["status"] == "constraint-evaluation-failed"
    assert report["evidence"]["spec_sha256"] == materialize.sha256_file(spec_path)
    assert report["evidence"]["synthetic_sha256"] == materialize.sha256_file(candidate_path)

    preserved = report_path.read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        evaluate_spec.main()
    assert report_path.read_bytes() == preserved


def test_lognormal_distribution_is_positive_and_preserves_skewed_moments() -> None:
    spec, rows = materialized_rows("historical_small_business")
    approvals = [float(row["approval_amount"]) for row in rows]
    report = evaluate_spec.evaluate(spec, rows)

    assert min(approvals) >= 150000
    assert max(approvals) > 2 * min(approvals)
    assert report["metrics"]["numeric"]["approval_amount"]["mean_relative_error"] <= 0.15
    assert report["metrics"]["numeric"]["approval_amount"]["std_relative_error"] <= 0.2


def test_invalid_joint_and_derived_contracts_fail_before_materialization() -> None:
    spec = copy.deepcopy(PROFILE_BY_CATEGORY["public_records"]["spec"])
    spec["columns"][-1]["derived"]["columns"] = ["total_all_chapters", "nonbusiness_all_chapters"]
    columns = materialize.normalize_columns(spec)
    with pytest.raises(ValueError, match="dependency cycle|depend on itself"):
        materialize.derived_contract(columns)

    spec = copy.deepcopy(PROFILE_BY_CATEGORY["industry_validity"]["spec"])
    duplicate = copy.deepcopy(spec["joint_distributions"][0])
    duplicate["name"] = "overlapping_classification"
    spec["joint_distributions"].append(duplicate)
    columns = materialize.normalize_columns(spec)
    with pytest.raises(ValueError, match="cannot overlap"):
        materialize.joint_distribution_contract(spec, columns)


def test_replication_fixture_is_documented_by_the_generation_skill() -> None:
    skill = (ROOT / "skills" / "generate-synthetic-data" / "SKILL.md").read_text(encoding="utf-8")
    reference = ROOT / "skills" / "generate-synthetic-data" / "references" / "public-data-replication.md"

    assert "public-data-replication.md" in skill
    assert reference.is_file()


@pytest.mark.parametrize("profile", PROFILES, ids=lambda profile: profile["category"])
def test_real_generator_replicates_public_data_contract_end_to_end(
    profile: dict, tmp_path, monkeypatch, capsys
) -> None:
    spec = copy.deepcopy(profile["spec"])
    columns = materialize.normalize_columns(spec)
    rows = materialize.generate_rows(spec, columns, spec["rows"], spec["seed"])
    root = tmp_path / profile["category"]
    root.mkdir()
    spec_path = root / "aggregate-spec.json"
    proxy_path = root / "aggregate-proxy.csv"
    materialization_report = root / "materialization-report.json"
    output_path = root / "synthetic.csv"
    generation_report = root / "generation-report.json"
    workspace = root / "workspace"
    policy_path = root / "policy.json"
    spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    materialization_report.write_text('{"passed": true}\n', encoding="utf-8")
    materialize.write_rows(proxy_path, [column["name"] for column in columns], rows)
    policy = materialize.build_policy(
        spec,
        spec_path,
        proxy_path,
        materialization_report,
        output_path,
        generation_report,
        workspace,
        columns,
        spec["rows"],
        spec["seed"],
    )
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["generate.py", str(policy_path)])

    assert generate.main() == 0
    capsys.readouterr()
    output_rows = evaluate_spec.load_rows(output_path)
    constraint_report = evaluate_spec.evaluate(spec, output_rows)
    generated_report = json.loads(generation_report.read_text(encoding="utf-8"))

    assert constraint_report["passed"] is True, constraint_report["failed_gates"]
    assert generated_report["input_provenance"]["kind"] == "aggregate-proxy"
    assert generated_report["rows"] == spec["rows"]
    for column in columns:
        if column["role"] != "identifier":
            continue
        source_values = {row[column["name"]] for row in rows}
        generated_values = {row[column["name"]] for row in output_rows}
        assert source_values.isdisjoint(generated_values)
        assert len(generated_values) == spec["rows"]

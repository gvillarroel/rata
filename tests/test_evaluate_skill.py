from __future__ import annotations

import json
import sys

import pandas as pd
import pytest
from conftest import load_skill_script

evaluate = load_skill_script("evaluate-synthetic-data", "evaluate.py")


def frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    original = pd.DataFrame(
        {
            "country": ["US", "US", "CA", "CA", "MX", "MX"] * 5,
            "age": list(range(20, 50)),
            "diagnosis": ["common-a", "common-b"] * 15,
            "email": [f"real-{index}@example.test" for index in range(30)],
            "secret": [f"secret-{index}" for index in range(30)],
        }
    )
    synthetic = pd.DataFrame(
        {
            "country": ["US", "CA", "MX"] * 10,
            "age": list(range(21, 51)),
            "diagnosis": ["common-b", "common-a"] * 15,
            "email": [f"syn-{index}" for index in range(30)],
        }
    )
    return original, synthetic


def test_privacy_metrics_respect_column_roles() -> None:
    original, synthetic = frames()

    protected = evaluate.rare_value_replay(original, synthetic, ["age"], threshold=1)
    private = evaluate.rare_value_replay(original, synthetic, ["diagnosis"], threshold=1)
    identifier = evaluate.value_overlap(original["email"], synthetic["email"])

    assert protected["ratio"] > 0
    assert private["ratio"] == 0
    assert identifier == 0


def test_quality_metrics_and_propensity_are_available() -> None:
    original, synthetic = frames()
    columns = ["country", "age", "diagnosis"]

    distributions = evaluate.distribution_metrics(original, synthetic, columns)
    correlations = evaluate.correlation_metrics(original, synthetic, columns)
    auc = evaluate.propensity_auc(original, synthetic, columns, seed=42)

    assert distributions["mean_numeric_ks"] is not None
    assert distributions["mean_categorical_tv"] is not None
    assert correlations["mean_abs_delta"] is None
    assert auc is not None
    assert 0.5 <= auc <= 1.0


def test_dp_evidence_requires_valid_checkpoint() -> None:
    policy = {"privacy": {"dp": {"max_epsilon": 8.0, "delta": 0.00001}}}
    report = {"stages": [{"stage": "private", "dp_checkpoint": {"epsilon": 4.2, "delta": 0.00001}}]}

    assert evaluate.dp_evidence(policy, report, True)["valid"] is True
    assert evaluate.dp_evidence(policy, None, True)["valid"] is False
    assert evaluate.dp_evidence(policy, None, False)["valid"] is True


def test_datetime_encodings_are_compared_as_continuous_values() -> None:
    original = pd.DataFrame(
        {
            "birthdate": pd.Series(
                [f"2020-01-{day:02d}" for day in range(1, 21)],
                dtype="string",
            )
        }
    )
    synthetic = pd.DataFrame({"birthdate": [f"2020-01-{day:02d}" for day in range(2, 22)]})

    original_normalized = evaluate.normalize_datetime_columns(original, {"birthdate"})
    synthetic_normalized = evaluate.normalize_datetime_columns(synthetic, {"birthdate"})
    metrics = evaluate.distribution_metrics(
        original_normalized,
        synthetic_normalized,
        ["birthdate"],
    )

    assert metrics["numeric_ks"]["birthdate"] < 0.1
    assert metrics["categorical_tv"] == {}

    differently_formatted = pd.DataFrame({"birthdate": ["1/1/2020", "2020-01-02"]})
    formatted_normalized = evaluate.normalize_datetime_columns(differently_formatted, {"birthdate"})
    replay = evaluate.rare_value_replay(
        original_normalized,
        formatted_normalized,
        ["birthdate"],
        threshold=1,
    )
    assert replay["ratio"] == 1.0


def test_character_encoding_uses_text_metrics_instead_of_exact_categories() -> None:
    original = pd.DataFrame(
        {
            "message": [
                "fast helpful support",
                "clear billing answer",
                "simple account setup",
            ]
            * 10
        }
    )
    synthetic = pd.DataFrame(
        {
            "message": [
                "support helpful fast",
                "answer billing clear",
                "setup account simple",
            ]
            * 10
        }
    )

    distributions = evaluate.distribution_metrics(original, synthetic, ["message"], {"message"})
    text = evaluate.text_metrics(original, synthetic, ["message"])

    assert distributions["categorical_tv"] == {}
    assert text["mean_length_ks"] == 0.0
    assert text["mean_tfidf_centroid_distance"] < 0.2
    assert text["per_column"]["message"]["exact_value_replay_ratio"] == 0.0
    assert text["per_column"]["message"]["max_nearest_tfidf_similarity"] > 0.8


def test_policy_cannot_reference_unknown_source_columns() -> None:
    original, _ = frames()
    policy = {
        "privacy": {
            "default_role": "protected",
            "columns": {"not_in_source": {"role": "private"}},
        }
    }

    with pytest.raises(ValueError, match="unknown columns"):
        evaluate.resolve_roles(original, policy)


def test_generation_report_is_bound_to_policy_input_and_output(tmp_path) -> None:
    original = tmp_path / "original.csv"
    synthetic = tmp_path / "synthetic.csv"
    original.write_text("value\n1\n", encoding="utf-8")
    synthetic.write_text("value\n2\n", encoding="utf-8")
    policy = {
        "version": 1,
        "quality": {"profile": "fast"},
        "privacy": {"default_role": "protected", "columns": {"value": {"role": "private"}}},
    }
    roles = {"public": [], "protected": [], "private": ["value"], "identifier": [], "drop": []}
    report = {
        "schema_version": 1,
        "method": "staged-column-privacy-tabular-argn",
        "engine": {"package": "mostlyai-engine"},
        "rows": 1,
        "roles": roles,
        "evidence": {
            "policy_fingerprint": evaluate.generation_policy_fingerprint(policy),
            "input_sha256": evaluate.sha256_file(original),
            "output_sha256": evaluate.sha256_file(synthetic),
        },
    }

    binding = evaluate.generation_report_binding(policy, report, original, synthetic, 1, roles, required=True)
    assert binding["valid"] is True

    synthetic.write_text("value\n3\n", encoding="utf-8")
    tampered = evaluate.generation_report_binding(policy, report, original, synthetic, 1, roles, required=True)
    assert tampered["valid"] is False
    assert "output_sha256" in tampered["failures"]


def test_missing_released_columns_write_a_failed_report(tmp_path, monkeypatch, capsys) -> None:
    original, synthetic = frames()
    synthetic = synthetic.drop(columns=["age"])
    original_path = tmp_path / "original.csv"
    synthetic_path = tmp_path / "synthetic.csv"
    policy_path = tmp_path / "policy.json"
    report_path = tmp_path / "evaluation.json"
    original.to_csv(original_path, index=False)
    synthetic.to_csv(synthetic_path, index=False)
    policy = {
        "version": 1,
        "dataset": {"seed": 42},
        "privacy": {
            "default_role": "protected",
            "rare_value_threshold": 1,
            "columns": {
                "country": {"role": "public"},
                "age": {"role": "protected"},
                "diagnosis": {"role": "protected"},
                "email": {"role": "identifier"},
                "secret": {"role": "drop"},
            },
        },
        "acceptance": {"columns": {"age": {"max_numeric_ks": 0.1}}},
    }
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate.py", str(original_path), str(synthetic_path), str(policy_path), str(report_path)],
    )

    assert evaluate.main() == 2
    capsys.readouterr()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema"]["missing_released_columns"] == ["age"]
    assert "released_columns_present" in report["failed_gates"]
    assert "column.age.max_numeric_ks" in report["failed_gates"]


def test_evaluation_refuses_to_overwrite_existing_evidence(tmp_path, monkeypatch) -> None:
    report_path = tmp_path / "evaluation.json"
    report_path.write_text('{"preserved": true}\n', encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate.py",
            str(tmp_path / "original.csv"),
            str(tmp_path / "synthetic.csv"),
            str(tmp_path / "policy.json"),
            str(report_path),
        ],
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        evaluate.main()
    assert json.loads(report_path.read_text(encoding="utf-8")) == {"preserved": True}

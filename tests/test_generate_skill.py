from __future__ import annotations

import json
import sys

import pandas as pd
import pytest
from conftest import load_skill_script

generate = load_skill_script("generate-synthetic-data", "generate.py")


def policy() -> dict:
    return {
        "version": 1,
        "quality": {"profile": "fast", "max_epochs": 2, "max_training_minutes": 0.5},
        "privacy": {
            "default_role": "protected",
            "columns": {
                "country": {"role": "public"},
                "age": {"role": "protected"},
                "salary": {"role": "private", "encoding": "TABULAR_NUMERIC_AUTO"},
                "email": {"role": "identifier"},
                "secret": {"role": "drop"},
            },
            "dp": {"enabled": True},
        },
    }


def test_resolve_roles_and_quality_settings() -> None:
    frame = pd.DataFrame(columns=["country", "age", "salary", "email", "secret"])

    roles = generate.resolve_roles(frame, policy())
    settings = generate.quality_settings(policy())

    assert roles == {
        "public": ["country"],
        "protected": ["age"],
        "private": ["salary"],
        "identifier": ["email"],
        "drop": ["secret"],
    }
    assert settings["max_epochs"] == 2
    assert settings["max_training_minutes"] == 0.5
    assert generate.encoding_types(policy(), ["country", "salary"]) == {"salary": "TABULAR_NUMERIC_AUTO"}


def test_surrogates_are_deterministic_unique_and_unlinked() -> None:
    first = generate.surrogate_values(20, 42, "syn", "uuid")
    second = generate.surrogate_values(20, 42, "syn", "uuid")

    assert first == second
    assert len(set(first)) == 20
    assert all(value.startswith("syn-") for value in first)


def test_dp_checkpoint_prefers_checkpoint_row(tmp_path) -> None:
    path = tmp_path / "ModelStore" / "model-data"
    path.mkdir(parents=True)
    pd.DataFrame(
        [
            {"is_checkpoint": 1, "dp_eps": 2.1, "dp_delta": 0.00001},
            {"is_checkpoint": 0, "dp_eps": 3.0, "dp_delta": 0.00001},
        ]
    ).to_csv(path / "progress-messages.csv", index=False)

    assert generate.read_dp_checkpoint(tmp_path) == {"epsilon": 2.1, "delta": 0.00001}
    assert generate.validate_dp_checkpoint(
        {"epsilon": 2.1, "delta": 0.00001}, {"max_epsilon": 8.0, "delta": 0.00001}
    ) == {"epsilon": 2.1, "delta": 0.00001}
    with pytest.raises(RuntimeError, match="epsilon"):
        generate.validate_dp_checkpoint({"epsilon": -1.0, "delta": 0.00001}, {"max_epsilon": 8.0, "delta": 0.00001})
    with pytest.raises(RuntimeError, match="delta"):
        generate.validate_dp_checkpoint({"epsilon": 2.1, "delta": float("inf")}, {"max_epsilon": 8.0, "delta": 0.00001})


def test_load_policy_rejects_unknown_version(tmp_path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"version": 2, "privacy": {"columns": {}}}), encoding="utf-8")

    try:
        generate.load_policy(path)
    except ValueError as error:
        assert "version" in str(error)
    else:
        raise AssertionError("expected policy validation failure")


def test_invalid_semantic_encoding_is_rejected() -> None:
    invalid = policy()
    invalid["privacy"]["columns"]["salary"]["encoding"] = "NOT_REAL"

    with pytest.raises(ValueError, match="invalid encoding"):
        generate.encoding_types(invalid, ["salary"])


def test_invalid_dp_parameters_and_path_collisions_are_rejected(tmp_path) -> None:
    invalid = policy()
    invalid["privacy"]["dp"]["delta"] = 1.0
    roles = {
        "public": ["country"],
        "protected": ["age"],
        "private": ["salary"],
        "identifier": ["email"],
        "drop": ["secret"],
    }

    with pytest.raises(ValueError, match="delta"):
        generate.validate_policy_parameters(invalid, roles)
    invalid_quality = policy()
    invalid_quality["quality"]["max_epochs"] = 1.5
    with pytest.raises(ValueError, match="positive integer"):
        generate.quality_settings(invalid_quality)
    with pytest.raises(ValueError, match="input=output"):
        generate.validate_artifact_paths(
            tmp_path / "data.csv",
            tmp_path / "data.csv",
            tmp_path / "report.json",
            tmp_path / "workspace",
        )


def test_dry_run_reports_workspace_stages_and_dp_configuration(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "source.csv"
    pd.DataFrame(
        {
            "country": ["US", "CA"],
            "age": [30, 40],
            "salary": [100.0, 200.0],
            "email": ["a@example.test", "b@example.test"],
            "secret": ["x", "y"],
        }
    ).to_csv(source, index=False)
    configured = policy()
    configured["dataset"] = {
        "input": str(source),
        "output": str(tmp_path / "synthetic.csv"),
        "report": str(tmp_path / "generation.json"),
        "workspace": str(tmp_path / "workspace"),
        "rows": 2,
        "seed": 42,
    }
    configured["privacy"]["dp"].update(
        {
            "max_epsilon": 8.0,
            "delta": 0.00001,
            "noise_multiplier": 1.5,
            "max_grad_norm": 1.0,
            "value_protection_epsilon": 1.0,
        }
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(configured), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["generate.py", str(policy_path), "--dry-run"])

    assert generate.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert output["workspace_root"] == str(tmp_path / "workspace")
    assert output["dp_configuration"]["max_epsilon"] == 8.0
    assert "private-dp-model" in output["planned_stages"]


def test_aggregate_proxy_dry_run_binds_spec_provenance(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "proxy.csv"
    pd.DataFrame({"age": [30, 40], "salary": [100.0, 200.0]}).to_csv(source, index=False)
    spec = tmp_path / "spec.json"
    spec.write_text('{"version": 1}', encoding="utf-8")
    configured = policy()
    configured["dataset"] = {
        "input": str(source),
        "input_kind": "aggregate-proxy",
        "aggregate_spec": str(spec),
        "output": str(tmp_path / "synthetic.csv"),
        "report": str(tmp_path / "generation.json"),
        "workspace": str(tmp_path / "workspace"),
        "rows": 2,
        "seed": 42,
    }
    configured["privacy"]["columns"] = {
        "age": {"role": "protected"},
        "salary": {"role": "protected"},
    }
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(configured), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["generate.py", str(policy_path), "--dry-run"])

    assert generate.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["input_provenance"]["kind"] == "aggregate-proxy"
    assert output["input_provenance"]["aggregate_spec_sha256"] == generate.sha256_file(spec)


def test_staged_generation_never_trains_on_identifier_or_drop_columns(tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "source.csv"
    frame = pd.DataFrame(
        {
            "country": ["US", "CA"] * 10,
            "age": list(range(20, 40)),
            "salary": [float(value * 1000) for value in range(20, 40)],
            "email": [f"real-{index}@example.test" for index in range(20)],
            "secret": [f"secret-{index}" for index in range(20)],
        }
    )
    frame.to_csv(source, index=False)
    configured = policy()
    configured["dataset"] = {
        "input": str(source),
        "output": str(tmp_path / "synthetic.csv"),
        "report": str(tmp_path / "generation.json"),
        "workspace": str(tmp_path / "workspace"),
        "rows": 20,
        "seed": 42,
    }
    configured["privacy"]["dp"].update(
        {
            "max_epsilon": 8.0,
            "delta": 0.00001,
            "noise_multiplier": 1.5,
            "max_grad_norm": 1.0,
            "value_protection_epsilon": 1.0,
        }
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(configured), encoding="utf-8")
    calls = []

    def fake_stage_model(
        name,
        training_data,
        seed_data,
        generated_columns,
        output,
        workspace,
        settings,
        seed,
        dp_config,
        encoding_types,
        verbose,
    ):
        calls.append(
            {
                "name": name,
                "training_columns": list(training_data.columns),
                "seed_columns": list(seed_data.columns) if seed_data is not None else [],
                "generated_columns": generated_columns,
                "dp": dp_config is not None,
            }
        )
        for offset, column in enumerate(generated_columns):
            output[column] = [index + offset for index in range(len(output))]
        return {
            "stage": name,
            "training_columns": list(training_data.columns),
            "generated_columns": generated_columns,
            "workspace": str(workspace),
            "train_seconds": 0.0,
            "sample_seconds": 0.0,
            "dp_checkpoint": {"epsilon": 2.0, "delta": 0.00001} if dp_config is not None else None,
        }

    monkeypatch.setattr(generate, "stage_model", fake_stage_model)
    monkeypatch.setattr(generate, "version", lambda _package: "test")
    monkeypatch.setattr(sys, "argv", ["generate.py", str(policy_path)])

    assert generate.main() == 0
    capsys.readouterr()
    synthetic = pd.read_csv(tmp_path / "synthetic.csv")
    report = json.loads((tmp_path / "generation.json").read_text(encoding="utf-8"))
    assert calls == [
        {
            "name": "protected",
            "training_columns": ["country", "age"],
            "seed_columns": ["country"],
            "generated_columns": ["age"],
            "dp": False,
        },
        {
            "name": "private",
            "training_columns": ["country", "age", "salary"],
            "seed_columns": ["country", "age"],
            "generated_columns": ["salary"],
            "dp": True,
        },
    ]
    assert "secret" not in synthetic
    assert synthetic["email"].is_unique
    assert not set(synthetic["email"]) & set(frame["email"])
    assert report["evidence"]["policy_fingerprint"] == generate.generation_policy_fingerprint(configured)


def test_generation_failure_writes_new_non_overwriting_evidence(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.csv"
    pd.DataFrame(
        {
            "country": ["US", "CA"],
            "age": [30, 40],
            "salary": [100.0, 200.0],
            "email": ["a@example.test", "b@example.test"],
            "secret": ["x", "y"],
        }
    ).to_csv(source, index=False)
    configured = policy()
    configured["dataset"] = {
        "input": str(source),
        "output": str(tmp_path / "synthetic.csv"),
        "report": str(tmp_path / "generation.json"),
        "workspace": str(tmp_path / "workspace"),
        "rows": 2,
        "seed": 42,
    }
    configured["privacy"]["dp"]["delta"] = 1.0
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(configured), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["generate.py", str(policy_path)])

    with pytest.raises(ValueError, match="delta"):
        generate.main()
    failure = json.loads((tmp_path / "generation.json").read_text(encoding="utf-8"))
    assert failure["passed"] is False
    assert failure["status"] == "generation-failed"
    assert failure["error"]["type"] == "ValueError"
    assert "message" not in failure["error"]
    assert len(failure["error"]["message_sha256"]) == 64
    assert failure["evidence"]["policy_sha256"] == generate.sha256_file(policy_path)
    assert failure["evidence"]["input_sha256"] == generate.sha256_file(source)

    preserved = (tmp_path / "generation.json").read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        generate.main()
    assert (tmp_path / "generation.json").read_bytes() == preserved

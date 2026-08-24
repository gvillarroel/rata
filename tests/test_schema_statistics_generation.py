from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ROOT, load_skill_script

materialize = load_skill_script("generate-synthetic-data", "materialize_spec.py")


def aggregate_spec(rows: int = 800) -> dict:
    return {
        "version": 1,
        "rows": rows,
        "seed": 73,
        "columns": [
            {
                "name": "age",
                "type": "integer",
                "role": "protected",
                "distribution": {"kind": "normal", "mean": 45, "std": 11},
                "missing_rate": 0.02,
            },
            {
                "name": "income",
                "type": "number",
                "role": "private",
                "distribution": {"kind": "normal", "mean": 72000, "std": 15000},
            },
            {
                "name": "region",
                "type": "categorical",
                "role": "public",
                "values": {"north": 0.45, "south": 0.35, "west": 0.2},
            },
            {"name": "customer_id", "type": "identifier", "role": "identifier"},
        ],
        "correlations": {"columns": ["age", "income"], "matrix": [[1.0, 0.6], [0.6, 1.0]]},
    }


def run_materializer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spec: dict | None = None) -> dict[str, Path]:
    paths = {
        "spec": tmp_path / "spec.json",
        "proxy": tmp_path / "proxy.csv",
        "policy": tmp_path / "policy.json",
        "materialization": tmp_path / "materialization.json",
        "output": tmp_path / "synthetic.csv",
        "generation": tmp_path / "generation.json",
        "workspace": tmp_path / "workspace",
    }
    paths["spec"].write_text(json.dumps(spec or aggregate_spec()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "materialize_spec.py",
            str(paths["spec"]),
            str(paths["proxy"]),
            str(paths["policy"]),
            "--materialization-report",
            str(paths["materialization"]),
            "--output",
            str(paths["output"]),
            "--report",
            str(paths["generation"]),
            "--workspace",
            str(paths["workspace"]),
        ],
    )
    assert materialize.main() == 0
    return paths


def test_materialize_schema_statistics_creates_proxy_policy_and_provenance(tmp_path, monkeypatch) -> None:
    paths = run_materializer(tmp_path, monkeypatch)

    policy = json.loads(paths["policy"].read_text(encoding="utf-8"))
    report = json.loads(paths["materialization"].read_text(encoding="utf-8"))
    with paths["proxy"].open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 800
    assert policy["dataset"]["input_kind"] == "aggregate-proxy"
    assert policy["dataset"]["aggregate_spec"] == str(paths["spec"])
    assert policy["privacy"]["columns"]["income"]["role"] == "private"
    assert policy["privacy"]["columns"]["customer_id"]["role"] == "identifier"
    assert len({row["customer_id"] for row in rows}) == len(rows)
    assert report["method"] == "aggregate-constraint-proxy-materialization"
    assert report["evidence"]["spec_sha256"] == materialize.sha256_file(paths["spec"])


def test_missing_role_defaults_to_protected_and_public_must_be_explicit(tmp_path, monkeypatch) -> None:
    spec = aggregate_spec(50)
    spec["columns"][0].pop("role")
    paths = run_materializer(tmp_path, monkeypatch, spec)
    policy = json.loads(paths["policy"].read_text(encoding="utf-8"))

    assert policy["privacy"]["columns"]["age"]["role"] == "protected"
    assert policy["planning"]["findings"][0]["decision"] == "conservative-default"


def test_invalid_correlation_matrix_is_rejected() -> None:
    spec = aggregate_spec(50)
    spec["correlations"]["matrix"] = [[1.0, 1.4], [1.4, 1.0]]
    columns = materialize.normalize_columns(spec)

    with pytest.raises(ValueError, match="between -1 and 1"):
        materialize.correlation_contract(spec, columns)


def test_failed_materialization_writes_bound_non_overwriting_report(tmp_path, monkeypatch) -> None:
    spec = aggregate_spec(50)
    spec["correlations"]["matrix"] = [[1.0, 1.4], [1.4, 1.0]]
    paths = {
        "spec": tmp_path / "spec.json",
        "proxy": tmp_path / "proxy.csv",
        "policy": tmp_path / "policy.json",
        "materialization": tmp_path / "materialization.json",
        "output": tmp_path / "synthetic.csv",
        "generation": tmp_path / "generation.json",
        "workspace": tmp_path / "workspace",
    }
    paths["spec"].write_text(json.dumps(spec), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "materialize_spec.py",
            str(paths["spec"]),
            str(paths["proxy"]),
            str(paths["policy"]),
            "--materialization-report",
            str(paths["materialization"]),
            "--output",
            str(paths["output"]),
            "--report",
            str(paths["generation"]),
            "--workspace",
            str(paths["workspace"]),
        ],
    )

    with pytest.raises(ValueError, match="between -1 and 1"):
        materialize.main()
    failure = json.loads(paths["materialization"].read_text(encoding="utf-8"))
    assert failure["passed"] is False
    assert failure["status"] == "materialization-failed"
    assert failure["evidence"]["spec_sha256"] == materialize.sha256_file(paths["spec"])

    preserved = paths["materialization"].read_bytes()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        materialize.main()
    assert paths["materialization"].read_bytes() == preserved


def test_constraint_evaluator_accepts_materialized_statistics(tmp_path, monkeypatch) -> None:
    paths = run_materializer(tmp_path, monkeypatch)
    evaluation = tmp_path / "constraint-evaluation.json"
    script = ROOT / "skills" / "generate-synthetic-data" / "scripts" / "evaluate_spec.py"

    completed = subprocess.run(
        [sys.executable, str(script), str(paths["spec"]), str(paths["proxy"]), str(evaluation)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    report = json.loads(evaluation.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["metrics"]["correlations"]["age|income"]["delta"] <= 0.2

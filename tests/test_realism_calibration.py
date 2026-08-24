from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import load_skill_script

materialize = load_skill_script("generate-synthetic-data", "materialize_spec.py")
sys.modules["materialize_spec"] = materialize
evaluate_spec = load_skill_script("generate-synthetic-data", "evaluate_spec.py")
generate = load_skill_script("generate-synthetic-data", "generate.py")


def realism_spec(rows: int = 2000) -> dict:
    first_names = {f"First{index:03d}": 201 - index for index in range(1, 151)}
    surnames = {f"Last{index:03d}": 251 - index for index in range(1, 151)}
    street_names = {f"Street{index:03d}": 221 - index for index in range(1, 151)}
    return {
        "version": 1,
        "rows": rows,
        "seed": 91,
        "columns": [
            {"name": "city", "type": "string", "role": "public", "values": {"Austin": 6, "Boston": 4}},
            {"name": "state", "type": "categorical", "role": "public", "values": {"TX": 6, "MA": 4}},
            {
                "name": "zip_code",
                "type": "string",
                "role": "public",
                "values": {"78701": 6, "02108": 4},
                "pattern": "^\\d{5}$",
            },
            {
                "name": "summary",
                "type": "string",
                "role": "public",
                "generator": {
                    "kind": "token_sequence",
                    "tokens": {"account": 20, "payment": 16, "credit": 12, "company": 9, "report": 7},
                    "lengths": {"8": 4, "12": 5, "20": 1},
                },
            },
            {
                "name": "person_name",
                "type": "identifier",
                "role": "identifier",
                "surrogate": {
                    "strategy": "weighted_template",
                    "template": "{first_name} {surname}",
                    "components": {
                        "first_name": {"kind": "choice", "values": first_names},
                        "surname": {"kind": "choice", "values": surnames},
                    },
                },
            },
            {
                "name": "address",
                "type": "identifier",
                "role": "identifier",
                "surrogate": {
                    "strategy": "weighted_template",
                    "template": "{house_number} {street_name} {suffix}, {city}, {state} {zip_code}",
                    "components": {
                        "house_number": {"kind": "integer", "min": 100, "max": 9999},
                        "street_name": {"kind": "choice", "values": street_names},
                        "suffix": {"kind": "choice", "values": {"St": 5, "Ave": 3, "Rd": 2}},
                    },
                },
            },
        ],
        "joint_distributions": [
            {
                "name": "city_state_zip",
                "columns": ["city", "state", "zip_code"],
                "rows": [
                    {"values": {"city": "Austin", "state": "TX", "zip_code": "78701"}, "weight": 6},
                    {"values": {"city": "Boston", "state": "MA", "zip_code": "02108"}, "weight": 4},
                ],
            }
        ],
    }


def generate_final(spec: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    columns = materialize.normalize_columns(spec)
    proxy_rows = materialize.generate_rows(spec, columns, spec["rows"], spec["seed"])
    spec_path = tmp_path / "spec.json"
    proxy_path = tmp_path / "proxy.csv"
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "synthetic.csv"
    generation_report = tmp_path / "generation.json"
    materialization_report = tmp_path / "materialization.json"
    workspace = tmp_path / "workspace"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    materialization_report.write_text('{"passed": true}\n', encoding="utf-8")
    materialize.write_rows(proxy_path, [column["name"] for column in columns], proxy_rows)
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
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["generate.py", str(policy_path)])
    assert generate.main() == 0
    return evaluate_spec.load_rows(output_path)


def test_weighted_name_address_and_text_calibration_passes_end_to_end(tmp_path, monkeypatch) -> None:
    spec = realism_spec()
    rows = generate_final(spec, tmp_path, monkeypatch)
    report = evaluate_spec.evaluate(spec, rows)

    assert report["passed"] is True, report["failed_gates"]
    assert len({row["person_name"] for row in rows}) == spec["rows"]
    assert len({row["address"] for row in rows}) == spec["rows"]
    assert report["metrics"]["identifier_templates"]["address"]["template_violation_ratio"] == 0.0
    assert report["metrics"]["text_distributions"]["summary"]["token_tv"] <= 0.15


def test_realism_gates_reject_language_and_geography_drift(tmp_path, monkeypatch) -> None:
    spec = realism_spec()
    rows = generate_final(spec, tmp_path, monkeypatch)
    drifted = copy.deepcopy(rows)
    drifted[0]["address"] = drifted[0]["address"].replace(drifted[0]["city"], "Wrong City")
    for row in drifted:
        row["summary"] = "Unknown unknown unknown unknown unknown unknown unknown unknown."
    report = evaluate_spec.evaluate(spec, drifted)

    assert report["passed"] is False
    assert "column.address.identifier_template_violation_ratio" in report["failed_gates"]
    assert "column.summary.text_token_tv" in report["failed_gates"]


def test_realism_contract_rejects_identifier_chaining_and_invalid_lengths() -> None:
    spec = realism_spec(20)
    spec["columns"][-1]["surrogate"]["template"] += " ({person_name})"
    with pytest.raises(ValueError, match="cannot reference identifier"):
        materialize.normalize_columns(spec)

    spec = realism_spec(20)
    spec["columns"][3]["generator"]["lengths"] = {"0": 1}
    with pytest.raises(ValueError, match="1 to 1000"):
        materialize.normalize_columns(spec)

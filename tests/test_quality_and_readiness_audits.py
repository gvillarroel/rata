from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

from conftest import ROOT


def load_tool(name: str):
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


quality = load_tool("audit_public_data_quality")
readiness = load_tool("audit_evaluation_readiness")


def test_delimited_quality_profile_checks_types_patterns_grain_and_totals() -> None:
    rule = quality.DelimitedRule(
        required=("state", "code", "records"),
        numeric=("records",),
        patterns=(("state", r"[A-Z]{2}"), ("code", r"\d{4}")),
        dimensions=("state", "code"),
        weight="records",
    )
    valid = io.StringIO("state,code,records\nCA,0123,10\nNY,4567,5\n")

    metrics = quality.profile_delimited(valid, rule)

    assert quality.artifact_failures(metrics, rule) == []
    assert metrics["rows_scanned"] == 2
    assert metrics["weight_total"] == 15


def test_delimited_quality_profile_rejects_invalid_values_and_duplicate_grain() -> None:
    rule = quality.DelimitedRule(
        required=("state", "code", "records"),
        numeric=("records",),
        patterns=(("state", r"[A-Z]{2}"), ("code", r"\d{4}")),
        dimensions=("state", "code"),
        weight="records",
    )
    invalid = io.StringIO("state,code,records\nCalifornia,123,-1\nCalifornia,123,not-numeric\n")

    metrics = quality.profile_delimited(invalid, rule)
    failures = quality.artifact_failures(metrics, rule)

    assert "pattern_violations" in failures
    assert "numeric_parse_violations" in failures
    assert "numeric_negative_values" in failures
    assert "duplicate_dimension_rows" in failures
    assert "aggregate_weight_total" in failures


def test_matrix_readiness_distinguishes_compute_capacity_from_candidate_quality(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    path.write_text(
        json.dumps(
            {
                "captured_utc": "2026-08-22T00:00:00+00:00",
                "passed": False,
                "scenarios": [
                    {
                        "id": "tabular-text",
                        "modality": "tabular+text",
                        "commands": {
                            "plan": {"exit_code": 0},
                            "dry_run": {"exit_code": 0},
                            "generate": {"exit_code": 0, "duration_seconds": 12.5},
                            "negative_control": {"exit_code": 2},
                        },
                        "candidate_metrics": {"passed": False, "failed_gates": ["mean_text_length_ks"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    evidence = readiness.matrix_evidence(path)

    assert evidence["capacity_passed"] is True
    assert evidence["quality_passed"] is False
    assert evidence["total_generation_seconds"] == 12.5
    assert evidence["scenarios"][0]["failed_gates"] == ["mean_text_length_ks"]


def test_missing_matrix_is_not_hardware_readiness_evidence(tmp_path: Path) -> None:
    evidence = readiness.matrix_evidence(tmp_path / "missing.json")

    assert evidence["available"] is False
    assert evidence["capacity_passed"] is False

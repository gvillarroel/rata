"""Audit hardware, runtime, and benchmark readiness for Rata skill evaluation."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "datasets" / "public-data" / "evaluation-readiness" / "matrix" / "summary.json"
DEFAULT_JSON = ROOT / "datasets" / "public-data" / "evaluation-readiness" / "readiness.json"
DEFAULT_MARKDOWN = ROOT / "datasets" / "public-data" / "evaluation-readiness" / "readiness.md"
GIB = 1024**3
MIN_LOGICAL_CPUS = 8
MIN_MEMORY_BYTES = 16 * GIB
MIN_FREE_DISK_BYTES = 20 * GIB
REQUIRED_PACKAGES = ("mostlyai-engine", "numpy", "pandas", "scikit-learn", "scipy")


class MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("available_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended_virtual", ctypes.c_ulonglong),
    ]


def memory_bytes() -> tuple[int | None, int | None]:
    if sys.platform == "win32":
        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.total_physical), int(status.available_physical)
        return None, None
    if hasattr(os, "sysconf"):
        try:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            total = page_size * int(os.sysconf("SC_PHYS_PAGES"))
            available = page_size * int(os.sysconf("SC_AVPHYS_PAGES"))
            return total, available
        except (OSError, ValueError):
            return None, None
    return None, None


def command_result(command: list[str], timeout: int = 15) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "error": str(error)}
    return {
        "available": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def gpu_inventory() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "required": False, "devices": []}
    result = command_result(
        [
            executable,
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    devices = []
    if result.get("available"):
        for line in result["stdout"].splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) == 4:
                devices.append(
                    {
                        "name": parts[0],
                        "memory_total_mib": int(parts[1]),
                        "memory_free_mib": int(parts[2]),
                        "driver_version": parts[3],
                    }
                )
    return {"available": bool(devices), "required": False, "devices": devices, "probe": result}


def docker_inventory() -> dict[str, Any]:
    executable = shutil.which("docker")
    if not executable:
        return {"available": False, "executable": None, "reason": "docker executable is not on PATH"}
    result = command_result([executable, "version", "--format", "{{json .Server}}"], timeout=20)
    return {
        "available": bool(result.get("available")),
        "executable": executable,
        "probe": result,
        "reason": None if result.get("available") else "docker server is unavailable",
    }


def package_inventory() -> dict[str, Any]:
    installed: dict[str, str | None] = {}
    for package in REQUIRED_PACKAGES:
        try:
            installed[package] = version(package)
        except PackageNotFoundError:
            installed[package] = None
    return {"installed": installed, "passed": all(installed.values())}


def matrix_evidence(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "available": False,
            "capacity_passed": False,
            "quality_passed": None,
            "reason": f"matrix summary does not exist: {path}",
        }
    summary = json.loads(path.read_text(encoding="utf-8"))
    scenarios = summary.get("scenarios", [])
    capacity_checks = []
    negative_checks = []
    durations = []
    scenario_results = []
    for scenario in scenarios:
        commands = scenario.get("commands", {})
        capacity = all(commands.get(name, {}).get("exit_code") == 0 for name in ("plan", "dry_run", "generate"))
        negative = commands.get("negative_control", {}).get("exit_code") == 2
        capacity_checks.append(capacity)
        negative_checks.append(negative)
        generation_seconds = commands.get("generate", {}).get("duration_seconds")
        if isinstance(generation_seconds, (int, float)):
            durations.append(float(generation_seconds))
        metrics = scenario.get("candidate_metrics") or {}
        scenario_results.append(
            {
                "id": scenario.get("id"),
                "modality": scenario.get("modality"),
                "capacity_passed": capacity,
                "candidate_passed": metrics.get("passed"),
                "failed_gates": metrics.get("failed_gates", []),
                "generation_seconds": generation_seconds,
                "negative_control_rejected": negative,
            }
        )
    return {
        "available": True,
        "path": str(path),
        "captured_utc": summary.get("captured_utc"),
        "scenarios": scenario_results,
        "capacity_passed": bool(scenarios) and all(capacity_checks) and all(negative_checks),
        "quality_passed": bool(summary.get("passed")),
        "total_generation_seconds": round(sum(durations), 3),
        "slowest_generation_seconds": max(durations, default=None),
    }


def audit(matrix_path: Path = DEFAULT_MATRIX) -> dict[str, Any]:
    total_memory, available_memory = memory_bytes()
    logical_cpus = os.cpu_count() or 0
    disk = shutil.disk_usage(ROOT)
    packages = package_inventory()
    hardware_checks = {
        "logical_cpus": {
            "value": logical_cpus,
            "minimum": MIN_LOGICAL_CPUS,
            "passed": logical_cpus >= MIN_LOGICAL_CPUS,
        },
        "physical_memory_bytes": {
            "value": total_memory,
            "minimum": MIN_MEMORY_BYTES,
            "passed": total_memory is not None and total_memory >= MIN_MEMORY_BYTES,
        },
        "workspace_free_disk_bytes": {
            "value": disk.free,
            "minimum": MIN_FREE_DISK_BYTES,
            "passed": disk.free >= MIN_FREE_DISK_BYTES,
        },
    }
    runtime_checks = {
        "python": {
            "value": platform.python_version(),
            "minimum": "3.12",
            "passed": sys.version_info >= (3, 12),
        },
        "packages": packages,
    }
    matrix = matrix_evidence(matrix_path)
    docker = docker_inventory()
    gpu = gpu_inventory()
    local_ready = (
        all(check["passed"] for check in hardware_checks.values())
        and runtime_checks["python"]["passed"]
        and packages["passed"]
        and matrix["capacity_passed"]
    )
    harbor_files_present = (
        ROOT / "evaluations" / "harbor-private" / "generate-synthetic-data-evolution.yaml"
    ).is_file() and (ROOT / "evaluations" / "harbor-studies" / "generate-synthetic-data-v1" / "study.json").is_file()
    return {
        "schema_version": 1,
        "captured_utc": datetime.now(UTC).isoformat(),
        "local_evaluation_ready": local_ready,
        "harbor_evaluation_ready": local_ready and docker["available"] and harbor_files_present,
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "logical_cpus": logical_cpus,
            "physical_memory_bytes": total_memory,
            "available_memory_bytes": available_memory,
            "workspace_disk_total_bytes": disk.total,
            "workspace_disk_free_bytes": disk.free,
            "checks": hardware_checks,
            "gpu": gpu,
        },
        "runtime": runtime_checks,
        "skill_matrix": matrix,
        "harbor": {
            "docker": docker,
            "configuration_present": harbor_files_present,
            "ready": local_ready and docker["available"] and harbor_files_present,
        },
        "interpretation": {
            "gpu_required": False,
            "gpu_note": "The current Rata tabular evaluation path is CPU-capable; a GPU is optional acceleration.",
            "quality_note": (
                "Hardware capacity and candidate quality are independent; failed quality gates remain failures."
            ),
        },
    }


def gib(value: int | None) -> str:
    return "unknown" if value is None else f"{value / GIB:.1f} GiB"


def markdown_report(report: dict[str, Any]) -> str:
    hardware = report["hardware"]
    matrix = report["skill_matrix"]
    gpu = hardware["gpu"]
    lines = [
        "# Evaluation readiness audit",
        "",
        f"Captured: `{report['captured_utc']}`",
        "",
        f"- Local skill evaluation ready: **{report['local_evaluation_ready']}**",
        f"- Harbor evaluation ready: **{report['harbor_evaluation_ready']}**",
        f"- Logical CPUs: {hardware['logical_cpus']} (minimum {MIN_LOGICAL_CPUS}).",
        f"- Physical memory: {gib(hardware['physical_memory_bytes'])} (minimum {gib(MIN_MEMORY_BYTES)}).",
        f"- Workspace free disk: {gib(hardware['workspace_disk_free_bytes'])} (minimum {gib(MIN_FREE_DISK_BYTES)}).",
        f"- NVIDIA GPU available: {gpu['available']} (optional).",
        f"- Docker available: {report['harbor']['docker']['available']} (required only for Harbor).",
        "",
        "## Executed skill matrix",
        "",
        f"- Capacity passed: **{matrix.get('capacity_passed')}**.",
        f"- Candidate quality matrix passed: **{matrix.get('quality_passed')}**.",
        f"- Total model-generation time: {matrix.get('total_generation_seconds')} seconds.",
        "",
        "| Scenario | Modality | Capacity | Candidate | Generation seconds | Failed gates |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for scenario in matrix.get("scenarios", []):
        lines.append(
            f"| `{scenario['id']}` | {scenario['modality']} | {scenario['capacity_passed']} | "
            f"{scenario['candidate_passed']} | {scenario['generation_seconds']} | "
            f"{', '.join(scenario['failed_gates']) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Passing the readiness audit means the local machine completed the actual planner/generator/evaluator",
            "workload and has the configured CPU, memory, disk, Python, and package capacity. It does not convert a",
            "failed candidate into a passing one. Harbor remains unavailable until Docker is installed and its server",
            "is running; no holdout or model call should be reported as completed before that gate passes.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit hardware and runtime readiness for Rata skill evaluation.")
    parser.add_argument("--matrix-summary", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-report", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--require-harbor", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit(args.matrix_summary)
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_report.write_text(markdown_report(report), encoding="utf-8")
    required_passed = report["harbor_evaluation_ready"] if args.require_harbor else report["local_evaluation_ready"]
    print(
        json.dumps(
            {
                "local_evaluation_ready": report["local_evaluation_ready"],
                "harbor_evaluation_ready": report["harbor_evaluation_ready"],
                "matrix_quality_passed": report["skill_matrix"].get("quality_passed"),
                "report": str(args.json_report),
            },
            indent=2,
        )
    )
    return 0 if required_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

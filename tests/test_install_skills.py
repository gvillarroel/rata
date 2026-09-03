from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("install_skills", ROOT / "tools" / "install_skills.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load skill installer")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def test_installer_copies_complete_skill_and_refuses_overwrite(tmp_path) -> None:
    destination = tmp_path / "codex-skills"

    installed = installer.install(destination, ["plan-synthetic-data"], overwrite=False, dry_run=False)

    assert installed == [("plan-synthetic-data", destination / "plan-synthetic-data")]
    assert (destination / "plan-synthetic-data" / "SKILL.md").is_file()
    assert (destination / "plan-synthetic-data" / "agents" / "openai.yaml").is_file()
    assert (destination / "plan-synthetic-data" / "scripts" / "plan.py").is_file()
    assert (destination / "plan-synthetic-data" / "scripts" / "plan.py.lock").is_file()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        installer.install(destination, ["plan-synthetic-data"], overwrite=False, dry_run=False)


def test_installer_dry_run_does_not_write(tmp_path) -> None:
    destination = tmp_path / "codex-skills"

    targets = installer.install(destination, installer.available_skills(), overwrite=False, dry_run=True)

    assert len(targets) == 5
    assert not destination.exists()


def test_installer_copies_every_complete_skill_payload(tmp_path) -> None:
    destination = tmp_path / "codex-skills"
    names = installer.available_skills()

    installed = installer.install(destination, names, overwrite=False, dry_run=False)

    assert installed == [(name, destination / name) for name in names]
    for name in names:
        source = installer.SOURCE_ROOT / name
        target = destination / name
        source_files = {
            path.relative_to(source): path.read_bytes()
            for path in source.rglob("*")
            if path.is_file() and path.suffix not in {".pyc", ".pyo"} and path.parent.name != "__pycache__"
        }
        target_files = {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()}
        assert target_files == source_files

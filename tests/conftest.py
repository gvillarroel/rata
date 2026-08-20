from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def load_skill_script(skill: str, script: str) -> ModuleType:
    path = ROOT / "skills" / skill / "scripts" / script
    spec = importlib.util.spec_from_file_location(f"test_{skill.replace('-', '_')}_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

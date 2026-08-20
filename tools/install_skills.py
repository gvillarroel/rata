from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "skills"


def default_destination() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return (Path(codex_home) if codex_home else Path.home() / ".codex") / "skills"


def available_skills() -> list[str]:
    return sorted(path.name for path in SOURCE_ROOT.iterdir() if path.is_dir() and (path / "SKILL.md").is_file())


def validate_destination(destination: Path) -> Path:
    resolved = destination.resolve()
    protected = {Path(resolved.anchor).resolve(), Path.home().resolve(), ROOT.resolve(), SOURCE_ROOT.resolve()}
    if resolved in protected:
        raise ValueError(f"unsafe skill destination: {resolved}")
    return resolved


def install(destination: Path, names: list[str], overwrite: bool, dry_run: bool) -> list[tuple[str, Path]]:
    destination = validate_destination(destination)
    available = set(available_skills())
    unknown = sorted(set(names) - available)
    if unknown:
        raise ValueError(f"unknown skills: {', '.join(unknown)}")
    targets = [(name, destination / name) for name in names]
    conflicts = [target for _, target in targets if target.exists()]
    if conflicts and not overwrite:
        raise FileExistsError(f"refusing to overwrite: {', '.join(map(str, conflicts))}")
    if dry_run:
        return targets

    destination.mkdir(parents=True, exist_ok=True)
    for name, target in targets:
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        shutil.copytree(
            SOURCE_ROOT / name,
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    return targets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Rata skills into a Codex skill directory.")
    parser.add_argument("--destination", type=Path, default=default_destination())
    parser.add_argument("--skill", action="append", choices=available_skills())
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    names = args.skill or available_skills()
    targets = install(args.destination, names, args.overwrite, args.dry_run)
    action = "would install" if args.dry_run else "installed"
    for name, target in targets:
        print(f"{action} {name} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

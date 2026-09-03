from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "plan-synthetic-data",
    "generate-synthetic-data",
    "evaluate-synthetic-data",
    "run-synthetic-data-workflow",
    "harbor-author-evaluation-datasets",
}


def test_skill_packages_have_required_metadata_and_valid_links() -> None:
    assert {path.name for path in (ROOT / "skills").iterdir() if path.is_dir()} == SKILLS

    for name in SKILLS:
        skill_root = ROOT / "skills" / name
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"---\n(.*?)\n---\n", skill_text, flags=re.DOTALL)
        assert match, f"{name} is missing YAML frontmatter"
        frontmatter = yaml.safe_load(match.group(1))
        assert frontmatter["name"] == name
        assert isinstance(frontmatter["description"], str) and frontmatter["description"]

        agent = yaml.safe_load((skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8"))
        assert f"${name}" in agent["interface"]["default_prompt"]
        assert "uv run skills/" not in skill_text, f"{name} contains a repository-relative runtime command"

        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", skill_text):
            if "://" not in target:
                assert (skill_root / target).is_file(), f"{name} has a broken link to {target}"

        for script in (skill_root / "scripts").glob("*.py") if (skill_root / "scripts").is_dir() else []:
            assert script.with_suffix(f"{script.suffix}.lock").is_file(), f"{script} is missing its uv script lock"

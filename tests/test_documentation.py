from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIRECT_INSTALL_SKILLS = {
    "skills/plan-synthetic-data",
    "skills/generate-synthetic-data",
    "skills/evaluate-synthetic-data",
    "skills/run-synthetic-data-workflow",
}


def test_local_markdown_links_resolve() -> None:
    documents = [ROOT / "README.md", ROOT / "AGENTS.md", *sorted((ROOT / "docs").glob("*.md"))]
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for raw_target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target:
                continue
            assert (document.parent / target).resolve().exists(), f"{document} links to missing {raw_target}"


def test_documented_policy_example_is_valid_json() -> None:
    text = (ROOT / "skills" / "plan-synthetic-data" / "references" / "policy.md").read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
    assert match
    policy = json.loads(match.group(1))
    assert policy["version"] == 1
    assert policy["acceptance"]["columns"]["age"]["max_numeric_ks"] == 0.15


def test_ci_workflow_is_valid_yaml() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8"))
    assert workflow["jobs"]["validate"]["steps"]


def test_github_pages_site_has_a_us_aligned_entrypoint() -> None:
    config = yaml.safe_load((ROOT / "docs" / "_config.yml").read_text(encoding="utf-8"))
    index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    assert config["url"] == "https://gvillarroel.github.io"
    assert config["baseurl"] == "/rata"
    assert config["repository"] == "gvillarroel/rata"
    assert "<strong>30</strong>" in index
    assert "default U.S.-aligned sources" in index
    assert "100%" in index
    assert "country fields are filtered to `US`" in index


def test_direct_github_install_is_documented_for_every_skill() -> None:
    for document in (ROOT / "README.md", ROOT / "docs" / "commands.md"):
        text = document.read_text(encoding="utf-8")
        assert "$skill-installer" in text
        assert "gvillarroel/rata" in text
        assert "ref main" in text
        for skill_path in DIRECT_INSTALL_SKILLS:
            assert skill_path in text


def test_readme_exposes_the_download_center() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Download center" in text
    assert "https://github.com/gvillarroel/rata/archive/refs/heads/main.zip" in text
    assert "docs/public-data-sources.md" in text
    assert "docs/public-data-examples.md" in text
    assert "tools/download_public_data.py --list" in text
    assert "tools/download_public_data.py --workers 4" in text

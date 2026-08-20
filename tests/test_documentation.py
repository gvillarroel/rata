from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


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

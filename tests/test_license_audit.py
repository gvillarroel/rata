from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("license_audit", ROOT / "tools" / "audit_licenses.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load license audit")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_license_policy_rejects_strong_copyleft_and_reviews_mpl() -> None:
    assert audit.FORBIDDEN.search("GPL-3.0-only")
    assert audit.FORBIDDEN.search("GNU Affero General Public License")
    assert audit.FORBIDDEN.search("LGPL-2.1-or-later")
    assert not audit.FORBIDDEN.search("Apache-2.0")
    assert audit.REVIEW.search("MPL-2.0")

from __future__ import annotations

import importlib.metadata
import re
import sys

FORBIDDEN = re.compile(
    r"(?:^|[^A-Z])(?:A?GPL|LGPL|SSPL|EUPL|OSL|CPAL|BUSINESS SOURCE|COMMONS CLAUSE|"
    r"GNU (?:LESSER |AFFERO )?GENERAL PUBLIC LICENSE)(?:[^A-Z]|$)",
    re.IGNORECASE,
)
REVIEW = re.compile(r"MPL|MOZILLA PUBLIC LICENSE|CDDL|ECLIPSE PUBLIC LICENSE", re.IGNORECASE)
REQUIRED_PERMISSIVE = {
    "fastavro": ("MIT",),
    "mostlyai-engine": ("APACHE",),
    "numpy": ("BSD",),
    "pandas": ("BSD",),
    "pyarrow": ("APACHE",),
    "scikit-learn": ("BSD",),
    "scipy": ("BSD",),
}


def license_text(distribution: importlib.metadata.Distribution) -> str:
    expressions = distribution.metadata.get_all("License-Expression") or []
    classifiers = distribution.metadata.get_all("Classifier") or []
    license_classifiers = [item for item in classifiers if item.startswith("License ::")]
    declared_lines = (distribution.metadata.get("License") or "").splitlines()
    declared = declared_lines[0].strip() if declared_lines else ""
    if expressions:
        return " | ".join(expressions)
    if license_classifiers:
        return " | ".join(license_classifiers)
    return declared or "UNKNOWN"


def inventory() -> list[tuple[str, str, str]]:
    packages: dict[str, tuple[str, str, str]] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name") or "<unknown>"
        key = name.casefold()
        packages[key] = (name, distribution.version, license_text(distribution))
    return [packages[key] for key in sorted(packages)]


def main() -> int:
    packages = inventory()
    by_name = {name.casefold(): (version, license_value) for name, version, license_value in packages}
    forbidden = [item for item in packages if FORBIDDEN.search(item[2])]
    review = [item for item in packages if REVIEW.search(item[2]) and not FORBIDDEN.search(item[2])]
    unknown = [item for item in packages if item[2] == "UNKNOWN"]

    print(f"Audited {len(packages)} installed distributions.")
    for label, items in (("REVIEW", review), ("UNKNOWN", unknown), ("FORBIDDEN", forbidden)):
        for name, version, license_value in items:
            print(f"{label}: {name}=={version}: {license_value}")

    boundary_errors: list[str] = []
    for name, expected_markers in REQUIRED_PERMISSIVE.items():
        installed = by_name.get(name)
        if installed is None:
            boundary_errors.append(f"required runtime package is missing: {name}")
            continue
        version, license_value = installed
        if not any(marker in license_value.upper() for marker in expected_markers):
            boundary_errors.append(f"unexpected SDK boundary license: {name}=={version}: {license_value}")
    for error in boundary_errors:
        print(f"BOUNDARY: {error}", file=sys.stderr)

    if forbidden:
        print("Strong or network copyleft metadata detected.", file=sys.stderr)
        return 1
    if boundary_errors:
        print("The selected runtime SDK boundary failed its permissive-license check.", file=sys.stderr)
        return 1
    print("No forbidden strong or network copyleft metadata detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

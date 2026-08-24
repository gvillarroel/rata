"""Build a privacy-safe aggregate specification for realistic names, addresses, and short text."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "datasets" / "public-data"
DERIVED = BUNDLE / "derived"
RAW = BUNDLE / "raw"
DEFAULT_OUTPUT = BUNDLE / "realism" / "aggregate-spec.json"
DEFAULT_PROFILE = BUNDLE / "realism" / "profile-evidence.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def weighted_csv(
    path: Path,
    value_column: str,
    weight_column: str = "records",
    *,
    limit: int,
) -> dict[str, int]:
    totals: Counter[str] = Counter()
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            value = str(row.get(value_column, "")).strip()
            raw_weight = str(row.get(weight_column, "0")).strip()
            if value and raw_weight.isdigit():
                totals[value] += int(raw_weight)
    return dict(totals.most_common(limit))


def length_distribution(path: Path) -> dict[str, int]:
    lengths: Counter[str] = Counter()
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            band = str(row.get("word_count_band", ""))
            weight = int(row.get("records", 0))
            if band == "1000_PLUS":
                representative = 120
            else:
                bounds = [int(value) for value in band.split("_")]
                representative = min(round(sum(bounds) / 2), 120)
            lengths[str(representative)] += weight
    return dict(lengths)


def geography_distribution(path: Path, limit: int = 500) -> list[dict[str, Any]]:
    totals: Counter[tuple[str, str, str]] = Counter()
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith((".csv", ".txt"))]
        if not members:
            raise RuntimeError(f"No CSV member in {path}")
        with archive.open(max(members, key=lambda name: archive.getinfo(name).file_size)) as source:
            for chunk in pd.read_csv(
                source,
                usecols=["zip", "city", "stabbr", "naics", "est"],
                dtype={"zip": "string", "city": "string", "stabbr": "string", "naics": "string"},
                chunksize=100_000,
            ):
                national_totals = chunk[chunk["naics"].fillna("").isin(["00", "------"])]
                for row in national_totals.itertuples(index=False):
                    zip_code = str(row.zip).zfill(5)
                    city = str(row.city).strip().title()
                    state = str(row.stabbr).strip().upper()
                    if len(zip_code) == 5 and city and len(state) == 2:
                        totals[(city, state, zip_code)] += int(row.est)
    if not totals:
        raise RuntimeError("No ZIP/city/state totals found in ZBP")
    return [
        {"values": {"city": city, "state": state, "zip_code": zip_code}, "weight": weight}
        for (city, state, zip_code), weight in totals.most_common(limit)
    ]


def build_spec(rows: int, seed: int) -> tuple[dict[str, Any], list[Path]]:
    sources = [
        DERIVED / "census_surname_distribution.csv",
        DERIVED / "nyc_given_name_distribution.csv",
        DERIVED / "tiger_street_name_distribution.csv",
        DERIVED / "tiger_street_suffix_distribution.csv",
        DERIVED / "sec_business_name_token_distribution.csv",
        DERIVED / "cfpb_narrative_token_distribution.csv",
        DERIVED / "cfpb_narrative_length_distribution.csv",
        RAW / "census_zbp_industry_detail_2023.zip",
    ]
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing realism inputs: {', '.join(str(path) for path in missing)}")
    geography = geography_distribution(sources[-1])
    city_values: Counter[str] = Counter()
    state_values: Counter[str] = Counter()
    zip_values: Counter[str] = Counter()
    for row in geography:
        city_values[row["values"]["city"]] += row["weight"]
        state_values[row["values"]["state"]] += row["weight"]
        zip_values[row["values"]["zip_code"]] += row["weight"]
    given_names = weighted_csv(sources[1], "given_name", limit=750)
    surnames = weighted_csv(sources[0], "surname", limit=250)
    street_names = weighted_csv(sources[2], "street_name", limit=500)
    suffixes = weighted_csv(sources[3], "standard_suffix", limit=150)
    business_tokens = weighted_csv(sources[4], "token", limit=750)
    narrative_tokens = weighted_csv(sources[5], "token", limit=1500)
    narrative_lengths = length_distribution(sources[6])
    spec: dict[str, Any] = {
        "version": 1,
        "rows": rows,
        "seed": seed,
        "quality": {"profile": "fast", "max_epochs": 2, "max_training_minutes": 2},
        "columns": [
            {"name": "city", "type": "string", "role": "public", "values": dict(city_values)},
            {"name": "state", "type": "categorical", "role": "public", "values": dict(state_values)},
            {
                "name": "zip_code",
                "type": "string",
                "role": "public",
                "values": dict(zip_values),
                "pattern": "^\\d{5}$",
            },
            {
                "name": "consumer_summary",
                "type": "string",
                "role": "public",
                "generator": {
                    "kind": "token_sequence",
                    "tokens": narrative_tokens,
                    "lengths": narrative_lengths,
                    "capitalize": True,
                    "terminal": ".",
                },
            },
            {
                "name": "synthetic_person_name",
                "type": "identifier",
                "role": "identifier",
                "surrogate": {
                    "strategy": "weighted_template",
                    "template": "{given_name} {middle_initial}. {surname}",
                    "components": {
                        "given_name": {"kind": "choice", "values": given_names},
                        "middle_initial": {
                            "kind": "choice",
                            "values": {character: 1 for character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
                        },
                        "surname": {"kind": "choice", "values": surnames},
                    },
                },
            },
            {
                "name": "synthetic_address",
                "type": "identifier",
                "role": "identifier",
                "surrogate": {
                    "strategy": "weighted_template",
                    "template": "{house_number} {street_name} {suffix}, {city}, {state} {zip_code}",
                    "components": {
                        "house_number": {"kind": "integer", "min": 100, "max": 19999},
                        "street_name": {"kind": "choice", "values": street_names},
                        "suffix": {"kind": "choice", "values": suffixes},
                    },
                },
            },
            {
                "name": "synthetic_business_name",
                "type": "identifier",
                "role": "identifier",
                "surrogate": {
                    "strategy": "weighted_template",
                    "template": "{brand} {descriptor} {legal_suffix}",
                    "components": {
                        "brand": {"kind": "choice", "values": business_tokens},
                        "descriptor": {"kind": "choice", "values": business_tokens},
                        "legal_suffix": {
                            "kind": "choice",
                            "values": {"LLC": 45, "Inc": 25, "Corp": 15, "Company": 10, "LP": 5},
                        },
                    },
                },
            },
        ],
        "joint_distributions": [
            {"name": "city_state_zip", "columns": ["city", "state", "zip_code"], "rows": geography}
        ],
        "acceptance": {
            "max_identifier_component_tv": 0.15,
            "max_identifier_template_violation_ratio": 0.0,
            "max_text_length_tv": 0.15,
            "max_text_token_tv": 0.15,
        },
    }
    return spec, sources


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260822)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.rows < 1000:
        raise ValueError("--rows must be at least 1000 for stable long-tail calibration")
    existing = [path for path in (args.output, args.evidence) if path.exists()]
    if existing and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite: {', '.join(str(path) for path in existing)}")
    spec, sources = build_spec(args.rows, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    evidence = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "spec": str(args.output),
        "spec_sha256": sha256_file(args.output),
        "inputs": [
            {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in sources
        ],
        "privacy": [
            "Person names combine independent published frequency distributions and do not preserve source pairings.",
            "Addresses combine independent road-name/suffix components with geography; no household address rows "
            "or ranges are used.",
            "Language uses high-document-frequency unigrams and capped length bands; no narrative, phrase, or token "
            "order is retained.",
            "Generated names and addresses can coincidentally match real-world values and must remain labeled "
            "synthetic.",
        ],
        "limitations": [
            "NYC given-name counts are geographically biased and are not a national population estimate.",
            "The six-county road sample is diverse but not nationally representative.",
            "Unigram sequences calibrate vocabulary and length, not grammar, factuality, or semantic coherence.",
            "Narrative lengths are capped at 120 words for practical generation and evaluation.",
            "Finite-sample profiles truncate each long-tail vocabulary to an explicit top-K before normalization.",
        ],
    }
    args.evidence.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"spec": str(args.output), "evidence": str(args.evidence), "rows": args.rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

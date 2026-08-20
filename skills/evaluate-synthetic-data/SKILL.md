---
name: evaluate-synthetic-data
description: Compare original and synthetic CSV, JSON, JSONL, Parquet, or Avro tables using policy-aware tabular and TABULAR_CHARACTER text quality/privacy gates. Use when Codex needs to audit distribution or lexical fidelity, correlation drift, propensity AUC, exact replay, rare-value replay by column privacy level, identifier overlap, DCR, NNDR, schema completeness, generation-report binding, or differential-privacy checkpoint evidence.
---

# Evaluate Synthetic Data

Audit every generated table independently from its generator.

## Run

Resolve `scripts/evaluate.py` relative to this `SKILL.md` and invoke it by absolute path. The adjacent script lockfile pins the standalone environment.

```powershell
uv run C:\absolute\path\to\evaluate-synthetic-data\scripts\evaluate.py `
  original.parquet synthetic.parquet policy.json evaluation.json `
  --generation-report synthetic.report.json
```

The command writes the report even when acceptance gates fail and exits with code `2` for a failed release candidate.
It refuses to replace an existing evaluation report unless `--overwrite` is present.

## Interpretation

Read [metrics.md](references/metrics.md) before changing thresholds or explaining privacy. Distinguish these cases:

- Exact replay in `public` columns is allowed and reported separately.
- Replay in `protected` or `private` rare values is a privacy warning.
- Any source overlap in `identifier` columns is a hard failure.
- Presence of a `drop` column is a hard failure.
- Any unexpected output column is a hard failure.
- Missing DP checkpoint evidence for a `private` stage is a hard failure.
- A generation report whose policy, source, output, roles, or row count does not match the candidate is a hard failure.
- `TABULAR_CHARACTER` columns use text length and TF-IDF gates, not exact-category total variation.

Do not call DCR, NNDR, or low replay a formal privacy guarantee. Only the recorded DP training budget supports a DP claim.

Respect `dataset.input_kind`. A `synthetic-reference` comparison does not establish original-source release fitness.
An `aggregate-proxy` comparison is mechanical generation evidence and must be paired with the aggregate constraint
report produced by `generate-synthetic-data/scripts/evaluate_spec.py`.

## Release Decision

Report every failing gate with its measured and threshold values. Apply both global and user-defined per-column gates. Never weaken privacy gates automatically. Improve role assignments, generation configuration, or source preparation, regenerate, and rerun the audit.

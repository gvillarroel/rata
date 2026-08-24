---
name: plan-synthetic-data
description: Inspect CSV, JSON, JSONL, Parquet, or Avro tabular data and create a conservative column-level synthetic-data policy. Use when Codex needs to classify columns as public, protected, private, identifier, or drop; translate user-defined quality, privacy, and release requirements into global or per-column gates; choose differential-privacy settings; or prepare a policy for the generate-synthetic-data skill.
---

# Plan Synthetic Data

Create an explicit policy before generation. Never infer `public`; require the user or task context to name columns that may be copied without privacy protection.

## Workflow

1. Inspect the table and the user's privacy requirements.
2. Resolve `scripts/plan.py` relative to this `SKILL.md`; use its absolute path so the skill works outside the source repository. Run the planner, passing explicit role lists whenever they are known:

```powershell
uv run C:\absolute\path\to\plan-synthetic-data\scripts\plan.py data.parquet policy.json `
  --public country,product `
  --private diagnosis,salary `
  --identifier customer_id,email `
  --drop internal_notes `
  --output out/data.synthetic.parquet `
  --report out/data.synthetic.report.json `
  --workspace out/data.synthetic-workspace
```

3. Review every inferred `identifier`, `private`, and `drop` decision. Treat name-based inference as a warning, not authoritative domain knowledge.
4. Resolve any column left at the conservative `protected` default.
5. Review inferred semantic encodings. Date-like strings should use `TABULAR_DATETIME`; override ambiguous columns with repeated `--encoding COLUMN=TYPE` arguments.
6. Translate user quality/privacy requirements into explicit DP flags, repeated `--acceptance NAME=VALUE` thresholds, and repeated `--column-requirement COLUMN.METRIC=VALUE` thresholds.
7. Read [policy.md](references/policy.md) when editing roles, encodings, DP parameters, quality profiles, or acceptance gates manually.
8. Hand the approved policy to `$generate-synthetic-data`.

When the supplied table is already synthetic, pass `--input-kind synthetic-reference` and attach its generation or
provenance report with `--input-report` when available. This preserves its origin but does not establish privacy or
release fitness against unavailable original rows.

## Role Rules

- `public`: allow joint resampling and exact source values. Assign only explicitly.
- `protected`: use non-DP generation with value protection and replay auditing.
- `private`: use a separately trained DP model and strict replay auditing.
- `identifier`: exclude from training and replace with unrelated unique surrogates.
- `drop`: exclude from training and output.

`protected` is the conservative default when there is no domain evidence that requires DP. Promote health, financial, demographic, or similarly sensitive fields to `private`; do not interpret "conservative" as a reason to leave known sensitive data merely protected.

Identifier surrogates are intentionally unlinkable strings. `uuid` preserves uniqueness but not source formatting; `sequential` produces stable prefixed sequence strings. Names, emails, IP addresses, card-like values, and numeric IDs therefore lose their original type or shape unless a future domain-specific surrogate strategy is explicitly added and audited.

Treat public-data entity keys such as NPI, UEI, DUNS, CIK, loan/award/case numbers, DOT/MC numbers, legal names, and
registered-agent fields as identifier candidates unless the task explicitly authorizes a public role. Treat row-level
payroll, wages, revenue, receipts, loans, awards, balances, delinquencies, and credit limits as sensitive candidates;
published aggregates may be explicitly public after review.

Do not downgrade a role to improve quality. If requirements conflict, keep the stronger role and report the utility tradeoff.

## Validation

Re-run the planner after source-schema changes. It rejects unknown or multiply assigned columns and refuses to replace an existing policy without `--overwrite`. The emitted JSON is deterministic and suitable for review and version control.

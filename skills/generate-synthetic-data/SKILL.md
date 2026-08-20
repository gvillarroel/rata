---
name: generate-synthetic-data
description: Generate and validate synthetic CSV, JSON, JSONL, Parquet, or Avro tables with Apache-2.0 mostlyai-engine from source rows, an existing synthetic reference, or a schema plus aggregate statistics. Use when Codex needs policy-driven public/protected/private roles, DP evidence, identifiers replaced, aggregate constraints materialized, or reproducible generation and validation reports.
---

# Generate Synthetic Data

Run policy-driven staged generation with `mostlyai-engine`, not the full connector SDK.

## Select the Input Mode

Read [request-modes.md](references/request-modes.md) when the user supplies anything other than an approved policy and
source table. Choose exactly one mode: source rows, existing synthetic reference, or schema with aggregate statistics.
Preserve the input kind and its provenance in the policy and reports.

For source rows, use a policy created or reviewed with `$plan-synthetic-data`. For an existing synthetic reference,
do not infer that it is private or releasable when original-source evidence is missing. For aggregate-only input,
materialize proxy rows with the bundled script, label them `aggregate-proxy`, and validate the final output against the
declared constraints as well as the generation evidence.

Read [engine.md](references/engine.md) before changing engine versions, DP behavior, or staging semantics.

## Generate

Resolve `scripts/generate.py` relative to this `SKILL.md` and invoke it by absolute path. The adjacent script lockfile pins the standalone environment.

```powershell
uv run C:\absolute\path\to\generate-synthetic-data\scripts\generate.py policy.json `
  --output out/data.synthetic.parquet `
  --report out/data.synthetic.report.json `
  --workspace out/data.synthetic-workspace
```

Useful overrides:

```powershell
uv run C:\absolute\path\to\generate-synthetic-data\scripts\generate.py policy.json `
  --input data.parquet --output data.synthetic.parquet --rows 10000 --overwrite
```

The command must produce both the synthetic table and a JSON generation report. The report binds SHA-256 evidence for the generation policy, source, and output. For `private` columns, fail the run unless the engine records a DP checkpoint epsilon and delta.

When the policy input kind is `aggregate-proxy`, also run the bundled `scripts/evaluate_spec.py` against the final table.
When it is `synthetic-reference`, label original-source privacy and release fitness unresolved unless the original policy
and bound evidence are available.

## Safety Rules

- Never silently downgrade `private` to non-DP generation.
- Never train on `identifier` or `drop` columns.
- Never infer a column as `public` during generation.
- Treat public-column exact replay as explicitly allowed by policy, not as anonymization.
- Keep each run in a new workspace directory; do not reuse model state accidentally.
- Run `$evaluate-synthetic-data` before presenting output as releasable.
- Preserve failed generation, constraint, and evaluation reports as evidence.

Use `--dry-run` to validate paths, planned stages, isolated workspace root, roles, and the complete DP configuration without training.

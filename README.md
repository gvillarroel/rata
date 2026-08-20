# Rata Synthetic Data Skills

Rata is a set of four Codex skills for generating tabular synthetic data under an explicit column-level privacy policy. It uses the Apache-2.0 `mostlyai-engine` SDK directly and keeps planning, generation, and release evaluation separate so a candidate cannot silently bypass its privacy gates.

## Skill catalog

| Skill | Responsibility |
| --- | --- |
| [`plan-synthetic-data`](skills/plan-synthetic-data/SKILL.md) | Inspect a table and assign `public`, `protected`, `private`, `identifier`, or `drop` roles. |
| [`generate-synthetic-data`](skills/generate-synthetic-data/SKILL.md) | Route source, synthetic-reference, or aggregate-spec inputs through staged generation and validation. |
| [`evaluate-synthetic-data`](skills/evaluate-synthetic-data/SKILL.md) | Apply policy-aware quality, replay, overlap, schema, and DP-evidence gates. |
| [`run-synthetic-data-workflow`](skills/run-synthetic-data-workflow/SKILL.md) | Coordinate the other skills and remediate failed release candidates without weakening privacy. |

## Quick start

Install the locked Python 3.12 environment with [uv](https://docs.astral.sh/uv/):

```powershell
uv sync --python 3.12 --locked
```

Preview and install the four packages into the current Codex skill directory:

```powershell
python tools/install_skills.py --dry-run
python tools/install_skills.py
```

The installer uses `$CODEX_HOME\skills` when `CODEX_HOME` is set and otherwise uses `~\.codex\skills`. It refuses to replace an installed skill unless `--overwrite` is explicit. Restart or reload Codex after installation so the skills are discovered.

Create and review a policy. `public` is never inferred because it permits exact source values:

```powershell
uv run skills/plan-synthetic-data/scripts/plan.py data.parquet policy.json `
  --public country,product `
  --private diagnosis,salary `
  --identifier customer_id,email `
  --drop internal_notes `
  --output out/data.synthetic.parquet `
  --report out/data.synthetic.report.json `
  --workspace out/data.synthetic-workspace
```

Add user-defined release requirements when defaults are insufficient:

```powershell
uv run skills/plan-synthetic-data/scripts/plan.py data.parquet policy.json `
  --private salary `
  --noise-multiplier 2.0 `
  --acceptance max_propensity_auc=0.72 `
  --column-requirement salary.max_numeric_ks=0.15
```

Validate the run, generate a candidate, and evaluate it:

```powershell
uv run skills/generate-synthetic-data/scripts/generate.py policy.json --dry-run
uv run skills/generate-synthetic-data/scripts/generate.py policy.json
uv run skills/evaluate-synthetic-data/scripts/evaluate.py `
  data.parquet out/data.synthetic.parquet policy.json out/evaluation.json `
  --generation-report out/data.synthetic.report.json
```

An evaluation exit code of `2` means the report was written but the candidate is not releasable. Remediate the policy or model settings, generate into a new workspace, and evaluate again.

## Schema and statistics only

When no row-level source exists, describe columns, roles, marginals, missingness, and optional numeric correlations in a
versioned JSON specification. Materialize reproducible proxy rows and a policy, generate with the same engine, then
evaluate both the bound generation and the declared constraints:

```powershell
uv run skills/generate-synthetic-data/scripts/materialize_spec.py spec.json proxy.csv policy.json `
  --materialization-report proxy.report.json `
  --output synthetic.csv --report generation.report.json --workspace model-workspace
uv run skills/generate-synthetic-data/scripts/generate.py policy.json
uv run skills/generate-synthetic-data/scripts/evaluate_spec.py spec.json synthetic.csv constraints.json
```

Proxy rows are not observed records. Metrics against them do not establish similarity to an unknown population, and DP
applied to proxy training does not create an original-source privacy guarantee.

## Privacy levels

- `public`: no privacy claim; joint source resampling and exact values are allowed.
- `protected`: non-DP synthesis with value protection and rare-value replay limits.
- `private`: a separate DP training stage with a required epsilon/delta checkpoint.
- `identifier`: excluded from training and replaced with unrelated unique surrogates.
- `drop`: excluded from both training and output.

Read [the privacy model](docs/privacy-model.md) before making a release claim. A passing report is evidence against the configured gates, not proof of anonymization.

## Validation

```powershell
uv run ruff check skills tests tools
uv run ruff format --check skills tests tools
uv run pytest
uv run python tools/audit_licenses.py
uv lock --check --script skills/plan-synthetic-data/scripts/plan.py
uv lock --check --script skills/generate-synthetic-data/scripts/generate.py
uv lock --check --script skills/generate-synthetic-data/scripts/materialize_spec.py
uv lock --check --script skills/generate-synthetic-data/scripts/evaluate_spec.py
uv lock --check --script skills/evaluate-synthetic-data/scripts/evaluate.py
python tools/install_skills.py --destination .local-skill-test --dry-run
```

See the [documentation index](docs/README.md), [architecture](docs/architecture.md), [command reference](docs/commands.md), [validation record](docs/validation.md), and [licensing boundary](docs/licensing.md).

## Evaluation matrix

The ordered [`evaluations/catalog.json`](evaluations/catalog.json) requires a tabular scenario followed by a
tabular-plus-text scenario. Run both real workflows and their deliberately leaky negative controls with:

```powershell
uv run tools/run_evaluation_matrix.py C:\absolute\path\to\evidence
```

See the [evaluation state-of-the-art report](docs/evaluation-state-of-art.md) and its
[machine-readable evidence](evaluations/results/2026-07-26.json).

The Harbor skill benchmark has three development tasks, two validation tasks, and two sealed holdouts. Its native
configuration and task digests pass dry-run validation; the live GEPA evolution stage is preserved as blocked because
this workstation has no Docker-compatible Harbor sandbox. See the safe
[study publication index](evaluations/harbor-studies/generate-synthetic-data-v1/publication/index.md).

# Rata Synthetic Data Skills

Rata is a set of four Codex skills for generating tabular synthetic data under an explicit column-level privacy policy. It uses the Apache-2.0 `mostlyai-engine` SDK directly and keeps planning, generation, and release evaluation separate so a candidate cannot silently bypass its privacy gates.

Browse the published documentation at [gvillarroel.github.io/rata](https://gvillarroel.github.io/rata/).

## Download center

| What you need | Start here | What is available |
| --- | --- | --- |
| All four Codex skills | [Install directly from GitHub](#install-directly-from-github) or [download the repository ZIP](https://github.com/gvillarroel/rata/archive/refs/heads/main.zip) | Planning, generation, evaluation, and end-to-end workflow packages with pinned script environments. |
| Public calibration datasets | [Official-source download catalog](docs/public-data-sources.md) | 30 reproducible U.S.-aligned default sources plus one documented U.S. opt-in source, grouped by business data, reference data, registries, and privacy-safe realism calibration. |
| Small verified examples | [Public-data example catalog](docs/public-data-examples.md) | Five-row examples and coverage notes for every requested category and every locally retained artifact. |
| Validation evidence | [Validation record](docs/validation.md), [evaluation evidence](evaluations/results/2026-07-26.json), and [Harbor publication index](evaluations/harbor-studies/generate-synthetic-data-v1/publication/index.md) | Test, quality, privacy, readiness, and benchmark evidence, including preserved failures and limitations. |
| Guides and reference | [Documentation index](docs/README.md) and [command reference](docs/commands.md) | Architecture, privacy model, licensing, commands, requirements, and ADRs. |

The large source bundle is intentionally not committed to Git. Dataset links in the catalog point to official
publishers, and the downloader validates and privacy-minimizes them locally. After cloning and installing the locked
environment, list every source key or download the default bundle with:

```powershell
uv run python tools/download_public_data.py --list
uv run python tools/download_public_data.py --workers 4
```

## Skill catalog

| Skill | Responsibility |
| --- | --- |
| [`plan-synthetic-data`](skills/plan-synthetic-data/SKILL.md) | Inspect a table and assign `public`, `protected`, `private`, `identifier`, or `drop` roles. |
| [`generate-synthetic-data`](skills/generate-synthetic-data/SKILL.md) | Route source, synthetic-reference, or aggregate-spec inputs through staged generation and validation. |
| [`evaluate-synthetic-data`](skills/evaluate-synthetic-data/SKILL.md) | Apply policy-aware quality, replay, overlap, schema, and DP-evidence gates. |
| [`run-synthetic-data-workflow`](skills/run-synthetic-data-workflow/SKILL.md) | Coordinate the other skills and remediate failed release candidates without weakening privacy. |

## Install directly from GitHub

Rata can be installed into Codex straight from the public repository; cloning the repository and synchronizing its
development environment are not required. Send this request to Codex:

```text
Use $skill-installer to install all of these paths from gvillarroel/rata at ref main:
- skills/plan-synthetic-data
- skills/generate-synthetic-data
- skills/evaluate-synthetic-data
- skills/run-synthetic-data-workflow
```

The built-in installer downloads each skill into `$CODEX_HOME/skills` or, when `CODEX_HOME` is unset,
`~/.codex/skills`. It refuses to replace an existing skill directory. Restart or reload Codex after installation so
the skills are discovered. The installed scripts use [uv](https://docs.astral.sh/uv/) to create their pinned runtime
environments when invoked.

## Install from a local clone

From the repository root, preview and install all four skills into the current Codex skill directory:

```powershell
python tools/install_skills.py --dry-run
python tools/install_skills.py
```

The local installer uses the same destinations and refuses to replace an installed skill unless `--overwrite` is
explicit. Use `--skill NAME` to install only one package.

## Quick start

For repository development, install the locked Python 3.12 environment:

```powershell
uv sync --python 3.12 --locked
```

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

An evaluation exit code of `2` means the report was written but the candidate is not releasable. Every release
decision requires the exact bound generation report, even for public-only data. Remediate the policy or model settings,
generate into a new workspace, and evaluate again.

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

Aggregate specs may also generate high-frequency token sequences and unique weighted-template identifier surrogates
for realistic names, business names, and address-shaped fields. These preserve declared component distributions while
keeping identifiers out of training; they do not guarantee semantic text quality or that a recombined value cannot
coincidentally exist in the real world.

## Privacy levels

- `public`: no privacy claim; joint source resampling and exact values are allowed.
- `protected`: non-DP synthesis with value protection and rare-value replay limits.
- `private`: a separate DP training stage with a required epsilon/delta checkpoint.
- `identifier`: excluded from training and replaced with unrelated, nonmissing, unique surrogates.
- `drop`: excluded from both training and output.

Read [the privacy model](docs/privacy-model.md) before making a release claim. A passing report is evidence against the
configured gates, not proof of anonymization. Full-policy provenance, semantic numeric/datetime/boolean validity, and
identifier uniqueness are hard release gates.

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
uv run python tools/audit_public_data_quality.py
uv run python tools/run_evaluation_matrix.py datasets/public-data/evaluation-readiness/matrix --overwrite
uv run python tools/audit_evaluation_readiness.py
```

See the [evaluation state-of-the-art report](docs/evaluation-state-of-art.md) and its
[machine-readable evidence](evaluations/results/2026-07-26.json). Data quality, compute readiness, and candidate
quality are separate decisions; a machine can be ready while a candidate correctly fails its gates.

The Harbor skill benchmark has three development tasks, two validation tasks, and two sealed holdouts. Its native
configuration and task digests pass dry-run validation; the live GEPA evolution stage is preserved as blocked because
this workstation has no Docker-compatible Harbor sandbox. See the safe
[study publication index](evaluations/harbor-studies/generate-synthetic-data-v1/publication/index.md).

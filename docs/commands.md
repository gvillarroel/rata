# Command Reference

Run workflow commands with Python 3.12 and `uv`.

## Install skills

For a direct installation from GitHub without cloning Rata, send the following request to Codex:

```text
Use $skill-installer to install all of these paths from gvillarroel/rata at ref main:
- skills/plan-synthetic-data
- skills/generate-synthetic-data
- skills/evaluate-synthetic-data
- skills/run-synthetic-data-workflow
```

For a local clone, run from the repository root:

```powershell
python tools/install_skills.py [--destination PATH] [--skill NAME] [--dry-run] [--overwrite]
```

Without `--skill`, install all packages. Both installation methods default to `$CODEX_HOME/skills` or
`~/.codex/skills`. Existing packages are never replaced; only the local installer offers the explicit `--overwrite`
escape hatch. Reload Codex after installation.

## Plan

```powershell
uv run skills/plan-synthetic-data/scripts/plan.py INPUT POLICY `
  [--public COLS] [--protected COLS] [--private COLS] `
  [--identifier COLS] [--drop COLS] `
  [--default-role protected|private] `
  [--quality-profile fast|balanced|high] `
  [--max-epochs N] [--max-training-minutes MINUTES] `
  [--sampling-temperature VALUE] `
  [--max-epsilon VALUE] [--delta VALUE] `
  [--noise-multiplier VALUE] [--max-grad-norm VALUE] `
  [--value-protection-epsilon VALUE] [--rare-value-threshold N] `
  [--encoding COLUMN=TYPE] `
  [--acceptance NAME=VALUE] `
  [--column-requirement COLUMN.METRIC=VALUE] `
  [--output PATH] [--report PATH] [--workspace PATH] `
  [--rows N] [--seed N] `
  [--input-kind source|synthetic-reference|aggregate-proxy] `
  [--input-report PATH] [--overwrite]
```

Column lists are comma-separated. Repeat `--encoding` to override semantic inference, for example `--encoding birthdate=TABULAR_DATETIME`. Repeat `--acceptance` for global requirements and `--column-requirement` for stricter field-level requirements, such as `--column-requirement salary.max_numeric_ks=0.15`. Destination options are written into the policy so the generator can run without path overrides. The planner refuses to replace an existing policy unless `--overwrite` is present.

Use `synthetic-reference` only for a table already generated elsewhere; attach its report when present. Original-source
privacy and release fitness remain unresolved without the original bound evidence.

## Materialize schema and aggregate statistics

```powershell
uv run skills/generate-synthetic-data/scripts/materialize_spec.py `
  SPEC PROXY POLICY `
  --materialization-report REPORT `
  --output SYNTHETIC --report GENERATION_REPORT --workspace WORKSPACE `
  [--rows N] [--seed N] [--overwrite]
```

The JSON specification supports numeric normal/lognormal/uniform/constant distributions, weighted categories,
booleans, strings, datetime bounds, identifiers, missing rates, regex code patterns, weighted categorical joint
distributions, acyclic numeric sum/difference/product derivations, and an optional positive-definite numeric
correlation matrix. Strings may use a weighted `token_sequence` generator, and identifiers may use
`weighted_template` choice/integer components plus released row context. It writes proxy rows, a complete
`aggregate-proxy` policy, and a SHA-256-bound materialization report.

## Generate

```powershell
uv run skills/generate-synthetic-data/scripts/generate.py POLICY `
  [--input PATH] [--output PATH] [--report PATH] [--workspace PATH] `
  [--rows N] [--seed N] [--dry-run] [--overwrite] [--verbose]
```

Every non-dry run uses a new timestamped workspace. `--overwrite` applies only to the selected table and report; it never reuses model state. Input, output, report, and workspace paths must be distinct. The generation report contains hashes binding the policy, source, and output.
The policy hash covers the complete policy. A safe unused report path also receives structured failure evidence when
generation raises before producing a candidate.
CSV columns explicitly encoded as categorical/character data, plus identifiers, are loaded as strings so leading-zero
codes survive planning, generation, and evaluation.

## Evaluate

```powershell
uv run skills/evaluate-synthetic-data/scripts/evaluate.py `
  ORIGINAL SYNTHETIC POLICY OUTPUT `
  [--generation-report PATH] [--overwrite]
```

Exit code `0` means every required gate passed. Exit code `2` means the evaluation report was written and one or more gates failed, including missing released columns. The evaluator refuses to overwrite prior evidence without `--overwrite` and verifies that generation evidence belongs to the exact candidate.
The `--generation-report` flag may be omitted only when `policy.dataset.report` resolves to that exact existing report;
missing or mismatched evidence fails every release mode. Numeric, datetime, and boolean semantic validity plus
identifier nonmissingness/uniqueness are zero-tolerance gates. Unexpected runtime errors write a structured failure
report when the requested output path is safe and unused.

## Evaluate aggregate constraints

```powershell
uv run skills/generate-synthetic-data/scripts/evaluate_spec.py `
  SPEC SYNTHETIC OUTPUT [--overwrite]
```

The report gates schema, missingness, numeric types/moments/bounds, integer integrity, declared categorical domains and
total variation, regex code patterns, joint combinations/distributions, derived row arithmetic, datetime validity,
identifier uniqueness, and declared numeric correlations. Exit code `2` preserves a failed constraint report.
Weighted templates additionally gate template/context validity and component total variation. Token sequences gate
unigram and length total variation.
Runtime failures also preserve a hash-bound report when the output path is safe and unused.

## Develop

```powershell
uv sync --python 3.12 --locked
uv run ruff check skills tests tools
uv run ruff format --check skills tests tools
uv run pytest
uv run python tools/audit_licenses.py
```

## Download public calibration data and examples

Download and privacy-minimize the official public-data bundle, audit its record coverage, and generate a small
example from every source:

```powershell
uv run python tools/download_public_data.py --workers 4
uv run python tools/download_public_data.py --only realism --workers 6
uv run python tools/download_public_data.py --only capability --workers 4
uv run python tools/build_realism_profile.py
uv run python tools/benchmark_realism_quality.py
uv run python tools/audit_public_data_coverage.py
uv run python tools/generate_public_data_examples.py
uv run python tools/audit_public_data_quality.py
```

List official source URLs without downloading, or verify an existing example catalog without network access:

```powershell
uv run python tools/download_public_data.py --list
uv run python tools/download_public_data.py --only census_cbp_state_2023
uv run python tools/generate_public_data_examples.py --check
```

`--list` prints every stable source key, official download URL, publisher landing page, vintage, and local handling
mode. Pass one or more keys to `--only` to avoid downloading the complete bundle; the optional SSA source is available
only through an explicit `--only ssa_national_names` request.

`generate_public_data_examples.py` covers all 48 U.S.-only source-manifest artifacts and fetches two small official gap
examples from USAspending and U.S. Courts. `--offline` regenerates local examples while reusing those cached external
CSV examples.

The quality audit performs a full value scan, validates manifest hashes, archive integrity, source-aware schemas,
numeric/code validity, aggregate grains and weights, privacy-minimized columns, and exact reconciliation with the
coverage report. Use `--sample` only for a fast diagnostic.

`--only realism` downloads or reuses the official name, road-component, postal-standard, language, business-token,
and ZIP/city sources without redownloading unrelated staged registries. Row-level CFPB complaints are reduced to
high-document-frequency token and length distributions and removed after successful processing. The profile builder
creates an ignored aggregate spec; the benchmark compares it with a uniform-weight baseline.

`--only capability` downloads or reuses the paired 2024 ACS PUMS North Carolina person/housing archives, the NHTSA
2020–2024 complaint archive, and the USDA 2026-04-30 Foundation Foods archive. ACS and NHTSA inputs are transformed
into thresholded distributions and deleted from staging; the non-person FoodData relational archive is retained.

## Audit evaluation hardware and runtime

Run the real ordered skill matrix, then bind its evidence to the local hardware/runtime audit:

```powershell
uv run python tools/run_evaluation_matrix.py datasets/public-data/evaluation-readiness/matrix --overwrite
uv run python tools/audit_evaluation_readiness.py
```

Local readiness requires the repository baseline for CPU, RAM, free disk, Python, locked packages, and completed
planner/generator/evaluator scenarios. Add `--require-harbor` when Docker-backed Harbor execution is required. A failed
candidate quality gate does not fail compute capacity and is never converted into a passing candidate.

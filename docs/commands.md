# Command Reference

Run commands from the repository root with Python 3.12 and `uv`.

## Install skills

```powershell
python tools/install_skills.py [--destination PATH] [--skill NAME] [--dry-run] [--overwrite]
```

Without `--skill`, install all packages. The default destination is `$CODEX_HOME\skills` or `~\.codex\skills`. Existing packages are never replaced without `--overwrite`.

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

The JSON specification supports numeric normal/uniform/constant distributions, weighted categories, booleans, strings,
datetime bounds, identifiers, missing rates, and an optional positive-definite numeric correlation matrix. It writes
proxy rows, a complete `aggregate-proxy` policy, and a SHA-256-bound materialization report.

## Generate

```powershell
uv run skills/generate-synthetic-data/scripts/generate.py POLICY `
  [--input PATH] [--output PATH] [--report PATH] [--workspace PATH] `
  [--rows N] [--seed N] [--dry-run] [--overwrite] [--verbose]
```

Every non-dry run uses a new timestamped workspace. `--overwrite` applies only to the selected table and report; it never reuses model state. Input, output, report, and workspace paths must be distinct. The generation report contains hashes binding the policy, source, and output.

## Evaluate

```powershell
uv run skills/evaluate-synthetic-data/scripts/evaluate.py `
  ORIGINAL SYNTHETIC POLICY OUTPUT `
  [--generation-report PATH] [--overwrite]
```

Exit code `0` means every required gate passed. Exit code `2` means the evaluation report was written and one or more gates failed, including missing released columns. The evaluator refuses to overwrite prior evidence without `--overwrite` and verifies that generation evidence belongs to the exact candidate.

## Evaluate aggregate constraints

```powershell
uv run skills/generate-synthetic-data/scripts/evaluate_spec.py `
  SPEC SYNTHETIC OUTPUT [--overwrite]
```

The report gates schema, missingness, numeric moments and bounds, category total variation, datetime validity, identifier
uniqueness, and declared numeric correlations. Exit code `2` preserves a failed constraint report.

## Develop

```powershell
uv sync --python 3.12 --locked
uv run ruff check skills tests tools
uv run ruff format --check skills tests tools
uv run pytest
uv run python tools/audit_licenses.py
```

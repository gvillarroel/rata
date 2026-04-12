# Reports And Output

Rata produces two kinds of output:

- human-friendly terminal output
- machine-friendly JSON output

## What Each Command Returns

- `rata stats` -> Markdown by default, JSON with `--output json`
- `rata schema` -> schema formats such as Markdown, JSON Schema, OpenAPI, Avro, TypeScript, and Python
- `rata head` -> Markdown by default, JSON with `--output json`
- `rata transform` -> JSON report
- `rata synth smote` -> JSON report
- `rata synth dp-noise` -> JSON report

## Generate Reports For All Local Datasets

```powershell
# Read all files in datasets/ and save reports into docs/reports/
./scripts/generate-stats-reports.ps1
```

This creates:

- one Markdown report per dataset
- one JSON report per dataset

The generated files are stored in [reports](C:\Users\villa\dev\rata\docs\reports).

## Readable Output

Use readable output when you want to inspect things manually.

```powershell
# Read a stats report directly in the terminal
rata stats datasets\iris.csv

# Preview a file quickly
rata head datasets\cars.json --rows 3
```

## JSON Output

Use JSON output when you want to compare runs or automate checks.

```powershell
# Export stats as JSON
rata stats datasets\iris.csv --output json

# Export a preview as JSON
rata head datasets\news_headlines.jsonl --output json
```

## What A Stats Report Usually Contains

A stats report can include:

- row and column counts
- dominant types
- null and missing values
- distinct counts
- numeric summaries
- string summaries
- structure summaries
- semantic hints
- pairwise relationships

## What A Synthetic Generation Report Usually Contains

A generation report can include:

- source and output paths
- selected parameters
- selected feature columns
- `stats_diff`
- `evaluation`

The `evaluation` section focuses on:

- quality
- drift
- privacy proxy metrics

## Related Docs

- [Analyze Datasets](C:\Users\villa\dev\rata\docs\analyze-datasets.md)
- [Generate Synthetic Data](C:\Users\villa\dev\rata\docs\synthetic-data.md)
- [Commands](C:\Users\villa\dev\rata\docs\commands.md)

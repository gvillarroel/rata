# Reports And Output

Rata can return either human-readable Markdown or machine-readable JSON, depending on the command.

## Output By Command

- `rata stats` supports `markdown` and `json`
- `rata schema` supports multiple schema render formats
- `rata head` supports `markdown` and `json`
- `rata transform` returns a JSON report
- `rata synth smote` returns a JSON report
- `rata synth dp-noise` returns a JSON report

## Generated Reports For Local Datasets

To generate reports for every local dataset in `datasets/`:

```powershell
./scripts/generate-stats-reports.ps1
```

This writes output into [reports](C:\Users\villa\dev\rata\docs\reports).

Each dataset gets:

- one Markdown report
- one JSON report

## What A Stats Report Contains

A full stats report can include:

- dataset path, format, row count, and column count
- type and structure summaries
- nested field paths
- semantic hints
- per-column distributions
- numeric summaries
- string summaries
- boolean and temporal summaries
- pairwise numeric and categorical relationships

## What A Synthetic Generation Report Contains

Synthetic-data commands return:

- input and output paths
- generation parameters
- row counts
- selected feature columns
- `stats_diff` between original and generated datasets
- `evaluation` for quality and privacy diagnostics

## When To Use Markdown vs JSON

Use Markdown when:

- you want to read the output directly in the terminal
- you want a quick summary
- you want to keep user-facing reports

Use JSON when:

- you want to automate checks
- you want to compare runs
- you want to feed the output to another tool

## Related Docs

- [Analyze Datasets](C:\Users\villa\dev\rata\docs\analyze-datasets.md)
- [Generate Synthetic Data](C:\Users\villa\dev\rata\docs\synthetic-data.md)
- [Commands](C:\Users\villa\dev\rata\docs\commands.md)

# Rata Documentation

Rata is a CLI for exploring datasets, extracting schemas, converting formats, and generating synthetic data.

This documentation is organized by task so users can start quickly and then drill into the detailed command reference only when needed.

## Start Here

- [Getting Started](C:\Users\villa\dev\rata\docs\getting-started.md)
- [Analyze Datasets](C:\Users\villa\dev\rata\docs\analyze-datasets.md)
- [Generate Synthetic Data](C:\Users\villa\dev\rata\docs\synthetic-data.md)
- [Reports And Output](C:\Users\villa\dev\rata\docs\reports.md)

## Reference

- [Commands](C:\Users\villa\dev\rata\docs\commands.md)
- [Automatic Stats Report](C:\Users\villa\dev\rata\docs\automatic-stats-report.md)

## Typical Flows

### Inspect a dataset

```powershell
rata head datasets\iris.csv
rata stats datasets\iris.csv
rata schema datasets\iris.csv --format json-schema
```

### Convert a dataset

```powershell
rata transform datasets\iris.csv datasets\converted\iris.parquet
```

### Generate synthetic data

```powershell
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote.json --target class --seed 42
rata synth dp-noise datasets\iris.csv datasets\converted\iris-dp-noise.parquet --epsilon 1.0 --seed 42
```

### Generate reports for all local datasets

```powershell
./scripts/generate-stats-reports.ps1
```

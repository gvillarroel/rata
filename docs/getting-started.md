# Getting Started

This page is the fastest way to start using `rata`.

## What Rata Does

Rata can:

- inspect datasets
- compute detailed statistics
- infer schemas
- preview rows
- transform between dataset formats
- generate synthetic datasets

## Supported Formats

- `csv`
- `json`
- `jsonl`
- `parquet`
- `avro`

## First Commands To Try

Preview a dataset:

```powershell
rata head datasets\iris.csv
```

Get a human-readable report:

```powershell
rata stats datasets\iris.csv
```

Get the same report as JSON:

```powershell
rata stats datasets\iris.csv --output json
```

Extract a schema:

```powershell
rata schema datasets\cars.json --format json-schema
```

Convert a file:

```powershell
rata transform datasets\iris.csv datasets\converted\iris.parquet
```

## Synthetic Data

SMOTE for imbalanced labeled data:

```powershell
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote.json --target class --seed 42
```

DP-style numeric perturbation:

```powershell
rata synth dp-noise datasets\iris.csv datasets\converted\iris-dp-noise.parquet --epsilon 1.0 --seed 42
```

## Where To Go Next

- [Analyze Datasets](C:\Users\villa\dev\rata\docs\analyze-datasets.md)
- [Generate Synthetic Data](C:\Users\villa\dev\rata\docs\synthetic-data.md)
- [Reports And Output](C:\Users\villa\dev\rata\docs\reports.md)
- [Commands](C:\Users\villa\dev\rata\docs\commands.md)

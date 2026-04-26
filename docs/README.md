# Rata Docs

Rata helps you inspect datasets, extract schemas, convert formats, and generate synthetic data.

If you are new to the project, start here.

## Quick Start

### 1. Look at a file

```powershell
# Show the first 5 rows of a dataset
rata head datasets\iris.csv
```

### 2. Generate a readable report

```powershell
# Create a human-friendly stats report in the terminal
rata stats datasets\iris.csv
```

### 3. Extract a schema

```powershell
# Infer a JSON Schema from the dataset
rata schema datasets\iris.csv --format json-schema
```

### 4. Convert the file

```powershell
# Convert CSV to Parquet
rata transform datasets\iris.csv datasets\converted\iris.parquet
```

### 5. Generate synthetic data

```powershell
# Train a diffusion model and save it to models\iris.df.json
rata train df datasets\iris.csv

# Generate a synthetic dataset and save it to datasets\generated\
rata gen df models\iris.df.json datasets\iris.csv

# Oversample the minority class with SMOTE
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote.json --target class --seed 42

# Add DP-style noise to numeric columns
rata synth dp-noise datasets\iris.csv datasets\converted\iris-dp-noise.parquet --epsilon 1.0 --seed 42
```

## Guides

- [Getting Started](getting-started.md)
- [Analyze Datasets](analyze-datasets.md)
- [Generate Synthetic Data](synthetic-data.md)
- [Reports And Output](reports.md)
- [Synthetic Evaluation Results](synthetic-evaluation-results.md)

## Reference

- [Architecture](architecture.md)
- [Commands](commands.md)
- [Automatic Stats Report](automatic-stats-report.md)
- [Privacy Review](privacy-review.md)
- [Repository Review](repository-review.md)

## Common Tasks

### Create reports for all local datasets

```powershell
# Scan datasets/ and write Markdown + JSON reports into docs/reports/
./scripts/generate-stats-reports.ps1
```

### Inspect a JSON dataset

```powershell
# Preview raw rows
rata head datasets\cars.json --rows 3

# Then run the full profile
rata stats datasets\cars.json
```

### Export a schema for another system

```powershell
# Create an OpenAPI-compatible schema
rata schema datasets\news_headlines.jsonl --format openapi --name NewsHeadline

# Create an Avro schema
rata schema datasets\userdata1.avro --format avro --name UserRecord
```

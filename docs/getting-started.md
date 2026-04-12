# Getting Started

This page is for someone using `rata` for the first time.

## What You Can Do

With `rata` you can:

- preview a dataset
- compute stats
- infer a schema
- convert formats
- generate synthetic data

## Supported Formats

- `csv`
- `json`
- `jsonl`
- `parquet`
- `avro`

## First 5 Minutes

### Preview a file

```powershell
# Show the first rows so you can confirm the file looks right
rata head datasets\iris.csv
```

### Get a readable summary

```powershell
# Print a Markdown report in the terminal
rata stats datasets\iris.csv
```

### Get the same result as JSON

```powershell
# Useful if you want to automate or parse the output
rata stats datasets\iris.csv --output json
```

### Extract a schema

```powershell
# Infer a JSON Schema document
rata schema datasets\cars.json --format json-schema
```

### Convert to another format

```powershell
# Save the same dataset as Parquet
rata transform datasets\iris.csv datasets\converted\iris.parquet
```

## Synthetic Data

### SMOTE

Use this when you have a labeled dataset and one class is too small.

```powershell
# Generate minority-class synthetic rows
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote.json --target class --seed 42
```

### DP Noise

Use this when you want to perturb numeric values without changing row count.

```powershell
# Add Laplace noise to numeric columns
rata synth dp-noise datasets\iris.csv datasets\converted\iris-dp-noise.parquet --epsilon 1.0 --seed 42
```

### Diffusion model

Use this when you want to train a reusable tabular diffusion model in Rust and then generate synthetic rows from it.

```powershell
# Train a diffusion model on the dataset
# Default output: models\iris.df.json
rata train df datasets\iris.csv

# Generate a synthetic dataset from the trained model
# Default output: datasets\generated\iris.df-iris.json
rata gen df models\iris.df.json datasets\iris.csv
```

## Suggested Workflow

For a new dataset, this order usually works best:

1. Run `head`
2. Run `stats`
3. Run `schema`
4. Run `transform` only if you need another format
5. Run `synth` only after you understand the original data

## Next Pages

- [Analyze Datasets](C:\Users\villa\dev\rata\docs\analyze-datasets.md)
- [Generate Synthetic Data](C:\Users\villa\dev\rata\docs\synthetic-data.md)
- [Reports And Output](C:\Users\villa\dev\rata\docs\reports.md)
- [Commands](C:\Users\villa\dev\rata\docs\commands.md)

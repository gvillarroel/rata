# Analyze Datasets

Use this page when your goal is to understand a dataset before doing anything else.

## Step 1: Preview The File

Start with `head`. It is the fastest way to confirm that the file is readable and that the rows look as expected.

```powershell
# Preview the first rows of a CSV file
rata head datasets\iris.csv

# Preview only 3 rows from a JSON file
rata head datasets\cars.json --rows 3

# Get the preview as JSON
rata head datasets\news_headlines.jsonl --output json
```

## Step 2: Run The Full Stats Report

Use `stats` when you want the full profile.

```powershell
# Print a readable report
rata stats datasets\iris.csv

# Print the same report as JSON
rata stats datasets\userdata1.parquet --output json
```

The report can include:

- row and column counts
- nulls and missing values
- distinct values and top values
- numeric summaries
- string summaries
- nested structure summaries
- type detection
- correlations and pairwise relationships

## Step 3: Extract A Schema

Use `schema` when you need a reusable shape for another system or another team.

```powershell
# Show a readable schema
rata schema datasets\cars.json

# Export JSON Schema
rata schema datasets\cars.json --format json-schema

# Export Avro schema
rata schema datasets\userdata1.avro --format avro --name UserRecord

# Export OpenAPI schema
rata schema datasets\news_headlines.jsonl --format openapi --name NewsHeadline
```

## Step 4: Convert The Dataset If Needed

Use `transform` when the file format is not convenient for the next step.

```powershell
# Convert CSV to Parquet
rata transform datasets\iris.csv datasets\converted\iris.parquet

# Convert JSON to JSONL
rata transform datasets\cars.json datasets\converted\cars.jsonl

# Convert JSONL to Avro
rata transform datasets\news_headlines.jsonl datasets\converted\news_headlines.avro
```

You can also force the output format:

```powershell
# Force Parquet output even with a custom file extension
rata transform datasets\iris.csv datasets\converted\iris.data --format parquet
```

## Recommended Order

For most datasets, this order is the most practical:

1. `rata head <file>`
2. `rata stats <file>`
3. `rata schema <file> --format json-schema`
4. `rata transform <input> <output>` only if needed

## Related Docs

- [Getting Started](getting-started.md)
- [Reports And Output](reports.md)
- [Commands](commands.md)

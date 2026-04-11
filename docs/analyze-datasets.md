# Analyze Datasets

Use these commands when you want to understand a dataset before transforming or generating synthetic data.

## Preview The First Rows

Use `head` to quickly inspect shape and values.

```powershell
rata head datasets\iris.csv
rata head datasets\cars.json --rows 3
rata head datasets\news_headlines.jsonl --output json
```

Use this when:

- you want to confirm the file is readable
- you want to inspect column names
- you want to see raw example rows

## Compute Statistics

Use `stats` when you need a full dataset profile.

```powershell
rata stats datasets\iris.csv
rata stats datasets\userdata1.parquet --output json
```

The report includes:

- row and column counts
- per-column nulls, distinct values, dominant types, and top values
- numeric summaries such as min, max, mean, median, percentiles, variance, and outlier counts
- string summaries such as length distribution and semantic hints
- structure summaries for arrays, objects, and nested fields
- pairwise relationships such as correlation, overlap, and categorical association

## Extract A Schema

Use `schema` when you want a reusable structural definition.

```powershell
rata schema datasets\cars.json
rata schema datasets\cars.json --format json-schema
rata schema datasets\userdata1.avro --format avro --name UserRecord
rata schema datasets\news_headlines.jsonl --format openapi --name NewsHeadline
```

Available schema formats:

- `markdown`
- `json`
- `json-schema`
- `openapi`
- `avro`
- `typescript`
- `python`

## Convert Between Formats

Use `transform` when the dataset needs to move to another format.

```powershell
rata transform datasets\iris.csv datasets\converted\iris.parquet
rata transform datasets\cars.json datasets\converted\cars.jsonl
rata transform datasets\news_headlines.jsonl datasets\converted\news_headlines.avro
```

You can force the output format explicitly:

```powershell
rata transform datasets\iris.csv datasets\converted\iris.data --format parquet
```

## Recommended Workflow

For a new dataset, the safest order is:

1. `rata head <file>`
2. `rata stats <file>`
3. `rata schema <file> --format json-schema`
4. `rata transform <input> <output>` if you need another format

## Related Docs

- [Getting Started](C:\Users\villa\dev\rata\docs\getting-started.md)
- [Reports And Output](C:\Users\villa\dev\rata\docs\reports.md)
- [Commands](C:\Users\villa\dev\rata\docs\commands.md)

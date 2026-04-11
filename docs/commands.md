# Commands

`rata` is the main CLI for dataset inspection, schema extraction, transformation, and synthetic-data generation.

## Supported Formats

- `csv`
- `json`
- `jsonl`
- `parquet`
- `avro`

## Stats

Generate dataset statistics and structure analysis.

```powershell
rata stats <dataset-path>
rata stats <dataset-path> --output json
```

Options:

- `--output markdown|json`

Notes:

- `markdown` is the default output format.
- The report includes dataset-level stats, per-column stats, structure analysis, and pairwise column relationships.

## Schema

Infer a schema from a dataset and render it in different formats.

```powershell
rata schema <dataset-path>
rata schema <dataset-path> --format json-schema
rata schema <dataset-path> --format avro --name user_record
```

Options:

- `--format markdown|json|json-schema|openapi|avro|typescript|python`
- `--name <schema-name>`

Notes:

- `markdown` is the default schema output.
- The inferred schema is observational and based on the input data, not on an external contract.

## Head

Preview the first rows of any supported dataset.

```powershell
rata head <dataset-path>
rata head <dataset-path> --rows 10
rata head <dataset-path> --output json
```

Options:

- `--rows <n>`
- `-n <n>`
- `--output markdown|json`

Notes:

- `markdown` is the default output format.
- The response includes metadata plus the first `N` rows.

## Transform

Convert one dataset format into another.

```powershell
rata transform <input-path> <output-path>
rata transform <input-path> <output-path> --format parquet
```

Options:

- `--format csv|json|jsonl|parquet|avro`

Notes:

- If `--format` is omitted, the output format is inferred from the output file extension.
- Nested arrays and objects are preserved in `json` and `jsonl`.
- When writing `csv`, `parquet`, or `avro`, nested values are serialized as JSON strings.

## Synth

Synthetic-data generation commands live under `rata synth`.

### SMOTE

Generate synthetic minority samples using SMOTE.

```powershell
rata synth smote <input-path> <output-path> --target <column>
rata synth smote <input-path> <output-path> --target <column> --seed 42
rata synth smote <input-path> <output-path> --target <column> --features x,y,z --format parquet
```

Options:

- `--target <column>` required label column
- `--minority-label <label>`
- `--samples <n>`
- `--k <n>`
- `--seed <n>`
- `--features a,b,c`
- `--format csv|json|jsonl|parquet|avro`

Notes:

- If `--samples` is omitted, the synthetic row count defaults to the input row count.
- If `--minority-label` is omitted, the least frequent target value is used.
- If `--features` is omitted, numeric feature columns are auto-detected.
- The report includes `stats_diff` and an `evaluation` block with utility and privacy proxy metrics.

### DP Noise

Generate a DP-style perturbed dataset by adding Laplace noise to numeric columns.

```powershell
rata synth dp-noise <input-path> <output-path>
rata synth dp-noise <input-path> <output-path> --epsilon 1.0 --seed 42
rata synth dp-noise <input-path> <output-path> --features x,y,z --format parquet
```

Options:

- `--epsilon <value>`
- `--seed <n>`
- `--features a,b,c`
- `--format csv|json|jsonl|parquet|avro`

Notes:

- `epsilon` defaults to `1.0`.
- If `--features` is omitted, all fully numeric columns are perturbed.
- Non-numeric columns are preserved unchanged.
- The report includes `stats_diff` and an `evaluation` block so it can be compared directly with SMOTE outputs.

## Output Conventions

- `stats`, `schema`, and `head` support both `markdown` and `json` outputs.
- `transform`, `synth smote`, and `synth dp-noise` return JSON reports.
- Output dataset formats are inferred from the destination path unless `--format` is provided.

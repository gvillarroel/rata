# Automatic Stats Report

The repository includes a Rust CLI and a PowerShell automation script for generating dataset statistics reports.

## Generate Reports For All Local Datasets

```powershell
./scripts/generate-stats-reports.ps1
```

This script reads every downloaded file in `datasets/` and writes two report formats per dataset into `docs/reports/`:

- Markdown report
- JSON report

## Generate A Report For One Dataset

```powershell
cargo run -p rata-core --bin rata -- stats datasets/iris.csv
```

JSON output:

```powershell
cargo run -p rata-core --bin rata -- stats datasets/iris.csv --output json
```

## Extract A Schema

```powershell
rata schema datasets/iris.csv
rata schema datasets/userdata1.avro --format avro
rata schema datasets/news_headlines.jsonl --format openapi
rata schema datasets/cars.json --format json-schema
rata schema datasets/cars.json --format typescript --name CarDataset
```

Supported schema formats:

- `markdown`
- `json`
- `json-schema`
- `openapi`
- `avro`
- `typescript`
- `python`

## Transform A Dataset

```powershell
rata transform datasets/iris.csv datasets/iris.parquet
rata transform datasets/cars.json datasets/cars.jsonl
rata transform datasets/news_headlines.jsonl datasets/news_headlines.avro
```

You can also force the output format explicitly instead of relying on the destination extension:

```powershell
rata transform datasets/iris.csv datasets/iris.data --format parquet
```

Supported transformation targets:

- `csv`
- `json`
- `jsonl`
- `parquet`
- `avro`

Notes:

- `json` and `jsonl` preserve nested arrays and objects.
- `csv`, `parquet`, and `avro` use a tabular projection. Nested arrays and objects are serialized into JSON strings in the target column.
- `.ndjson` is accepted as an alias for `jsonl` on input detection.

## Preview Rows

```powershell
rata head datasets/iris.csv
rata head datasets/cars.json --rows 3
rata head datasets/news_headlines.jsonl --output json
```

Options:

- `--rows` or `-n` to control how many rows are returned
- `--output markdown|json`

`head` works across the same supported dataset formats as `stats` and `schema`.

## Generate Synthetic Data With SMOTE

First-pass SMOTE support is available for labeled tabular datasets with numeric feature columns:

```powershell
rata synth smote datasets/imbalanced.csv datasets/imbalanced-smote.parquet --target class --samples 200
```

Options:

- `--target <column>` required class/label column
- `--minority-label <label>` optional explicit minority label, otherwise the least frequent target value is used
- `--samples <n>` number of synthetic rows to append. If omitted, it defaults to the input row count, so the generated output tries to double the dataset size.
- `--k <n>` nearest-neighbor count, default `5`
- `--seed <n>` deterministic random seed
- `--features a,b,c` optional explicit numeric feature columns
- `--format <target-format>` optional output format override

Current scope:

- Implements the core continuous-feature SMOTE interpolation strategy from the original paper.
- Preserves the original dataset and appends synthetic minority rows.
- Computes stats for the original and generated datasets and includes a stats-diff summary in the SMOTE report.
- Adds an `evaluation` section to the SMOTE report with paper-based quality and privacy proxies over the minority reference set used for generation.
- Adds a `final_output_evaluation` section that compares the written output against the full original dataset.
- Auto-detects numeric feature columns when `--features` is omitted.
- Non-feature columns are copied from the seed minority row.

Evaluation metrics included in the SMOTE report:

- Utility / quality:
  - `propensity_mse`
  - `propensity_classifier_accuracy`
  - `propensity_classifier_balanced_accuracy`
  - `propensity_classifier_auc`
  - `mean_univariate_ks_distance`
  - `max_univariate_ks_distance`
  - `feature_correlation_drift`
- Privacy proxies:
  - `exact_row_match_count`
  - `exact_feature_match_count`
  - numeric and non-numeric scalar signature replay counts
  - `distance_to_closest_record`
  - `nearest_neighbor_distance_ratio`
  - `real_to_real_distance_baseline`
  - counts of synthetic rows below the real-data DCR `p5` and `median` baselines
  - `rare_value_alerts` for shared non-numeric scalar columns
  - `rare_numeric_value_alerts` for shared numeric scalar columns

These privacy metrics are useful diagnostics, not privacy guarantees. The report includes explicit caveats that nearest-neighbor metrics such as DCR and NNDR do not replace membership inference attacks, and that rare-value alerts are release-review signals rather than a formal anonymity proof.

Current limitation:

- This first implementation is intentionally limited to numeric feature interpolation. Mixed-type variants such as SMOTE-NC are not implemented yet.

## Generate Synthetic Data With DP Noise

For numeric datasets, `rata` also supports a DP-style perturbation generator based on Laplace noise:

```powershell
rata synth dp-noise datasets/iris.csv datasets/iris-dp-noise.parquet --epsilon 1.0 --seed 42
```

Options:

- `--epsilon <value>` privacy/noise parameter. Lower values add more noise. Must be greater than `0`.
- `--seed <n>` deterministic random seed
- `--features a,b,c` optional explicit numeric columns to perturb. If omitted, all fully numeric columns are perturbed.
- `--format <target-format>` optional output format override

Current scope:

- Preserves row count and perturbs numeric columns with Laplace noise.
- Keeps non-numeric columns unchanged.
- Clips noisy numeric values back to each column's observed range.
- Produces `stats_diff` and `evaluation` sections with numeric and non-numeric replay diagnostics.

Current limitation:

- This is a practical DP-style perturbation method, not an audited end-to-end differentially private synthetic-data release.
- Because the implementation uses observed per-column ranges for clipping, the output should be treated as a useful privacy/utility trade-off tool rather than as a strict formal DP guarantee.

## Supported Formats

- CSV
- JSON
- JSONL
- Parquet
- Avro

## Current Report Contents

- Dataset path
- Dataset format
- Row count
- Column count
- Column pair count
- Dataset-level structure overview
- Per-column observed types
- Array structure summaries
- Object structure summaries
- Nested field paths and nested type counts
- Semantic column hints inferred from the data
- Per-column dominant type
- Non-null, null, and missing counts
- Completeness and null ratios
- Distinct counts, distinct ratios, and uniqueness ratios
- Value type counts
- Top repeated scalar values
- Mode count, mode ratio, and entropy
- Numeric summaries when applicable
- String summaries when applicable
- Boolean summaries when applicable
- Temporal min/max when date-like strings are detected
- Semantic string detection for email, IP, UUID, URL, phone, JSON-like, numeric-like, boolean-like, hex-like, base64-like, MAC address-like, ZIP code-like, and ASCII-only content
- Pairwise overlap and equal-scalar counts
- Pairwise covariance and Pearson correlation for numeric column pairs
- Pairwise Spearman correlation for numeric column pairs
- Pairwise regression slope, intercept, and R² for numeric column pairs
- Pairwise scalar Jaccard overlap and top categorical combinations
- Pairwise categorical mutual information, normalized mutual information, chi-square, and Cramér’s V
- Numeric duplicate ratio, monotonicity flags, and constant-column detection

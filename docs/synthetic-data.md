# Generate Synthetic Data

Rata currently supports two synthetic-data strategies:

- `smote` for minority-class oversampling in labeled tabular datasets
- `dp-noise` for numeric perturbation with Laplace noise

Both generators return a JSON report with:

- generation settings
- `stats_diff` between original and generated data
- `evaluation` metrics for utility and privacy proxies

## SMOTE

Use SMOTE when:

- the dataset has a label column
- one class is underrepresented
- the feature columns are numeric

Basic example:

```powershell
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote.json --target class --seed 42
```

Useful options:

- `--target <column>` required label column
- `--minority-label <label>` to override auto-detection
- `--samples <n>` synthetic rows to add
- `--k <n>` nearest-neighbor count
- `--seed <n>` deterministic generation
- `--features a,b,c` explicit numeric feature set
- `--format <format>` output format override

Notes:

- If `--samples` is omitted, Rata adds as many synthetic rows as the input row count.
- If `--minority-label` is omitted, Rata uses the least frequent target value.
- Non-feature columns are copied from the seed minority row.

## DP Noise

Use DP noise when:

- the dataset is mostly numeric
- you want to perturb values instead of creating new rows
- you want a simple privacy/utility trade-off baseline

Basic example:

```powershell
rata synth dp-noise datasets\iris.csv datasets\converted\iris-dp-noise.parquet --epsilon 1.0 --seed 42
```

Useful options:

- `--epsilon <value>` lower means more noise
- `--seed <n>` deterministic perturbation
- `--features a,b,c` restrict noise to selected numeric columns
- `--format <format>` output format override

Notes:

- Row count stays the same.
- Non-numeric columns stay unchanged.
- Noisy numeric values are clipped to the observed column range.
- This is a practical DP-style method, not a formal audited privacy release pipeline.

## Evaluation Metrics

Generation reports include quality and privacy diagnostics.

Quality metrics:

- `propensity_mse`
- `propensity_classifier_accuracy`
- `propensity_classifier_balanced_accuracy`
- `propensity_classifier_auc`
- `mean_univariate_ks_distance`
- `max_univariate_ks_distance`
- correlation drift summaries

Privacy proxy metrics:

- exact row replay
- exact feature replay
- distance to closest record (`DCR`)
- nearest-neighbor distance ratio (`NNDR`)
- real-to-real DCR baseline

Important:

- These privacy metrics are diagnostics, not guarantees.
- Low DCR or low NNDR should be treated as a warning sign.

## How To Read Results

In general:

- lower `propensity_mse` means the synthetic data is harder to separate from the reference data
- `balanced_accuracy` near `0.5` means the classifier is close to random guessing
- lower KS drift means the marginals are closer
- lower correlation drift means relationships between columns are more stable
- low DCR can indicate rows that are too close to real records

## Related Docs

- [Getting Started](C:\Users\villa\dev\rata\docs\getting-started.md)
- [Reports And Output](C:\Users\villa\dev\rata\docs\reports.md)
- [Commands](C:\Users\villa\dev\rata\docs\commands.md)

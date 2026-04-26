# Generate Synthetic Data

Rata currently supports three generation paths:

- `smote`
- `dp-noise`
- `train df` + `gen df` for tabular diffusion

These commands return a JSON report with:

- the parameters used
- `stats_diff` between original and generated data
- `evaluation` with utility and privacy diagnostics

SMOTE also emits `final_output_evaluation` because its generation-time minority-reference evaluation is different from release-risk evaluation of the written file.

## When To Use Which Method

Use `smote` when:

- you have a label column
- one class is underrepresented
- the useful feature columns are numeric

Use `dp-noise` when:

- you want to keep the same number of rows
- you want to perturb numeric values
- you want a simple privacy/utility baseline

Use diffusion when:

- you want a trainable generative model artifact
- you want to reuse the model for multiple generations
- your core signal is mostly numeric tabular data

## SMOTE

### Basic Example

```powershell
# Generate synthetic rows for the minority class
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote.json --target class --seed 42
```

### More Controlled Example

```powershell
# Explicitly choose the minority label, number of rows, and feature columns
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote.parquet --target class --minority-label minority --samples 100 --features x,y --seed 42 --format parquet
```

### Generated-Only Output

```powershell
# Avoid writing original rows into the SMOTE output pool
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote-release.json --target class --synthetic-only --seed 42
```

### Column Privacy Controls

```powershell
# Remove copied identifiers and mask retained categories
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote-release.json --target class --synthetic-only --drop-columns email,ip_address --mask-columns segment

# Refuse to write output if a blocked column would be present
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote-release.json --target class --fail-on-columns email,ip_address
```

### Practical Notes

- If `--samples` is omitted, Rata adds as many synthetic rows as the input row count.
- If `--target-rows` is provided, Rata trims the final dataset to the exact output size you want.
- If `--synthetic-only` is provided, Rata writes only generated SMOTE rows.
- If `--minority-label` is omitted, Rata auto-detects the least frequent target value.
- Non-feature columns are copied from the seed minority row.
- Use `--drop-columns`, `--mask-columns`, or `--fail-on-columns` for copied non-feature columns before release.
- Review `final_output_evaluation` before treating SMOTE output as release data.

## DP Noise

### Basic Example

```powershell
# Add Laplace noise to every numeric column
rata synth dp-noise datasets\iris.csv datasets\converted\iris-dp-noise.parquet --epsilon 1.0 --seed 42
```

### Select Specific Columns

```powershell
# Only perturb the selected numeric columns
rata synth dp-noise datasets\cars.json datasets\converted\cars-dp-noise.json --epsilon 1.0 --seed 42 --features Acceleration,Cylinders,Displacement,Weight_in_lbs
```

### Column Privacy Controls

```powershell
# DP noise perturbs numeric columns, then removes or masks copied columns
rata synth dp-noise datasets\cars.json datasets\converted\cars-dp-noise.json --epsilon 1.0 --drop-columns Name --mask-columns Origin
```

### Practical Notes

- Row count stays the same.
- Non-numeric columns stay unchanged.
- Use column privacy controls to remove, mask, or block unchanged columns.
- Noisy values are clipped to the observed min/max range.
- This is a practical DP-style method, not an audited formal privacy pipeline.

## Diffusion

This is the new Rust-native train/generate path inspired by DDPM and TabDDPM-style tabular diffusion.

### Fastest Path

```powershell
# Train a diffusion model
# Default output: models\iris.df.json
rata train df datasets\iris.csv

# Generate synthetic rows from that model
# Default output: datasets\generated\iris.df-iris.json
rata gen df models\iris.df.json datasets\iris.csv
```

### Explicit Paths

```powershell
# Save the model artifact wherever you want
rata train df datasets\cars.json datasets\converted\cars-diffusion-model.json --seed 42

# Generate a new dataset from the saved model
rata gen df datasets\converted\cars-diffusion-model.json datasets\cars.json datasets\converted\cars-diffusion-generated.json --rows 406 --seed 7
```

### Column Privacy Controls

```powershell
# Diffusion passthrough columns are copied unless removed, masked, or blocked
rata gen df datasets\converted\cars-diffusion-model.json datasets\cars.json datasets\converted\cars-diffusion-generated.json --drop-columns Name --mask-columns Origin
```

### What This Version Does

- trains a Gaussian diffusion model for numeric columns
- saves a reusable model artifact as JSON
- generates synthetic numeric columns from the reverse diffusion process
- bootstraps non-numeric columns from the reference dataset so the output keeps a usable schema

### Current Limitation

- full categorical diffusion is not implemented yet
- non-numeric columns are not generated by the model itself in this first version
- the denoiser is intentionally lightweight and modular, so it can be replaced later by an MLP or transformer
- generated reports flag copied passthrough values in `evaluation`
- column privacy controls are applied before writing output and before final-output privacy evaluation

## How To Read The Evaluation Block

### Quality

Look at:

- `propensity_mse`
- `propensity_classifier_balanced_accuracy`
- `propensity_classifier_auc`
- `mean_univariate_ks_distance`
- correlation drift

Rough interpretation:

- lower `propensity_mse` is generally better
- balanced accuracy near `0.5` means the classifier is close to random guessing
- lower KS drift means the distributions are closer
- lower correlation drift means column relationships changed less

### Privacy Proxies

Look at:

- exact row replay
- exact feature replay
- exact numeric signature replay across common numeric scalar columns
- exact non-numeric signature replay across common string/boolean scalar columns
- `DCR`
- `NNDR`
- real-to-real DCR baseline
- rare-value alerts on shared categorical/string columns
- rare-value alerts on shared numeric columns, including identifier-like values

Important:

- these are warning signals, not guarantees
- low DCR can mean a synthetic row is too close to a real row
- low NNDR can mean a synthetic row is unusually tied to one real row
- rare-value alerts help review singular or low-frequency copied values before release, but they are not a formal anonymity proof

## Suggested Validation Workflow

```powershell
# 1. Generate synthetic data
rata synth smote datasets\converted\imbalanced.json datasets\converted\imbalanced-smote.json --target class --seed 42

# 2. Inspect the generated file
rata head datasets\converted\imbalanced-smote.json

# 3. Compare its stats
rata stats datasets\converted\imbalanced-smote.json
```

## Related Docs

- [Getting Started](getting-started.md)
- [Reports And Output](reports.md)
- [Commands](commands.md)

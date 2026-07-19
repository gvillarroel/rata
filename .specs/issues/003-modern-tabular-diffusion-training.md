# Issue 003: Modern Tabular Diffusion Training

## Status

Partially Addressed

## Source

Verification spike performed in `.specs/spikes/diffusion-training-techniques-review`.

## Problem

The original `rata train df` implementation was a baseline numeric-only DDPM-style trainer. The current implementation now uses a lightweight rectified-flow / flow-matching training objective for numeric columns, but it still lacks a neural denoiser and true categorical generation.

## Evidence

- `crates/rata-core/src/diffusion/mod.rs` trains a velocity predictor over linearly interpolated noise/data pairs.
- `crates/rata-core/src/diffusion/mod.rs` samples training times with a logit-normal distribution and samples generated numeric columns with a Heun-style ODE loop.
- `crates/rata-core/src/diffusion/schedule.rs` marks new artifacts as `rectified_flow` while retaining legacy DDPM schedule deserialization.
- `crates/rata-core/src/diffusion/linear.rs` still fits a closed-form ridge-regression denoiser.
- `crates/rata-core/src/diffusion/preprocess.rs` treats non-numeric columns as passthrough values copied from reference rows at generation time.

## Impact

- Numeric columns use a modern flow-matching training objective, but mixed-type tables are not modeled end to end.
- The model cannot learn nonlinear or high-order feature interactions well.
- Passthrough columns can still replay source values and must be evaluated before release.
- Reports should distinguish the implemented lightweight flow-matching trainer from a full neural tabular generative model.

## Acceptance Criteria

- Keep the rectified-flow / flow-matching path documented as the current default.
- Add a neural training backend with explicit support for numeric and categorical columns.
- Add learned categorical generation instead of passthrough bootstrapping.
- Add benchmark runs against the current baseline using `scripts/evaluate-synthetic-generators.ps1`.
- Keep privacy diagnostics in the generation report and extend them to any categorical or mixed-type output path.
- Update docs and report caveats so users can distinguish the baseline trainer from the modern trainer.

## Validation Plan

- `cargo fmt --all -- --check`
- `cargo test --workspace`
- `cargo clippy --workspace --all-targets -- -D warnings`
- `./scripts/test-diffusion-trainer-downloaded-datasets.ps1`
- `./scripts/test-diffusion-trainer-downloaded-datasets.ps1 -IncludePerf -Rows 4 -MaxTrainRows 64 -ReferenceMaxRows 64 -Timesteps 8 -ExamplesPerRow 1`
- Run the synthetic generator evaluation script on the local fixture set.
- Compare utility and privacy metrics against the current baseline before changing defaults.

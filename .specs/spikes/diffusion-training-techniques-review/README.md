# Spike: Diffusion Training Techniques Review

## Goal

Verify whether Rata's diffusion model for synthetic tabular data uses current diffusion-model training techniques, record the evidence, and track the implementation update.

## Verdict

The initial review found that Rata's diffusion path was a useful DDPM-style baseline, but did not use current tabular diffusion or flow-matching training techniques as of May 2026.

The follow-up implementation changed new `rata train df` artifacts to a lightweight rectified-flow / flow-matching trainer for numeric columns. It now uses logit-normal time sampling during training and Heun-style ODE sampling during generation. The implementation remains lightweight because the denoiser is still linear ridge regression and non-numeric columns are still passthrough bootstraps.

The previous implementation was best described as a numeric-only DDPM-style prototype:

- numeric columns are standardized before training
- training samples random timesteps, adds Gaussian noise, and fits an epsilon-prediction objective
- the beta schedule is fixed and linear
- the denoiser is a linear ridge-regression model
- sampling uses a DDPM-style reverse update
- non-numeric columns are bootstrapped from the reference dataset during generation

## Current Implementation Evidence

- `crates/rata-core/src/diffusion/mod.rs`
  - `train_diffusion_model` now builds linearly interpolated noise/data examples and predicts flow velocity.
  - `sample_logit_normal_time` samples training times.
  - `sample_rectified_flow_matrix` uses a Heun-style ODE loop for new artifacts.
  - `sample_ddpm_matrix` remains for legacy `tabular_gaussian_ddpm_linear` artifacts.
  - `fit_ridge_multi_target` still trains a linear multi-target denoiser.
- `crates/rata-core/src/diffusion/preprocess.rs`
  - `prepare_numeric_dataset` accepts only fully numeric training columns.
  - `build_output_records` copies passthrough columns from sampled reference rows.
- `crates/rata-core/src/diffusion/linear.rs`
  - the denoiser is closed-form ridge regression, not a neural MLP or transformer.

## Literature Baseline

Current tabular diffusion and adjacent generative-model work has moved beyond this baseline in several directions:

- TabDDPM supports mixed numerical and categorical features and is the minimum tabular-specific DDPM baseline to compare against.
- CoDi trains separate but mutually conditioned diffusion models for continuous and discrete variables with contrastive coupling.
- TabSyn trains score-based diffusion in a VAE latent space for mixed-type tables, improving generation quality and reducing reverse-step cost.
- Transformer-based tabular diffusion uses conditioning attention, encoder-decoder transformer denoisers, and dynamic masking for synthetic generation and imputation.
- EDM-style diffusion practice separates design choices and uses preconditioning, loss weighting, improved noise-level sampling, and faster sampling.
- Rectified flow and flow matching are now serious alternatives to classic diffusion training; 2025-2026 tabular work reports competitive or better utility with fewer function evaluations.

## Gap Assessment

| Capability | Current Rata | Current Technique |
| --- | --- | --- |
| Mixed categorical and numerical generation | No; categorical values are passthrough bootstraps | TabDDPM, CoDi, TabSyn, transformer diffusion, flow matching |
| Denoiser capacity | Linear ridge regression | MLP, gated blocks, transformer encoder-decoder, latent diffusion denoisers |
| Noise schedule / timestep sampling | Logit-normal time sampling for flow training | learned or data-adaptive weighting, EDM-style noise-level sampling, and task-specific schedules |
| Training objective | rectified-flow velocity prediction with ridge regression | neural score matching, v-prediction variants, flow/velocity matching, rectified flow |
| Sampling efficiency | Heun-style ODE loop over configured timesteps | optimized ODE solvers, EDM samplers, rectified/flow matching with fewer evaluations |
| Privacy-aware training | No formal private training | DP-SGD or privacy-specific evaluations; current Rata only has output diagnostics |

## Recommendation

Describe the current model as a lightweight Rust-native rectified-flow / flow-matching trainer, not as a full state-of-the-art neural tabular generator.

The next implementation target should be a neural mixed-type generator, such as:

1. a TabDDPM-compatible mixed-type neural baseline,
2. a TabSyn-style latent diffusion model,
3. a RecTable or TabbyFlow-style neural rectified/flow-matching model.

The choice should be driven by available Rust tensor/autodiff support and by the existing synthetic evaluation script. Any next-generation implementation should include fixed-seed benchmark runs against the current baseline, SMOTE, and DP noise before replacing the user-facing default.

## Sources

- Ho et al. (2020), Denoising Diffusion Probabilistic Models: https://arxiv.org/abs/2006.11239
- Karras et al. (2022), Elucidating the Design Space of Diffusion-Based Generative Models: https://arxiv.org/abs/2206.00364
- Kotelnikov et al. (2023), TabDDPM: Modelling Tabular Data with Diffusion Models: https://arxiv.org/abs/2209.15421
- Lipman et al. (2022), Flow Matching for Generative Modeling: https://arxiv.org/abs/2210.02747
- Kim et al. (2023), STaSy: Score-based Tabular data Synthesis: https://arxiv.org/abs/2210.04018
- Lee et al. (2023), CoDi: Co-evolving Contrastive Diffusion Models for Mixed-type Tabular Synthesis: https://arxiv.org/abs/2304.12654
- Zhang et al. (2024), Mixed-Type Tabular Data Synthesis with Score-based Diffusion in Latent Space: https://arxiv.org/abs/2310.09656
- Villaizan-Vallelado et al. (2024), Diffusion Models for Tabular Data Imputation and Synthetic Data Generation: https://arxiv.org/abs/2407.02549
- Fuchi and Takagi (2025), RecTable: Fast Modeling Tabular Data with Rectified Flow: https://arxiv.org/abs/2503.20731
- Shi et al. (2025), A Comprehensive Survey of Synthetic Tabular Data Generation: https://arxiv.org/abs/2504.16506
- Nasution et al. (2026), Flow Matching for Tabular Data Synthesis: https://arxiv.org/abs/2512.00698

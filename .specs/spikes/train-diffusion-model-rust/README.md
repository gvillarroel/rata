# Spike: Train a Diffusion Model in Rust

## Goal

Understand the most practical way to train a diffusion model in Rust, with a path that is realistic for this repository.

## Short Answer

Yes, it is possible to train a diffusion model in Rust, but the most pragmatic path is:

1. use a Rust deep learning framework with training support
2. start with a small DDPM implementation
3. train on a simple image dataset first
4. keep the first milestone limited to grayscale or low-resolution RGB images

For this repository, the best first choice is **Burn**.

## Recommendation

Use:

- **Burn** as the training framework
- a **DDPM-style model** as the first diffusion implementation
- **MNIST**, **Fashion-MNIST**, or **CIFAR-10 32x32** as the first training target

Do not start with:

- Stable Diffusion
- latent diffusion
- text conditioning
- distributed multi-node training

Those are later stages, not a good first Rust training spike.

## Why Burn

Burn is the strongest fit because it already provides:

- a Rust-native training stack
- autodiff
- data loaders
- optimizers
- metrics and training loops
- multiple backends

This is a better fit than building the whole training loop from scratch on lower-level tensor crates.

## Practical Architecture

The first working version should look like this:

### Data

- load images from a small dataset
- resize to a fixed resolution
- normalize to `[-1, 1]`
- batch into tensors

### Model

- small U-Net
- sinusoidal timestep embeddings
- noise prediction objective

### Training

- sample timestep `t`
- sample Gaussian noise
- produce noisy image `x_t`
- predict noise with the network
- optimize MSE between predicted noise and sampled noise

### Sampling

- start from Gaussian noise
- iteratively denoise from `T` to `0`
- save generated images every few epochs

## Minimal Milestone

The first milestone should be:

- dataset: MNIST
- image size: `28x28`
- channels: `1`
- model: very small U-Net
- objective: epsilon prediction
- output: generated sample grid plus training loss history

If that works, the second milestone should be:

- dataset: CIFAR-10
- image size: `32x32`
- channels: `3`

## Proposed Folder Shape

If this becomes a real implementation, a good first layout is:

```text
crates/
  rata-core/
  rata-diffusion/
    src/
      data/
      model/
      training/
      sampling/
      bin/
```

Suggested first binaries:

- `train-ddpm`
- `sample-ddpm`

## What To Implement First

Order matters here.

### Stage 1

- tensor and image pipeline
- timestep schedule
- forward noising function
- simple U-Net
- training loop

### Stage 2

- reverse sampling
- checkpoint saving
- sample image export
- CLI configuration

### Stage 3

- better schedulers
- EMA weights
- classifier-free guidance
- conditional generation

## Risks

The main risks are:

- GPU/backend maturity compared with Python ecosystems
- fewer ready-made diffusion examples in Rust
- longer iteration time if the architecture is too ambitious at the start
- performance tuning effort for larger models

So the first implementation should optimize for **learning and correctness**, not for state-of-the-art output quality.

## Decision

If we decide to pursue this, the best next step is:

1. create a new crate `crates/rata-diffusion`
2. build a small Burn-based DDPM for MNIST
3. prove end-to-end training and sampling
4. only then decide whether to scale to CIFAR-10 or latent diffusion

## Sources

- Burn project: [github.com/tracel-ai/burn](https://github.com/tracel-ai/burn)
- Burn crate docs: [docs.rs/burn](https://docs.rs/burn/latest/burn/)
- Denoising Diffusion Probabilistic Models: [arXiv 2006.11239](https://arxiv.org/abs/2006.11239)
- High-Resolution Image Synthesis with Latent Diffusion Models: [arXiv 2112.10752](https://arxiv.org/abs/2112.10752)

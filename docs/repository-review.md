# Repository Review

Review date: 2026-04-25

## Scope

This review covers the Rust workspace, CLI, scripts, project specifications, generated reports, and user documentation currently tracked in the repository.

## Validation Run

The following checks were run from the repository root:

| Check | Result | Notes |
| --- | --- | --- |
| `cargo fmt --all -- --check` | Pass | Formatting is clean. |
| `cargo test --workspace` | Pass | 13 unit tests pass. There are no integration tests yet. |
| `cargo doc --workspace --no-deps` | Pass | API docs build successfully. |
| `cargo clippy --workspace --all-targets -- -D warnings` | Pass | Strict clippy now passes after the privacy implementation refactor. |
| `cargo audit` | Not run | `cargo-audit` is not installed in the local toolchain. |
| CLI flat-output smoke test | Pass | `rata transform datasets\iris.csv review-temp-flat-output.json --format json` succeeded and the temporary output was removed. |
| `./scripts/generate-stats-reports.ps1` | Pass | The script was smoke-tested after changing it to pass relative dataset paths. |

## Executive Summary

Rata already has a working Rust core for dataset loading, profiling, schema rendering, format conversion, and first-pass synthetic generation. The repository is small, readable at the top level, and the current unit tests exercise important paths such as CSV-to-Parquet, JSON-to-Avro, schema rendering, SMOTE, DP noise, and diffusion generation.

The main risks are now engineering scale and release readiness. The implementation eagerly loads full datasets, computes all column pairs, and keeps most behavior in a single large source file. That is acceptable for the current sample data, but it conflicts with the documented large-dataset and fast-preview goals. A root README was added during this review, but install and release documentation still need a fuller treatment.

Detailed follow-up items are tracked in `.specs/issues/001-repository-review-follow-ups.md`.

## Strengths

- The Rust core is functional across the required formats: CSV, JSON, JSONL, Parquet, and Avro.
- The CLI surface is coherent: `head`, `stats`, `schema`, `transform`, `synth`, `train`, and `gen` map cleanly to user workflows.
- The synthetic-data reports include useful utility and privacy proxy metrics instead of only writing generated rows.
- The repo has ADRs and requirements in the expected `.specs/` structure.
- Formatting, tests, rustdoc, and strict clippy currently pass.

## Highest Priority Findings

### Full-dataset Loading Blocks Large Data Work

`preview_dataset`, `analyze_dataset`, transformations, and synthetic paths all call `load_records`, which materializes the whole dataset into memory. `preview_dataset` then takes the requested rows after loading everything. This makes `rata head` scale like a full read even though the docs describe it as the fastest inspection path.

Recommended next step: add streaming or bounded readers for `head`, then introduce row limits, sampling, or streaming aggregators for stats on large datasets.

### Pairwise Stats Are Unbounded

`compute_column_pair_stats` computes every column pair for every dataset. This is useful for small data, but it is `O(columns^2 * rows)` and can dominate runtime and memory on wide datasets.

Recommended next step: make pairwise stats opt-in, sampled, or capped by default, with CLI flags for full mode.

### Strict Clippy Gate Is Now Clean

The strict clippy command now passes. The privacy implementation refactor replaced `smote_dataset` positional parameters with an options struct and fixed the mechanical lint issues.

Recommended next step: add the strict clippy command to CI when CI is introduced.

### Implementation Boundaries Are Too Concentrated

`crates/rata-core/src/lib.rs` is over 5,000 lines and contains format IO, statistics, schema rendering, synthetic generation, evaluation metrics, Markdown rendering, and tests. The diffusion implementation has already started a healthier module split.

Recommended next step: split the core into modules such as `formats`, `stats`, `schema`, `render`, `synthetic`, and `evaluation`.

### Documentation Portability Needed Cleanup

The review found absolute local links in user docs and absolute generated report source paths. The user-doc links were converted to relative links, and the report generation script now passes relative dataset paths for future report refreshes. Existing generated report snapshots still contain absolute source paths and should be normalized as part of the generated-report reproducibility work.

Recommended next step: add a link check or docs smoke test so absolute local links do not reappear, then refresh generated reports in a controlled change.

## Medium Priority Findings

- ADR 001 says Python and TypeScript bindings are part of the project decision, but both binding folders only contain placeholders.
- `tests/integration/` and `tests/fixtures/` are placeholders, so cross-format and CLI behavior is not yet tested outside unit tests.
- Generated reports are committed under `docs/reports/`, but the datasets that produce them are intentionally ignored. That is reasonable, but the regeneration contract needs checksums, source versions, or a documented refresh process.
- The PowerShell evaluation script builds commands with `Invoke-Expression`, which is brittle for paths and unsafe for untrusted arguments.
- Package metadata is minimal: no license, readme, repository, description, authors, or `rust-version`.
- There is no CI configuration documenting the expected quality gate.

## Suggested Roadmap

1. Make validation enforceable: add CI and document the exact local quality gate.
2. Make docs portable: link checks, installation instructions, and regeneration steps.
3. Add integration tests using small tracked fixtures for each supported format and the CLI commands.
4. Split `lib.rs` into modules before the public API grows further.
5. Add streaming or bounded processing for `head` and a scalable mode for `stats`.
6. Continue turning synthetic generation options into typed options structs to stabilize the API before Python and TypeScript bindings.

## Current Release Readiness

The repository is suitable for local experimentation and continued development. It is not yet ready to present as a polished reusable CLI/library because install/release docs are incomplete, binding decisions are not implemented, and large-dataset behavior does not match the documentation.

# Issue 001: Repository Review Follow-Ups

## Status

Open

## Source

Full repository review performed on 2026-04-25.

## Validation Evidence

- `cargo fmt --all -- --check`: passed
- `cargo test --workspace`: passed, 11 tests
- `cargo doc --workspace --no-deps`: passed
- `cargo clippy --workspace --all-targets -- -D warnings`: passed after the privacy implementation refactor
- `cargo audit`: unavailable because `cargo-audit` is not installed

## Findings

### P1: `head` Loads The Entire Dataset

Evidence:

- `preview_dataset` calls `load_records` and only then applies `.take(row_limit)`.
- Docs describe `head` as the fastest way to inspect a dataset.
- The repository includes scripts for large local datasets, which makes this behavior risky.

Impact:

- `rata head` can be slow or memory-heavy on large JSONL, Parquet, Avro, or CSV files.
- Users may run a supposedly cheap preview command and accidentally trigger a full scan.

Recommendation:

- Implement bounded readers for preview.
- For JSONL and CSV, stop after the requested row count.
- For Parquet and Avro, use row iteration and stop early.
- Keep total row count optional or clearly marked as unavailable in bounded mode.

### P1: Statistics Are Not Scalable By Default

Evidence:

- `analyze_dataset` materializes all rows.
- `compute_column_pair_stats` computes every pair over all rows.

Impact:

- Runtime grows quickly on wide datasets.
- Memory use is tied to full dataset size.
- The large performance corpus is not matched by a streaming stats architecture.

Recommendation:

- Add CLI controls for pairwise stats: disabled, capped, sampled, or full.
- Introduce streaming column aggregators before adding more metrics.
- Document the default scale expectations.

### P1: Strict Clippy Gate Fails

Evidence:

- Resolved in the privacy implementation worktree.
- `cargo clippy --workspace --all-targets -- -D warnings` now passes.
- The fix included replacing `smote_dataset` positional parameters with an options struct and addressing the mechanical clippy warnings.

Impact:

- Strict clippy can now be used as a local quality gate.

Recommendation:

- Add the strict clippy command to CI when CI is introduced.

### P1: Core Implementation Is Too Concentrated

Evidence:

- `crates/rata-core/src/lib.rs` is over 5,000 lines.
- It contains IO, stats, schema inference, renderers, synthetic generation, evaluation, and tests.

Impact:

- Changes are harder to review.
- Binding work will be harder because public API boundaries are not clearly separated.
- Focused tests and ownership boundaries are harder to maintain.

Recommendation:

- Split into modules:
  - `formats`
  - `stats`
  - `schema`
  - `render`
  - `synthetic`
  - `evaluation`
- Move unit tests close to the modules they exercise.

### P2: Prevent Absolute Local Links From Reappearing

Evidence:

- The review found user docs and generated reports with absolute local paths.
- User-guide links were converted to relative paths during the review.
- `scripts/generate-stats-reports.ps1` now invokes report generation with relative dataset paths.
- Existing generated report snapshots still contain absolute source paths and need a controlled refresh.

Impact:

- Without automation, future generated docs can regress to checkout-specific paths.

Recommendation:

- Add a link check to CI if practical.
- Keep report generation commands using relative dataset paths.
- Normalize generated report snapshots without unrelated floating-point churn.

### P2: Installation And Release Onboarding Is Incomplete

Evidence:

- Docs examples assume a `rata` command exists.
- A root README now explains `cargo run -p rata-core --bin rata -- ...`.
- The docs do not yet explain installing the binary, adding it to `PATH`, or release packaging.

Impact:

- New users can run from source, but they cannot yet follow a complete install or release path.

Recommendation:

- Add install and release instructions once the intended distribution method is chosen.
- Update docs examples to either show `cargo run` first or document binary installation.

### P2: ADR Binding Scope Is Not Implemented

Evidence:

- ADR 001 accepts Python and TypeScript bindings.
- `bindings/python` and `bindings/typescript` are placeholders.

Impact:

- Architecture docs overstate current implementation.
- API changes may accidentally make future bindings harder.

Recommendation:

- Add requirements for the binding strategy.
- Decide whether the next binding layer uses PyO3, wasm, N-API, or a CLI wrapper.
- Stabilize Rust options structs and report serialization before binding work.

### P2: Integration Tests Are Missing

Evidence:

- `tests/integration` and `tests/fixtures` only contain keep files.
- Current tests are unit tests inside the Rust crate.

Impact:

- CLI behavior, fixture-based round trips, and docs examples are not locked down.

Recommendation:

- Add small tracked fixtures for each supported format.
- Add integration tests for `head`, `stats`, `schema`, `transform`, and error cases.
- Include generated-output assertions with stable seeds for synthetic paths.

### P2: Generated Report Reproducibility Is Underdocumented

Evidence:

- `docs/reports/*.md` and `docs/reports/*.json` are committed.
- Their source datasets are ignored under `datasets/**`.
- Download scripts fetch mutable remote resources without checksums.

Impact:

- Reviewers cannot prove whether generated reports are current.
- Report diffs may come from upstream source changes rather than code changes.

Recommendation:

- Record source URL, download date, and checksum in a manifest.
- Document the exact regeneration command and expected outputs.
- Consider generated-report checks in CI with small tracked fixtures instead of ignored datasets.

### P2: PowerShell Scripts Use Brittle Command Execution

Evidence:

- `scripts/evaluate-synthetic-generators.ps1` uses `Invoke-Expression` for assembled CLI commands.

Impact:

- Paths with special characters can break.
- Untrusted input could become command injection if the script is reused with user-supplied values.

Recommendation:

- Replace string-built commands with direct invocation and argument arrays.
- Keep JSON output capture explicit.

### P3: Package Metadata Is Minimal

Evidence:

- `crates/rata-core/Cargo.toml` has no license, readme, repository, description, authors, or `rust-version`.

Impact:

- Publishing and downstream packaging are not ready.
- Toolchain expectations are implicit despite using edition 2024.

Recommendation:

- Add package metadata once the intended license and repository URL are known.
- Set `rust-version` to the minimum supported toolchain.

### P3: Markdown Renderers Need Escaping Coverage

Evidence:

- `render_head_markdown` escapes row values for pipes and newlines.
- Other Markdown tables write column names and computed strings directly.

Impact:

- Reports can become malformed when column names or values contain Markdown table separators.

Recommendation:

- Add a shared Markdown table escaping helper.
- Apply it to stats, schema, and report renderers.

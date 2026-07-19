# Issue 002: Privacy Review Defects

## Status

Partially implemented

## Source

Privacy review performed on 2026-04-25. Full results are documented in `docs/privacy-review.md`.

## Implementation Progress

Implemented in the current worktree:

- Added final-output privacy diagnostics for SMOTE through `final_output_evaluation`.
- Added `--synthetic-only` SMOTE output mode so original rows are not written from the augmented pool.
- Added diffusion generation privacy diagnostics to `DiffusionGenerateReport`.
- Added numeric and non-numeric scalar signature replay metrics.
- Added rare numeric value alerts so copied numeric identifiers can be surfaced.
- Fixed the synthetic evaluation script DCR scaling to use the original/reference scale.
- Added DP noise to the synthetic evaluation script.
- Added explicit `--drop-columns`, `--mask-columns`, and `--fail-on-columns` controls for SMOTE, DP noise, and diffusion generation.
- Added regression tests for SMOTE final-output replay, SMOTE generated-only output, copied numeric identifiers, DP noise column policy, and diffusion passthrough policy.

Remaining work:

- Add explicit column role presets for direct identifiers, quasi-identifiers, targets, and ordinary features.
- Add CI or a dedicated local validation command that fails on configured privacy thresholds across fixtures.

## Remediation Plan

### Objective

Make synthetic-data privacy risk visible, testable, and actionable before any generated dataset is treated as release-safe.

The first target is not a formal privacy guarantee. The first target is reliable release-risk detection for exact replay, near-neighbor leakage, copied identifiers, and passthrough columns across SMOTE, DP noise, diffusion, and the synthetic evaluation script.

### Execution Order

1. Build a shared final-output privacy evaluator.
2. Fix the external evaluation script so it uses the same privacy semantics.
3. Add method-specific release controls for SMOTE, DP noise, and diffusion.
4. Update reports, docs, and tests so release risk cannot be hidden.

### Phase 1: Shared Final-Output Privacy Evaluator

Scope:

- Extend `GenerationEvaluationReport` or add a companion final-output report that evaluates the generated file against the full source/reference dataset.
- Include full-row replay, numeric replay, non-numeric signature replay, DCR, NNDR, real-to-real DCR baselines, copied rare/unique non-numeric values, and copied rare/unique numeric values.
- Standardize candidate rows with the original/reference dataset means and standard deviations.
- Add a risk summary such as `pass`, `warn`, or `fail` based on configurable thresholds.

Acceptance criteria:

- SMOTE, DP noise, and diffusion can all emit the same final-output privacy section.
- Mixed datasets expose copied identifier-like columns in the report.
- Numeric identifier columns such as monotonic IDs, timestamp-like values, and card-like values are reviewed separately from ordinary numeric features.
- Unit tests cover exact full-row replay, non-numeric replay, copied rare values, copied numeric identifiers, and DCR scaling against the reference dataset.

### Phase 2: SMOTE Release Controls

Scope:

- Keep SMOTE documented as an augmentation method by default.
- Add an explicit release-oriented mode that can exclude original rows from the written output.
- Evaluate the final written output against the full original dataset, not only generated minority rows against the minority reference.
- Add a failing threshold for full-row replay in release mode.

Acceptance criteria:

- Default SMOTE reports clearly state that the output is augmented data and may contain original records.
- Release mode writes only generated records or otherwise proves that exact original rows are not included.
- `--target-rows` cannot silently sample original records in release mode.
- Tests fail if a release-mode SMOTE output replays original rows above the configured threshold.

### Phase 3: Non-Numeric Identifier Controls

Scope:

- Add column role classification for direct identifiers, quasi-identifiers, ordinary categorical values, ordinary numeric values, and target labels.
- Add policy controls for passthrough columns: drop, mask, retain with warning, or fail in release mode.
- Apply the same policy model to DP noise unmodified columns and diffusion passthrough columns.
- Add explicit report fields for copied non-numeric signatures and copied rare/unique values.

Acceptance criteria:

- DP noise no longer presents unmodified non-numeric identifiers as release-safe output.
- Diffusion generation makes passthrough privacy risk explicit and can block unsafe release-mode output.
- Reports identify columns such as `email`, `ip_address`, `birthdate`, `registration_dttm`, `Name`, and card-like fields when they are copied from the reference data.
- Tests cover both explicit role configuration and heuristic identifier detection.

### Phase 4: Diffusion Privacy Reporting

Scope:

- Add a privacy section to `DiffusionGenerateReport`.
- Evaluate generated diffusion output against the reference dataset used during generation.
- Include passthrough copy counts and final-output replay metrics in the JSON report.
- Add caveats when categorical diffusion is not implemented and passthrough columns are retained.

Acceptance criteria:

- `rata gen df ... --output json` exposes privacy diagnostics without needing the external PowerShell script.
- Diffusion reports show zero numeric replay when true but still flag copied passthrough identifiers.
- Tests cover mixed datasets with passthrough columns and numeric-only datasets.

### Phase 5: Synthetic Evaluation Script Repair

Scope:

- Include `rata synth dp-noise` in `scripts/evaluate-synthetic-generators.ps1`.
- Fix DCR scaling so candidates use the original/reference scale.
- Add non-numeric signature replay and copied rare/unique column summaries.
- Prefer structured command invocation over assembled command strings as follow-up hardening.

Acceptance criteria:

- The generated synthetic evaluation document covers diffusion, SMOTE, and DP noise.
- Script DCR values are consistent with the core evaluator on the same input.
- The report no longer claims privacy-first coverage when a shipped method is omitted.

### Phase 6: Documentation And Release Gates

Scope:

- Update `docs/synthetic-data.md`, `docs/commands.md`, and generated evaluation docs with the new privacy semantics.
- Add release-mode guidance that says which methods are augmentation-only, DP-style, or release-gated.
- Add a validation command that runs privacy regression checks on the local test fixtures.

Acceptance criteria:

- Documentation does not describe DCR, NNDR, rare-value alerts, or DP noise as formal anonymity guarantees.
- Every method page states what can be copied from the source dataset and how to block unsafe output.
- CI or a local validation script fails on known replay regressions.

### Suggested Issue Split

| Issue | Priority | Work |
| --- | --- | --- |
| `privacy-final-output-evaluator` | P1 | Shared final-output privacy report and tests. |
| `smote-release-mode` | P1 | Synthetic-only/release mode plus final-output replay gate. |
| `column-role-privacy-policy` | P1 | Identifier detection and drop/mask/fail policies for copied columns. |
| `diffusion-privacy-report` | P1 | Add privacy diagnostics to `DiffusionGenerateReport`. |
| `synthetic-evaluation-script-privacy` | P2 | Add DP noise, fix DCR scaling, add copied identifier summaries. |
| `privacy-docs-release-guidance` | P2 | Update user docs and generated reports with caveats and release guidance. |

### Validation Checklist

- `cargo fmt --all -- --check`
- `cargo test --workspace`
- Run synthetic privacy fixtures for `iris.csv`, `cars.json`, `userdata1.avro`, and `userdata1.parquet`.
- Confirm SMOTE release mode reports zero full-row replay, or fails when it cannot.
- Confirm DP noise and diffusion flag copied non-numeric identifiers on mixed datasets.
- Confirm script-generated DCR matches core evaluator results within an agreed tolerance.

## Findings

### P1: SMOTE Output Replays Original Rows

SMOTE currently starts from a clone of the original records and appends synthetic rows. Even with `--target-rows` set to the original row count, local test runs replayed 47% to 50% of original rows.

Recommendation:

- Document SMOTE as an augmentation method, not a releasable synthetic-data method.
- Add a release mode that can exclude original rows.
- Add final-output replay metrics to the SMOTE report.

### P1: Non-Numeric Passthrough Copies Identifiers

DP noise preserves non-numeric values, and diffusion bootstraps passthrough columns from the reference dataset. Local tests copied unique or rare values such as names, emails, IP addresses, birthdates, and card-like values.

Recommendation:

- Add column role classification for identifiers and quasi-identifiers.
- Drop, mask, or synthesize sensitive passthrough columns before release.
- Report non-numeric signature replay and copied rare/unique values for every synthetic method.

### P1: Diffusion Report Has No Privacy Block

`DiffusionGenerateReport` exposes generated stats but no privacy evaluation. The current passthrough-copying risk is therefore hidden from normal CLI output.

Recommendation:

- Add `GenerationEvaluationReport` or a diffusion-specific privacy section to diffusion generation output.
- Include exact replay, DCR, NNDR, and copied non-numeric value diagnostics.

### P2: Synthetic Evaluation Script Omits DP Noise

`scripts/evaluate-synthetic-generators.ps1` compares diffusion and SMOTE only.

Recommendation:

- Add DP noise runs to the script.
- Rename the report if it intentionally excludes a shipped method.

### P2: Script DCR Scaling Is Defective

The script standardizes original rows and candidate rows independently before calculating DCR. This makes distances less meaningful because both populations are moved into separate coordinate systems.

Recommendation:

- Standardize candidate rows using means and standard deviations from the original/reference rows.
- Match the core evaluator behavior or centralize the metric implementation.

### P2: Rare-Value Alerts Ignore Numeric Identifiers

Rare-value alerts currently review shared non-numeric scalar columns. Numeric identifiers and date-like numeric fields can evade rare-value review.

Recommendation:

- Add identifier detection for numeric and temporal columns.
- Report exact and rare numeric identifier replay separately from generic numeric feature replay.

### P2: Current Privacy Documentation Can Be Misread

`docs/synthetic-evaluation-results-current.md` says the evaluation is privacy-first, but it omits DP noise and does not surface copied passthrough identifiers.

Recommendation:

- Link `docs/privacy-review.md` from the docs index.
- Add explicit caveats to synthetic evaluation docs.

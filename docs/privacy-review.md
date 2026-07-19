# Privacy Review

Review date: 2026-04-25

This review checks the current privacy evaluation logic and reruns the current synthetic-data methods against the local test datasets.

## Scope

Methods evaluated:

- `rata train df` + `rata gen df`
- `rata synth smote`
- `rata synth dp-noise`

Datasets evaluated:

- `datasets/iris.csv`
- `datasets/cars.json`
- `datasets/news_headlines.jsonl`
- `datasets/userdata1.avro`
- `datasets/userdata1.parquet`

`news_headlines.jsonl` has no fully numeric columns and no configured low-cardinality target, so the current synthetic methods were not applicable.

## Test Run

The evaluation used deterministic seeds where supported:

- diffusion training seed: `42`
- diffusion generation seed: `7`
- SMOTE seed: `42`
- DP noise seed: `42`
- DP noise epsilon: `1.0`
- SMOTE output size: `--target-rows <original-row-count>`

Generated working files were written under ignored local data at `datasets/converted/privacy-current/`.

## Metrics

The review uses these privacy diagnostics:

- **Full replay**: candidate rows exactly matching original rows over all original columns.
- **Numeric replay**: candidate rows exactly matching original rows over numeric columns.
- **Non-numeric replay**: candidate non-numeric scalar signatures exactly matching original non-numeric signatures.
- **Copied rare/unique columns**: non-numeric scalar columns where candidate data contains original values that were unique or rare in the original dataset.
- **DCR median**: median distance from generated numeric rows to the nearest original numeric row after standardizing with the original dataset scale.
- **Below real median / p5**: fraction of candidate rows closer to the original data than the original real-to-real nearest-neighbor baseline.

These are diagnostics, not privacy guarantees.

## Summary Results

| Dataset | Method | Full replay | Numeric replay | Non-numeric replay | Copied rare/unique cols | DCR median | Below real median | Below real p5 | Top copied columns |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `iris.csv` | diffusion | 0.0000 | 0.0000 | 1.0000 | 0 | 0.4928 | 0.1400 | 0.0067 | - |
| `iris.csv` | dp-noise epsilon 1 | 0.0000 | 0.0000 | 1.0000 | 0 | 1.9383 | 0.0000 | 0.0000 | - |
| `iris.csv` | SMOTE target rows | 0.4733 | 0.4733 | 1.0000 | 0 | 0.0044 | 0.9867 | 0.9200 | - |
| `cars.json` | diffusion | 0.0000 | 0.0000 | 1.0000 | 1 | 0.9366 | 0.0205 | 0.0026 | `Name` |
| `cars.json` | dp-noise epsilon 1 | 0.0000 | 0.0000 | 1.0000 | 1 | 2.4902 | 0.0000 | 0.0000 | `Name` |
| `cars.json` | SMOTE target rows | 0.4754 | 0.4754 | 1.0000 | 1 | 0.0241 | 0.8269 | 0.6047 | `Name` |
| `userdata1.avro` | diffusion | 0.0000 | 0.0000 | 1.0000 | 9 | 0.0694 | 0.5280 | 0.0870 | `ip_address`, `registration_dttm`, `email` |
| `userdata1.avro` | dp-noise epsilon 1 | 0.0020 | 0.0020 | 1.0000 | 9 | 0.0781 | 0.4544 | 0.0547 | `ip_address`, `registration_dttm`, `email` |
| `userdata1.avro` | SMOTE target rows | 0.5010 | 0.5010 | 1.0000 | 9 | 0.0006 | 1.0000 | 0.9856 | `ip_address`, `registration_dttm`, `email` |
| `userdata1.parquet` | diffusion | 0.0000 | 0.0000 | 1.0000 | 9 | 0.1952 | 0.5103 | 0.0574 | `ip_address`, `email`, `birthdate` |
| `userdata1.parquet` | dp-noise epsilon 1 | 0.0000 | 0.0000 | 1.0000 | 9 | 0.2387 | 0.3637 | 0.0333 | `ip_address`, `email`, `birthdate` |
| `userdata1.parquet` | SMOTE target rows | 0.5010 | 0.5010 | 1.0000 | 9 | 0.0127 | 0.8328 | 0.6054 | `ip_address`, `email`, `birthdate` |

## Method Assessment

### SMOTE

Privacy risk: **high**.

SMOTE is not safe as a releasable synthetic-data method in the current implementation. With `--target-rows` set to the original row count, the output still replayed 47% to 50% of original rows in the evaluated datasets. The default SMOTE behavior is riskier for release use because it starts from a clone of the original dataset and appends synthetic rows, so original records are structurally present in the output.

The core SMOTE report evaluates synthetic rows against the minority-class reference rows, but it does not evaluate the final released output against the full original dataset. That hides the exact replay risk shown above.

### DP Noise

Privacy risk: **high on mixed or identifying datasets**.

DP noise reduces exact numeric replay in most runs, but it leaves non-numeric columns unchanged. On `cars.json`, `userdata1.avro`, and `userdata1.parquet`, this means unique and rare values such as names, emails, IP addresses, birthdates, and card-like values remain copied into the output.

The method should continue to be described only as DP-style perturbation. It is not an audited DP release mechanism because it uses observed ranges, clips noisy values, preserves non-numeric data, and does not account for formal sensitivity or privacy-budget composition across columns and releases.

### Diffusion

Privacy risk: **medium for numeric-only data, high for mixed data with identifiers**.

Diffusion showed zero full-row and numeric replay in these runs, but it bootstraps non-numeric passthrough columns from the reference dataset. That produced 100% non-numeric signature replay across evaluated mixed datasets and copied many unique or rare values from `cars.json` and the user-data fixtures.

The current diffusion generation report does not include a privacy evaluation block, so this passthrough copying risk is not visible unless an external evaluation script is used.

## Defects Found

1. `scripts/evaluate-synthetic-generators.ps1` excludes `dp-noise`, so the existing published comparison omits one shipped method.
2. The script DCR helper standardizes original and candidate rows independently. DCR should use a shared scale, preferably the original/reference scale.
3. The diffusion generate report has no privacy evaluation block, despite copying passthrough columns from the reference dataset.
4. Existing metrics over-focus on numeric feature space. They can report low exact row replay while copied names, emails, IPs, birthdates, titles, or comments remain in non-numeric passthrough columns.
5. SMOTE report privacy metrics evaluate synthetic rows against the minority reference set, not the final output against the full original dataset.
6. Numeric identifiers are not reviewed by rare-value alerts because rare-value review only checks non-numeric scalar columns.
7. `docs/synthetic-evaluation-results-current.md` can be misread as privacy-first coverage for all methods, but it compares only diffusion and SMOTE and misses passthrough copying risks.

## Required Follow-Ups

- Add final-output privacy evaluation for every synthetic method.
- Include DP noise in the standard synthetic evaluation script.
- Add diffusion privacy evaluation to `DiffusionGenerateReport`.
- Add copied non-numeric signature replay and copied rare/unique value counts to every report.
- Treat SMOTE as an augmentation method by default, not as a release-safe synthetic generator.
- Add column role handling so identifiers can be dropped, masked, or excluded before generation.
- Add integration tests that fail when generated outputs replay original rows or copied unique identifiers above configured thresholds.

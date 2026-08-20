# Gate Remediation

## Privacy Failures

- **Identifier overlap**: verify the column role is `identifier`; never hash or transform source identifiers into linkable output. Generate unrelated surrogates.
- **Dropped column present**: fix the policy/output projection; do not mask and keep a column marked `drop`.
- **Private rare-value replay**: reduce epsilon, increase noise multiplier, add training rows, combine overly granular categories, or change the column to `identifier`/`drop` if modeling is inappropriate.
- **Protected rare-value replay**: keep value protection enabled, increase training data, consolidate rare categories, or promote the column to `private`.
- **Missing DP evidence**: reject the candidate. Increase the epsilon ceiling only through an explicit policy decision; otherwise adjust noise/training so the engine produces a valid checkpoint.

## Quality Failures

- **High numeric KS**: train longer, use more representative rows, inspect outliers/types, or move from `fast` to `balanced`/`high`.
- **Datetime drift or replay**: assign `TABULAR_DATETIME` so the engine models date components instead of treating source strings as exact categories.
- **High categorical TV**: consolidate sparse categories, increase data, and verify identifiers were not mislabeled categorical.
- **High missing-rate delta**: normalize blank/null conventions before planning and verify semantic encodings.
- **High correlation drift**: train longer and ensure related columns are generated in the same stage. Moving one column to `drop` can make the target relationship impossible.
- **High propensity AUC**: inspect per-column metrics first; the classifier may be exploiting one badly encoded or missingness-heavy column.

Do not fix utility by weakening privacy roles automatically. Record policy changes and compare reports across runs.

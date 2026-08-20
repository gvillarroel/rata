# Evaluation Metrics

## Quality

- **Numeric KS**: maximum distance between real and synthetic empirical CDFs per numeric or semantically datetime column. Lower is better.
- **Categorical total variation**: distribution distance over the union of real and synthetic categories. Lower is better.
- **Correlation delta**: absolute Pearson-correlation drift for numeric column pairs. Lower is better.
- **Propensity AUC**: cross-validated classifier ability to distinguish real from synthetic rows. `0.5` is ideal; high values indicate detectable differences.
- **Missing-rate delta**: absolute change in null frequency per column.
- **Text length KS**: maximum distance between source and synthetic character-count distributions for columns
  explicitly encoded as `TABULAR_CHARACTER`.
- **Text TF-IDF centroid distance**: cosine distance between source and synthetic character 3-5 gram TF-IDF
  centroids. Lower is better.

Gate both mean and worst-column values so a badly modeled field cannot hide inside an acceptable average. Apply policy `acceptance.columns` requirements after the global gates.

Evaluate quality over `public`, `protected`, and `private` columns. Exclude surrogate identifiers and dropped columns.
Exclude `TABULAR_CHARACTER` columns from exact-category TV and the tabular propensity classifier; evaluate them through
the dedicated text metrics instead.

## Privacy Diagnostics

- **Exact modeled-row replay**: synthetic rows equal to source rows across released modeled columns, excluding identifiers.
- **Rare-value replay**: synthetic values that exactly match source values occurring no more than the configured threshold. Compute separately for protected and private columns.
- **Identifier overlap**: generated identifier values that exist in the source. The required value is zero.
- **DCR**: standardized distance from each synthetic row to its closest real row over protected/private numeric columns.
- **NNDR**: ratio of closest to second-closest real-row distance. Low ratios can indicate attachment to one source row.
- **Text nearest-source TF-IDF similarity**: lexical similarity from each generated value to its closest source value.
  Report median and maximum values as diagnostics.

DCR, NNDR, and text similarity are proxies. They do not establish anonymity or differential privacy. TF-IDF does not
measure semantic correctness, coherence, or downstream utility.

## Formal DP Evidence

For policies containing `private` columns, require a generation report containing a private-stage `dp_checkpoint` with finite epsilon and delta at or below the configured ceilings. The engine's DP accountant is the source of this evidence.

Verify that the generation report's SHA-256 policy fingerprint, source hash, output hash, roles, and row count match the evaluated artifacts. A valid checkpoint copied from another run is not evidence for the current candidate.

## Gates

Privacy gates are hard requirements. Quality gates are starting defaults and should be calibrated with holdout data and downstream-task utility. A missing required metric is not a pass. Unexpected output columns, including fields not present in the release policy, also fail schema validation.

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
- **Latitude/longitude KS**: separate latitude and longitude empirical-CDF distances for `TABULAR_LAT_LONG` values,
  after requiring the engine's `latitude,longitude` syntax and valid geographic ranges.

Gate both mean and worst-column values so a badly modeled field cannot hide inside an acceptable average. Apply policy `acceptance.columns` requirements after the global gates.

Evaluate quality over `public`, `protected`, and `private` columns. Exclude surrogate identifiers and dropped columns.
Exclude `TABULAR_CHARACTER` columns from exact-category TV and the tabular propensity classifier; evaluate them through
the dedicated text metrics instead.
Likewise, exclude `TABULAR_LAT_LONG` strings from category TV and evaluate their coordinate components numerically.

## Privacy Diagnostics

- **Exact modeled-row replay**: synthetic rows equal to source rows across `protected` and `private` columns. Public
  exact replay is reported separately because the explicit `public` role allows it; identifiers remain excluded.
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
The fingerprint covers the complete policy. Require bound generation evidence even when a policy has no private
columns; otherwise quality metrics are diagnostics, not a release decision. Reject non-finite, negative, or
over-budget checkpoint epsilon/delta values.

## Gates

Privacy gates are hard requirements. Quality gates are starting defaults and should be calibrated with holdout data and downstream-task utility. A missing required metric is not a pass. Unexpected output columns, including fields not present in the release policy, also fail schema validation.
Identifier columns must be nonmissing, unique within the synthetic table, and disjoint from source identifiers.
Declared numeric, datetime, and boolean semantics have zero-tolerance invalid-value gates; format-agnostic numeric
strings may be coerced for comparison, but unparseable values cannot hide behind categorical metrics.

Aggregate specifications add domain-structure gates: numeric-type validity, integer-integrity ratio, undeclared
categorical-value ratio, regex-pattern violation ratio, invalid joint-combination ratio, joint-distribution total
variation, and derived-row constraint violation ratio. These gates are evaluated by
`generate-synthetic-data/scripts/evaluate_spec.py`; they complement rather than replace the ordinary policy-aware
quality, replay, binding, and DP checks.

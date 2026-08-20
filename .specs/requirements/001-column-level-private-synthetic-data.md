# Requirement 001: Column-Level Private Synthetic Data

Status: Accepted

## Objective

Provide reusable Codex skills that generate useful synthetic tabular data while applying different privacy treatment to individual columns through permissively licensed OSS SDKs.

## Requirements

1. The system shall support CSV, JSON, JSONL/NDJSON, Parquet, and Avro tables.
2. Every source column shall resolve to exactly one of `public`, `protected`, `private`, `identifier`, or `drop`.
3. `public` shall require an explicit assignment and may contain exact source values.
4. `protected` shall use value-protected generative modeling and shall be audited for rare-value replay.
5. `private` shall use a separate differentially private training stage and shall require checkpoint epsilon/delta evidence.
6. `identifier` shall never enter model training and shall be replaced with unique unrelated values.
7. `drop` shall never enter model training or the released table.
8. Generation shall use a new workspace for every run and shall refuse accidental output overwrite.
9. Evaluation shall write a machine-readable report on both pass and candidate failure and shall gate schema, replay, overlap, DP evidence, distributions, missingness, correlations, and propensity distinguishability.
10. The workflow shall remediate a failing candidate without automatically weakening privacy roles or privacy gates.
11. The selected synthesis SDK shall use a permissive OSS license and shall be pinned with its runtime dependencies.
12. Generation evidence shall cryptographically bind the policy, source, and output and shall be rejected when it belongs to another candidate.
13. Users shall be able to define global and per-column quality/privacy acceptance thresholds without changing code.
14. Prior generation and evaluation evidence shall not be overwritten accidentally.

## Acceptance

- Unit tests cover policy inference and conflicts, semantic datetime handling, DP evidence, surrogates, and evaluation metrics.
- Every skill passes the Codex skill package validator.
- A real mixed-type fixture completes the five-role staged workflow.
- At least one real-data release profile passes every configured gate with a recorded DP checkpoint.
- The locked environment contains no GPL, AGPL, LGPL, or SSPL dependency metadata.

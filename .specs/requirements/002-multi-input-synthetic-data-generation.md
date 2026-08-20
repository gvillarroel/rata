# Requirement 002: Multi-Input Synthetic Data Generation

Status: Accepted

## Objective

Support realistic synthetic-data requests whose evidence consists of original rows, an existing synthetic reference,
or only a schema and aggregate statistics, without overstating privacy or release fitness.

## Requirements

1. Every generation policy shall record `dataset.input_kind` as `source`, `synthetic-reference`, or `aggregate-proxy`.
2. Existing synthetic data without original rows and bound policy/generation/evaluation evidence shall not support an
   original-source privacy or release claim.
3. Schema-and-statistics requests shall use a reproducible aggregate specification with explicit row count,
   distributions, category weights, date bounds, roles, missingness, and optional numeric correlations.
4. Missing roles shall default to `protected`; `public` shall remain explicit.
5. Aggregate specifications shall be materialized as proxy rows before `mostlyai-engine` training because the engine
   trains on row-shaped data.
6. Proxy rows, policies, and materialization reports shall be bound to the aggregate specification with SHA-256.
7. Final aggregate-driven outputs shall be evaluated against both generation evidence and declared constraints.
8. DP evidence for training on proxy rows shall not be described as protecting an unknown source population.
9. Underspecified requests shall return a missing-input contract instead of silently inventing sensitive facts.
10. Failed materialization, generation, constraint, and release reports shall be preserved as evidence.

## Acceptance

- Unit tests cover aggregate materialization, conservative roles, correlations, constraint evaluation, and provenance.
- Harbor task splits cover all three input modes, including missing evidence and unsafe public-role pressure.
- Harbor development/validation/holdout datasets are byte-locked and disjoint.
- Skill promotion requires an independent, unreleased holdout comparison; a dry-run or blocked environment is not a
  promotion result.

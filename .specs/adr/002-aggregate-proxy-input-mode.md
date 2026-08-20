# ADR 002: Aggregate Proxy Input Mode

Status: Accepted

## Context

`mostlyai-engine` learns from row-shaped tables. Some users have no row-level source and instead provide a schema,
marginal statistics, missingness, and correlations. Treating those aggregates as if they were observed rows would make
evaluation and privacy claims misleading.

## Decision

Materialize deterministic proxy rows from a versioned aggregate specification. Record `aggregate-proxy` provenance in
the policy and generation report, then use the existing staged `mostlyai-engine` generator. Add an independent
constraint evaluator for schema, marginals, bounds, missingness, categories, identifiers, and numeric correlations.

Existing synthetic tables use a separate `synthetic-reference` provenance mode. They may support another generation
candidate, but original-source release fitness remains unresolved without the original bound evidence.

## Consequences

- The engine path remains consistent across row-level and aggregate-only requests.
- Aggregate-driven results are reproducible and auditable.
- Relationships omitted from the specification cannot be recovered and must be listed as assumptions or limitations.
- Proxy comparison is mechanical evidence, not proof about an unobserved population.
- Private roles retain DP staging, but that DP guarantee applies to proxy training rather than an unknown original
  population.

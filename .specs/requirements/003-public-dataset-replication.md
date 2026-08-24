# Requirement 003: Public-Dataset Replication Coverage

Status: Accepted

## Objective

Use the public business calibration research to verify that the synthetic-data skills can reproduce the schema,
marginals, formatting, dependencies, arithmetic invariants, and privacy boundaries needed by all requested dataset
families without embedding public-source row identifiers in the test suite.

## Requirements

1. The test matrix shall cover business population, employment/wages, industry validity, geography, business
   formation, federal contractors, public companies, historical small-business programs, transportation, healthcare,
   and public records.
2. Compact fixtures shall use schema and aggregate statistics rather than downloaded row-level registry, provider,
   carrier, loan, contract, or court records.
3. Formatted categorical/string codes shall support a regular-expression contract and zero-tolerance format gate.
4. Valid code/description and geography/status combinations shall support weighted joint distributions, an invalid
   combination gate, and a joint-distribution fidelity gate.
5. Numeric totals and identities shall support acyclic `sum`, `difference`, and `product` derivations with an explicit
   tolerance and a row-level violation gate.
6. Heavy-tailed nonnegative counts and amounts shall support lognormal marginals with mean, standard deviation, bounds,
   numeric-type validity, and integer-integrity gates.
7. Public roles shall remain explicit. Entity/provider/award/loan/company/filing identifiers shall remain identifiers
   unless an authorized policy explicitly assigns a different role.
8. Negative controls shall prove rejection of malformed codes, nonnumeric values, fractional integer counts,
   undeclared categories, invalid categorical combinations, and broken numeric totals.
9. Aggregate constraint passing shall remain separate from bound generation evidence, DP evidence, replay auditing,
   and downstream-use validation.
10. Native format/checksum semantics for surrogate identifiers, multi-table referential integrity, conditional numeric
    distributions, and nested records shall remain explicit limitations until separately designed and tested.

## Acceptance

- A version-controlled fixture catalog contains exactly the 11 requested public-data categories.
- Every fixture deterministically materializes at least 2,000 rows and passes every declared constraint.
- Negative controls fail the specific pattern, numeric-type, integer, declared-domain, joint-combination, and
  derived-total gates.
- Planner tests cover public-data identifier names and row-level sensitive financial fields.
- Skill package validation, the complete unit suite, linting, formatting, dependency licensing, and script lock checks
  pass without weakening any privacy role or privacy gate.

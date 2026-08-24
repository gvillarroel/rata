# Public-Data Replication Contracts

Use this contract when a synthetic table must reproduce the structure of official business, labor, registry,
geography, contracting, healthcare, transportation, or court datasets. Treat each flat source table as a separate
generation unit. Cross-table foreign keys, conditional numeric distributions, nested records, and native
format/checksum semantics for identifier surrogates are not supported by the current engine path.

## Required evidence

Declare and independently gate every relationship that matters downstream. Marginals alone are not sufficient for
these datasets.

| Data characteristic | Aggregate specification | Required evaluation |
| --- | --- | --- |
| Leading-zero FIPS, ZIP/ZCTA, NAICS/SIC, taxonomy, or status codes | Categorical/string `values` plus `pattern` | Zero undeclared values and pattern violations plus categorical-TV gate |
| Code/description, state/FIPS, county/state, taxonomy/description, or status/type pairs | `joint_distributions` | Zero invalid combinations plus joint-distribution TV |
| Establishment-size totals, bankruptcy totals, net changes, or amount × count identities | Numeric `derived` with `sum`, `difference`, or `product` | Zero derived-constraint violations unless an explicit nonzero tolerance is declared |
| Skewed counts, payroll, receipts, awards, loans, or carrier/provider frequencies | `lognormal` numeric distribution with nonnegative bounds | Numeric-type, mean, standard-deviation, bounds, and integer-integrity gates |
| Published suppression or absent-value rates | `missing_rate` | Missing-rate delta gate |
| Unique entity, provider, award, loan, filing, or company keys | `identifier` | Unique unrelated surrogates and zero source overlap in ordinary evaluation |
| Person/business names or address-shaped identifiers | `identifier` with `weighted_template` components | Unique surrogates, zero template violations, component-distribution TV, and zero source overlap |
| Privacy-minimized natural-language calibration | `string.generator=token_sequence` with high-frequency unigram and length weights | Token and length TV; ordinary text quality gates when a model stage is used |
| Sensitive row-level financial, health, contact, or person fields | `private`, `identifier`, or `drop` as appropriate | DP checkpoint/replay gates for private fields; identifiers and drops excluded from training |

Do not mark a field `public` merely because its source organization is public. Assign `public` only when the actual
released field is deliberately public for this task. Public aggregate counts may be explicit-public; row-level NPI,
UEI, DUNS, CIK, loan, award, case, legal-name, address, or contact fields still require deliberate role review.

## Aggregate specification example

```json
{
  "version": 1,
  "rows": 2000,
  "columns": [
    {
      "name": "state_fips",
      "type": "categorical",
      "role": "public",
      "values": ["01", "06"],
      "pattern": "^\\d{2}$"
    },
    {
      "name": "state_abbr",
      "type": "categorical",
      "role": "public",
      "values": ["AL", "CA"],
      "pattern": "^[A-Z]{2}$"
    },
    {
      "name": "small_establishments",
      "type": "integer",
      "role": "public",
      "distribution": {"kind": "lognormal", "mean": 70, "std": 55, "min": 0}
    },
    {
      "name": "large_establishments",
      "type": "integer",
      "role": "public",
      "distribution": {"kind": "lognormal", "mean": 8, "std": 7, "min": 0}
    },
    {
      "name": "establishments",
      "type": "integer",
      "role": "public",
      "derived": {
        "kind": "sum",
        "columns": ["small_establishments", "large_establishments"]
      }
    }
  ],
  "joint_distributions": [
    {
      "name": "state_codes",
      "columns": ["state_fips", "state_abbr"],
      "rows": [
        {"values": {"state_fips": "01", "state_abbr": "AL"}, "weight": 0.4},
        {"values": {"state_fips": "06", "state_abbr": "CA"}, "weight": 0.6}
      ]
    }
  ]
}
```

Joint-distribution columns cannot overlap within one specification and cannot have missing values. Put all dependent
categorical fields needed for a row into one joint group. Every joint value must also be declared by its column's
`values` contract.

Derived columns must be numeric, cannot also declare a marginal distribution, and cannot be missing. Their numeric
dependencies must also be nonmissing. Derived dependencies may reference other derived columns when the resulting
graph is acyclic. Use `tolerance` only for a documented source identity that is approximate; the default is exact.

`lognormal` uses the requested arithmetic mean and standard deviation on the released scale. Optional `min` and `max`
bounds clip materialized proxy values; choose bounds consistent with the moments or explicitly account for clipping in
the acceptance thresholds.

## Evaluation sequence

For aggregate-proxy mode, require all three artifacts before calling a candidate releasable:

1. Bound generation report and ordinary policy-aware evaluation against the proxy.
2. Aggregate constraint report from `scripts/evaluate_spec.py` against the final generated table.
3. A downstream-use check appropriate to the dataset, such as valid joins, grouped totals, or query results.

The constraint evaluator gates schema, missingness, numeric types/moments/bounds, integer integrity, declared category
domains and marginals, code patterns, joint combinations/distributions, derived arithmetic, identifiers, datetimes,
numeric correlations, weighted identifier-template components, and token-sequence vocabulary/length distributions.
The engine can still lose strict relationships after proxy materialization; a perfect proxy report does not waive the
final constraint evaluation.

## Realism without row reconstruction

- Build person names from independently aggregated given-name and surname frequencies. Never retain or learn name
  pairs, name/address pairs, or contact relationships.
- Build address-shaped values from independent road-name and suffix distributions plus a declared city/state/ZIP
  joint distribution. Do not ingest household address points or preserve road-name/suffix/geography pairings merely
  to improve realism.
- Derive free-text calibration from high-document-frequency unigrams and coarse length bands. Remove narratives,
  phrase order, identifiers, locations, and rare tokens after aggregation. Unigram fidelity is not semantic quality.
- Treat every output as synthetic metadata, because component recombination cannot guarantee that a generated name
  or address does not coincidentally exist in the real world.

## Covered public-data archetypes

The repository test matrix covers business population, employment/wages, industry references, geography, formation
registries, federal contractors, public companies, historical small-business programs, transportation carriers,
healthcare organizations, and bankruptcy public records. It uses compact schema/statistics fixtures rather than
shipping source rows or identifiers.

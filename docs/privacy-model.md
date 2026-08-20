# Privacy Model

The policy applies privacy at column level. It is deliberately asymmetric: some columns may be declared public while other columns in the same output require value protection, differential privacy, replacement, or removal.

## Roles

| Role | Source values allowed? | Training | Release condition |
| --- | --- | --- | --- |
| `public` | Yes | Joint source resampling | Explicit assignment; no privacy claim |
| `protected` | Not intentionally | Non-DP model with value protection | Rare replay and quality gates pass |
| `private` | Not intentionally | Separate DP model | DP checkpoint and strict replay gates pass |
| `identifier` | No | Never trained | Fresh surrogate and zero source overlap |
| `drop` | No | Never trained | Absent from output |

`public` is never inferred. Low cardinality does not make a column safe to publish.

`protected` is the conservative default for data without a stronger known requirement. Domain-sensitive financial, health, demographic, or similar fields belong in `private`. Identifier replacement favors unlinkability over formatting: UUID and sequential strategies emit strings and do not preserve the original appearance or physical dtype.

## Differential privacy

Private-stage training uses the SDK's DP-SGD configuration. The policy records the maximum epsilon, delta, noise multiplier, gradient norm, and value-protection epsilon. The generation report records the selected checkpoint's actual epsilon and delta. A private release fails without this evidence or when the budget exceeds its configured ceiling.

The DP claim applies to the private training stage under its recorded configuration. It does not make public source values private and does not replace domain-specific legal or re-identification review.

## Release gates

The evaluator checks schema completeness, unexpected fields, dropped fields, modeled-row replay, rare protected/private value replay, identifier overlap, DP evidence, marginal numeric and categorical fidelity, dedicated length and lexical fidelity for `TABULAR_CHARACTER` text, missingness drift, correlation drift, and a real-versus-synthetic propensity classifier. It gates both aggregate and worst-column quality and applies user-defined per-column thresholds. DCR, NNDR, and text nearest-neighbor similarity are included as diagnostics but are not treated as formal privacy guarantees.

The generation report is evidence only when its SHA-256 policy fingerprint, source hash, output hash, roles, and row count match the evaluated artifacts. This prevents a checkpoint from another run being used to justify a candidate.

A failed candidate should be remediated by correcting semantic encodings, increasing a quality profile, strengthening a role, or omitting a field whose privacy/utility tradeoff is unacceptable. Privacy gates must not be weakened automatically.

## Input provenance

- `source` is the only mode that directly compares generated rows to observed source rows.
- `synthetic-reference` can support extension or reshaping, but without the original policy and bound generation and
  evaluation reports it cannot establish original-source privacy or release fitness.
- `aggregate-proxy` contains rows sampled from declared aggregate constraints. The aggregate specification must already
  be safe to use. DP evidence describes training on proxy rows, not protection of an unknown original population.

Aggregate-driven candidates require a separate constraint report because ordinary row-to-row metrics only compare the
candidate with proxy materialization.

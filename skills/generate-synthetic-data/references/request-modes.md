# Synthetic Request Modes

Select the mode from the evidence the user supplies. Do not silently substitute one mode for another.

## Source rows

Use `$plan-synthetic-data` to inspect the source table, assign roles, and create the policy. `public` remains explicit.
Then dry-run, generate, and independently evaluate against the source and bound generation report.

## Existing synthetic reference

First determine whether the user wants to evaluate, extend, reshape, or regenerate it.

- If original rows, policy, generation report, and evaluation report exist, verify their binding before relying on them.
- If the original evidence is absent, the supplied table can be used as a `synthetic-reference`, but it is not evidence
  of original-source privacy or release fitness.
- Create the policy with `plan.py --input-kind synthetic-reference` and pass `--input-report` when a provenance report
  exists. Keep identifiers excluded and do not infer public columns.
- A second-generation model may compound bias and lose rare relationships. Evaluate utility against the reference and
  label the original-source release decision unresolved unless original evidence is available.

## Schema and aggregate statistics

`mostlyai-engine` trains on rows, not a schema alone. Materialize a reproducible proxy table from explicit aggregate
constraints, then train on that proxy. This is not reconstruction of original records.

The specification is JSON:

```json
{
  "version": 1,
  "rows": 1000,
  "quality": {"profile": "fast", "max_epochs": 2, "max_training_minutes": 1},
  "seed": 42,
  "columns": [
    {
      "name": "age",
      "type": "integer",
      "role": "protected",
      "distribution": {"kind": "normal", "mean": 42, "std": 12, "min": 18, "max": 90},
      "missing_rate": 0.02
    },
    {
      "name": "region",
      "type": "categorical",
      "role": "public",
      "values": {"north": 0.4, "south": 0.35, "west": 0.25}
    }
  ],
  "correlations": {
    "columns": ["age", "income"],
    "matrix": [[1.0, 0.55], [0.55, 1.0]]
  }
}
```

Supported types are `number`, `integer`, `categorical`, `boolean`, `string`, `datetime`, and `identifier`.
Numeric distributions support `normal`, `lognormal`, `uniform`, and `constant`. Categorical/string columns use
`values` as a list or weighted object and may declare a regex `pattern`. Datetimes require ISO-8601 `min` and `max`.
Correlations are optional, numeric-only, symmetric, and positive definite. Weighted `joint_distributions` preserve
declared categorical combinations. Numeric `derived` columns support acyclic `sum`, `difference`, and `product`
identities. A missing role defaults to `protected`; `public` must be explicit. Optional `quality` and `privacy.dp`
objects override the balanced training and DP defaults without changing role semantics.

For privacy-safe vocabulary and length calibration, a `string` may replace `values` with a `token_sequence`
generator:

```json
{
  "name": "summary",
  "type": "string",
  "role": "public",
  "generator": {
    "kind": "token_sequence",
    "tokens": {"account": 20, "payment": 12, "report": 7},
    "lengths": {"8": 4, "12": 5, "20": 1},
    "capitalize": true,
    "terminal": "."
  }
}
```

Only use token distributions derived after rare-token removal. This models unigram and length distributions, not
grammar or meaning. The final constraint evaluator gates token and length total variation.

Identifiers may declare a `weighted_template` surrogate whose stochastic components are aggregate distributions and
whose other fields reference released row context:

```json
{
  "name": "synthetic_address",
  "type": "identifier",
  "role": "identifier",
  "surrogate": {
    "strategy": "weighted_template",
    "template": "{number} {street} {suffix}, {city}, {state} {zip_code}",
    "components": {
      "number": {"kind": "integer", "min": 100, "max": 19999},
      "street": {"kind": "choice", "values": {"Main": 20, "Oak": 8}},
      "suffix": {"kind": "choice", "values": {"St": 6, "Ave": 4}}
    }
  }
}
```

Template components are sampled independently, identifiers remain unique and excluded from training, and references
to another identifier or dropped field are rejected. Gate template violations and component total variation. A
synthetic-looking value can still coincide with a real person, business, or deliverable address; label the dataset as
synthetic and never use it for contact, identity resolution, or eligibility decisions.

Resolve `scripts/materialize_spec.py` relative to this skill and invoke it by absolute path:

```powershell
uv run C:\absolute\path\to\generate-synthetic-data\scripts\materialize_spec.py spec.json proxy.csv policy.json `
  --materialization-report proxy.report.json `
  --output synthetic.csv --report generation.report.json --workspace model-workspace
```

Review the materialization report and policy, dry-run `generate.py`, then generate. Evaluate both:

1. Run `$evaluate-synthetic-data` against the proxy to verify bound generation, roles, DP evidence, replay, and model
   quality. Treat proxy comparison as mechanical evidence only.
2. Resolve `scripts/evaluate_spec.py` relative to this skill and run it against the final output to gate schema,
   marginals, missingness, identifier uniqueness, numeric types, bounds, integer integrity, declared category domains,
   patterns, joint distributions, derived constraints, and declared correlations.

Do not claim that DP applied to proxy rows protects an unknown source population. The aggregate specification itself
must already be safe to use, and omitted relationships cannot be recovered by the model.

Treat every declared correlation as a release gate. Proxy materialization can honor it while a trained model still
loses it, especially under short or DP-constrained training. Increase training effort in a new workspace and reevaluate;
if the gate still fails, preserve the reports and return a non-releasable candidate rather than relaxing the target.

## Insufficient request

Do not invent sensitive roles, public status, category weights, numeric distributions, date bounds, row count, or
correlations as if supplied facts. When generation cannot proceed, return a compact missing-input contract. If the user
explicitly authorizes assumptions, record each assumption in the specification and reports so downstream users can
distinguish it from supplied evidence.

# Engine Contract

## Dependency Boundary

The executable pins `mostlyai-engine==2.6.2`, which is Apache-2.0. Use the engine package directly. Do not replace it with `mostlyai[local]` under a strict no-copyleft dependency policy because the connector extra currently pulls an LGPL dependency.

The script also pins `fastavro`, which is MIT, for Avro input/output. PEP 723 metadata lets `uv run` create an isolated environment without modifying the user's project environment.

`TabularARGN.fit` requires row-shaped training data. For schema-and-statistics requests, `materialize_spec.py` creates
reproducible proxy rows from declared aggregate constraints before this engine runs. The proxy does not reconstruct
unobserved source records, and DP applied to proxy training does not create a privacy guarantee for an unknown source.

## Staged Generation

1. Jointly resample `public` columns from source rows. Exact values and combinations are allowed.
2. Train a non-DP value-protected TabularARGN on `public + protected`; generate protected columns conditioned on public output.
3. Train a separate DP TabularARGN on `public + protected + private`; generate private columns conditioned on the already generated public/protected output.
4. Create unrelated unique surrogates for `identifier` columns.
5. Exclude `drop` columns from training and output.

This design avoids applying DP noise to deliberately public output while preserving conditional relationships with private columns. DP still protects all rows used by the private-stage model.

## DP Evidence

The report records:

- configured maximum epsilon and delta;
- noise multiplier and gradient norm;
- the actual checkpoint epsilon/delta read from the engine progress artifact;
- the exact engine version.
- SHA-256 evidence binding the generation policy, source file, and emitted table.

The run fails if private columns exist but DP is disabled or no DP checkpoint evidence exists. `max_epsilon` is a ceiling, not a promise that the run spent the full budget.

## Formats

Supported extensions are `.csv`, `.json`, `.jsonl`, `.ndjson`, `.parquet`, `.pq`, and `.avro`. All containers support flat scalar tabular columns only; nested objects or arrays must be flattened or dropped during planning.

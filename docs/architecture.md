# Architecture

Rata is a repository of self-contained Codex skills, not an application library. Each specialized skill owns one auditable phase and includes its instructions, script, references, and agent metadata.

```text
source table
    |
    v
plan-synthetic-data ----> policy.json
    |
    v
generate-synthetic-data ----> synthetic table + generation report
    |
    v
evaluate-synthetic-data ----> evaluation report + release decision
```

`run-synthetic-data-workflow` orchestrates those phases and preserves their artifacts.

Generation accepts three provenance modes before entering this pipeline:

1. `source`: observed rows planned and evaluated under the ordinary policy.
2. `synthetic-reference`: an already synthetic table whose original-source claims depend on its bound provenance.
3. `aggregate-proxy`: deterministic proxy rows materialized from schema and statistics, followed by both ordinary
   generation evaluation and aggregate-constraint evaluation.

The last two modes never masquerade as observed source rows in policies or reports.

## Staged generation

The generator produces columns in privacy order:

1. Jointly resample explicitly public columns from source rows.
2. Train a value-protected, non-DP TabularARGN on public and protected columns; sample protected columns conditioned on the public output.
3. Train a separate DP TabularARGN on public, protected, and private columns; sample private columns conditioned on the already generated values.
4. Create unrelated deterministic UUID or sequential surrogates for identifiers.
5. Omit dropped columns.

This separation prevents private columns from being emitted by a non-DP stage. Generation fails if a private stage lacks a recorded DP checkpoint or exceeds the policy epsilon ceiling. The report cryptographically binds the generation policy, source, and output; evaluation verifies that binding before accepting DP evidence.

## Dependency boundary

The skills call `mostlyai-engine` directly. They do not install the full MOSTLY AI local/connectors extra, which would broaden the runtime and its licensing surface. Exact direct versions are declared in each PEP 723 script, adjacent `.py.lock` files pin standalone transitive environments, and the root `uv.lock` pins repository development.

## File formats

CSV, JSON, JSONL/NDJSON, Parquet, and Avro use one internal pandas table representation. Outputs retain the selected container format; the policy records semantic encodings such as `TABULAR_DATETIME` when physical source types are ambiguous. Nested objects, arrays, tuples, and sets are outside the tabular contract and must be flattened or assigned `drop` before generation.

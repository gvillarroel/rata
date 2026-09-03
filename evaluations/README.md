# Evaluation Matrix

The canonical matrix is [`catalog.json`](catalog.json). Scenarios are ordered by increasing modality:

1. `tabular` exercises identifiers, public categories, protected categories, and protected numeric values.
2. `tabular-text` adds protected free text with an explicit `TABULAR_CHARACTER` encoding.

Run the matrix in a fresh evidence directory:

```powershell
uv run tools/run_evaluation_matrix.py C:\absolute\path\to\evidence
```

Each scenario executes the real planner, generator, and evaluator. It also evaluates the source table as a deliberately leaky negative control. The runner succeeds only when the release candidate passes and the negative control is rejected. Existing evidence is never replaced unless `--overwrite` is explicit.

The catalog relaxes only dataset-specific quality thresholds for this small mechanical benchmark. Identifier overlap, exact replay, protected rare-value replay, schema, generation binding, and any applicable DP requirements retain the product defaults.

Generated model workspaces can be large and are not repository fixtures. Keep them in an external evidence directory and commit only reviewed summaries when a durable validation record is needed.

## Dataset authoring for future Harbor studies

Use
[`harbor-author-evaluation-datasets`](../skills/harbor-author-evaluation-datasets/SKILL.md)
before registering any new native task cohort. Assign whole semantic families
to one split, let only development drive candidate changes, and keep validation
sealed until one candidate is frozen. Holdout is an optional later final gate.

Keep private blueprints, seeds, rendered tasks, solutions, verifiers, jobs,
traces, candidates, and diagnostics outside Git. A future
`evaluations/datasets/<dataset-id>/` may contain only reviewed public schemas,
adapter source, provenance, and redacted manifests; study-specific publication
indexes remain under `evaluations/harbor-studies/<study-id>/publication/`.
The existing v1 path is historical evidence and must not move.

After a cohort's release boundary permits aggregate publication, the same
bundle can consolidate finalized `harbor-run-results` reports into JSON,
Markdown, and three self-contained SVGs covering correctness, errors, tokens,
reported USD cost, agent time, wall time, throughput, and the quality/cost
frontier. Keep task-level rows and raw paths private, retain source hashes and
fairness warnings, and treat cross-hardware or cross-lock views as descriptive
unless the execution profiles are actually comparable.

## Harbor skill-request benchmark

The private Harbor 0.18.0 dataset exercises the `generate-synthetic-data` skill across original source rows, existing
synthetic references, complete schema/statistics requests, and missing-evidence cases. Its three development, two
validation, and two holdout tasks remain denied by `.gitignore`; only the organizer's source-path-free
[publication index](harbor-studies/generate-synthetic-data-v1/publication/index.md) is versionable.

The current study records a successful task/config dry-run and a blocked live-evolution doctor check. Holdout remains
sealed until GEPA selects a candidate and the append-only release gate is satisfied.

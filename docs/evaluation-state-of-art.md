# Evaluation State of the Art

## Executive finding

Rata now has an executable evaluation matrix ordered from tabular data to tabular data plus text. A real 120-row run on 2026-07-26 proved that the tabular workflow can produce a release candidate that passes its configured gates and that the same gates reject a deliberately leaked source copy. The mixed text workflow executed end to end, but its two-epoch smoke candidate was correctly rejected for protected-value replay and poor text fidelity.

The durable machine-readable record is [`evaluations/results/2026-07-26.json`](../evaluations/results/2026-07-26.json). SHA-256 digests bind every source, policy, candidate, generation report, evaluation report, and negative-control report from the evidence run.

## What is evaluated

The canonical [`evaluations/catalog.json`](../evaluations/catalog.json) requires these scenarios in this order:

1. `tabular`: identifier, public categorical, protected categorical, and protected numeric columns.
2. `tabular-text`: the same workflow shape plus protected free text explicitly encoded as `TABULAR_CHARACTER`.

Each scenario runs the real planner, generator, and evaluator. It then evaluates the source table itself as a deliberately leaky negative control. The small benchmark uses dataset-specific quality thresholds, but does not relax exact replay, identifier overlap, rare-value replay, schema, report binding, or DP evidence requirements.

## Real results

| Scenario | Candidate | Numeric KS | Categorical TV | Text length KS | Text TF-IDF distance | AUC | Protected rare replay |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `tabular` | Pass | 0.0667 | 0.0639 | n/a | n/a | 0.5239 | 0.0194 |
| `tabular-text` | Reject | 0.0750 | 0.0833 | 1.0000 | 0.8616 | 0.5305 | 0.0806 |

Both candidates had zero exact modeled-row replay and zero identifier overlap. The tabular candidate passed every gate. The mixed candidate failed:

- `protected_rare_value_replay`: 0.0806 against the unchanged 0.05 ceiling, driven by the protected numeric field.
- `mean_text_length_ks` and `max_column_text_length_ks`: 1.0.
- `mean_text_tfidf_distance` and `max_column_text_tfidf_distance`: 0.8616.

Both negative controls were rejected for generation-report binding, exact modeled-row replay, identifier overlap, and protected rare-value replay. This matters because identical source and candidate distributions look perfect under utility metrics; release gates must independently catch the leak.

## Text evaluation design

Columns encoded as `TABULAR_CHARACTER` no longer use exact-category total variation. That metric labels every novel sentence as total drift even when its language is similar. Rata now reports and gates:

- KS distance over text length distributions.
- Character 3-5 gram TF-IDF centroid distance.
- Exact text-value replay.
- Median and maximum nearest-source TF-IDF similarity as diagnostics.

Tabular metrics continue to run over the remaining modeled columns, while missing-rate drift still includes text columns. Exact row replay and protected/private rare-value replay continue to include text.

## Interpretation

The tabular evidence is a successful mechanical benchmark, not a universal utility claim. The mixed result is an honest capability boundary: the fast two-epoch `TabularARGN` run generated text that is lexically far from the fixture and replayed too many protected numeric values. The evaluator now exposes that failure instead of hiding it inside categorical TV or skipping a non-numeric dataset.

TF-IDF is lexical rather than semantic. It cannot establish factuality, coherence, safety, or downstream task utility. DCR, NNDR, text nearest-neighbor similarity, and low replay are diagnostics rather than formal privacy guarantees. Only a generation report bound to the exact artifacts and containing an in-budget DP checkpoint supports a differential-privacy claim for private columns.

## Next evidence stages

1. Re-run `tabular-text` with the balanced profile and more representative text before changing any threshold.
2. Add downstream language-task utility and human coherence review for text release candidates.
3. Calibrate lexical thresholds on held-out corpora rather than the small deterministic smoke fixture.
4. Add a private text scenario only after confirming that the engine emits a bound, in-budget DP checkpoint for that stage.

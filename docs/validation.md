# Validation Record

## Automated checks

Run the locked suite with:

```powershell
uv sync --python 3.12 --locked
uv run ruff check skills tests tools
uv run ruff format --check skills tests tools
uv run pytest
uv run python tools/audit_licenses.py
uv lock --check --script skills/plan-synthetic-data/scripts/plan.py
uv lock --check --script skills/generate-synthetic-data/scripts/generate.py
uv lock --check --script skills/generate-synthetic-data/scripts/materialize_spec.py
uv lock --check --script skills/generate-synthetic-data/scripts/evaluate_spec.py
uv lock --check --script skills/evaluate-synthetic-data/scripts/evaluate.py
```

The tests cover policy inference and user overrides, invalid policy rejection, all five table containers, identifier generation, DP checkpoint selection, datetime semantics, quality/privacy metrics, failed-schema report preservation, per-column gates, report binding and tamper detection, skill metadata/links, documentation links, installation, and licensing rules.

They also cover aggregate proxy materialization, conservative role defaults, weighted categories, correlated numeric
statistics, constraint evaluation, `synthetic-reference` provenance, and bound aggregate-spec hashes.

## Harbor skill benchmark

On 2026-08-20, Harbor 0.18.0 and GEPA 0.1.2 validated a seven-task evolution plan: three development requests, two
validation requests, and two byte-locked holdouts. Native `--print-config` validation passed for every task, and the
evolution dry-run verified exact skill/task digests and split disjointness.

The live evolution doctor stopped before model calls because Docker is not installed. The append-only study preserves
that infrastructure failure, keeps holdout sealed, and records no candidate or promotion claim. See the
[safe publication index](../evaluations/harbor-studies/generate-synthetic-data-v1/publication/index.md).

## Aggregate-only end-to-end evidence

On 2026-08-20, an 800-row aggregate specification with protected age, private income, explicit-public region, an
identifier, and a requested age-income correlation of 0.60 completed proxy materialization, real protected/private
`mostlyai-engine` training, sampling, generation binding, ordinary evaluation, and constraint evaluation.

The two-epoch candidate recorded DP checkpoint ε 1.59 / δ 1e-5 but was rejected for numeric KS and correlation. A new
ten-epoch workspace recorded ε 1.96 / δ 1e-5 and removed the KS failure, but correlation remained only 0.077, so both
the ordinary correlation gates and the aggregate constraint gate still rejected it. Both failed generations and reports
are preserved under ignored local evidence. No privacy or quality threshold was weakened.

## Mixed-type end-to-end run

On 2026-07-19, the complete workflow ran against a local 1,000-row, 13-column Parquet fixture with all five roles:

- `public`: `gender`, `country`
- `protected`: `registration_dttm`
- `private`: `salary`
- `identifier`: `id`, `first_name`, `last_name`, `email`, `ip_address`, `cc`
- `drop`: `birthdate`, `title`, `comments`

The fast profile used 10 epochs, a two-minute stage ceiling, maximum epsilon 8, delta 1e-5, and explicit per-column KS limits of 0.25 for salary and 0.15 for registration time. The generated 1,000-row candidate passed all configured gates:

| Evidence | Result |
| --- | ---: |
| Generation report binding checks | All passed |
| DP checkpoint | epsilon 2.01; delta 1e-5 |
| Mean / worst numeric KS | 0.116 / 0.190 |
| Mean / worst categorical TV | 0.056 / 0.103 |
| Worst missing-rate delta | 0.065 |
| Worst correlation delta | 0.009 |
| Propensity AUC | 0.501 |
| Exact modeled-row replay | 0 |
| Private rare-value replay | 0 |
| Protected rare-value replay | 0.029 |
| Maximum identifier overlap | 0 |

A negative control evaluated the same candidate with a generation report from another run. It exited with code 2 and failed both `generation_report_binding` and `dp_checkpoint_evidence` due mismatched policy, source, and output hashes.

These results establish that the workflow and gates operate end to end on the fixture. They do not generalize the measured utility or privacy diagnostics to a different dataset; every candidate requires its own policy and evaluation report.

## Ordered tabular and text matrix

On 2026-07-26, `tools/run_evaluation_matrix.py` ran the real planner, generator, evaluator, and a leaky negative
control for the ordered `tabular` and `tabular-text` scenarios. The tabular candidate passed all gates. The two-epoch
mixed-text smoke candidate was rejected for protected rare-value replay, text-length KS, and text TF-IDF distance.
Both source-as-candidate controls were rejected for binding, exact replay, identifier overlap, and protected
rare-value replay.

See the [state-of-the-art report](evaluation-state-of-art.md) and
[machine-readable evidence](../evaluations/results/2026-07-26.json) for measured values, hashes, limitations, and next
stages. The failed mixed candidate is retained as evidence; no privacy threshold was weakened.

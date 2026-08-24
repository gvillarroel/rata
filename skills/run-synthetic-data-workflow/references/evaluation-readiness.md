# Evaluation Readiness

Read this before an expensive quality run or when the user asks whether the environment can evaluate the skills.

Keep three decisions separate:

1. **Calibration-data quality**: integrity, schema, value validity, aggregate consistency, privacy minimization, and
   representativeness limitations.
2. **Compute readiness**: enough CPU, memory, disk, runtime dependencies, and an executed representative workload.
3. **Candidate quality/privacy**: the actual generation and evaluation gates for a particular dataset.

A machine can be ready while a candidate correctly fails. Never relax a replay, DP, binding, schema, or utility gate
to turn compute evidence into a quality pass.

## Repository baseline

For the checked-in 120-row, two-epoch smoke matrix, use 8 logical CPUs, 16 GiB physical memory, and 20 GiB free
workspace storage as the minimum local baseline. Python 3.12 and the locked engine/evaluator packages must be present.
This is a smoke/low-volume baseline; increase memory, storage, training time, and isolation for larger tables, text,
multiple repetitions, or concurrent trials.

The current tabular path runs on CPU. Report an NVIDIA GPU when present, but do not require one. Harbor jobs additionally
require a working Docker server; checked-in configs or an installed CLI are not sufficient when Docker is unavailable.

In the Rata repository, run:

```powershell
uv run python tools/audit_public_data_quality.py
uv run python tools/run_evaluation_matrix.py datasets/public-data/evaluation-readiness/matrix --overwrite
uv run python tools/audit_evaluation_readiness.py
```

Use `audit_public_data_quality.py --sample` only for a quick diagnostic. Final evidence requires the full scan. Preserve
the generated matrix directory because it contains failed evaluation reports and negative-control evidence.

## Release interpretation

- Local readiness passes only after the real planner, generator, evaluator, and leaky negative controls execute.
- Harbor readiness is a separate result and fails closed when Docker is absent or unreachable.
- Dataset warnings remain attached to any calibration claim.
- A failed text or tabular scenario is an observed skill-quality boundary, not a hardware failure.

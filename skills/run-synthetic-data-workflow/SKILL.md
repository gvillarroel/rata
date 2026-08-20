---
name: run-synthetic-data-workflow
description: Orchestrate planning, policy review, staged generation, and independent evaluation for synthetic tabular data with column-level privacy. Use when Codex needs an end-to-end workflow across plan-synthetic-data, generate-synthetic-data, and evaluate-synthetic-data, including iterative quality/privacy gate remediation.
---

# Run Synthetic Data Workflow

Coordinate the three specialized sibling skills. Resolve each bundled script relative to its sibling `SKILL.md` and invoke it by absolute path; do not assume the source repository is the working directory. Do not skip policy review or independent evaluation.

## Workflow

1. Use `$plan-synthetic-data` to inspect the source and create a policy.
2. Present inferred roles and explicitly confirm task-provided public columns. Never infer public status from low cardinality alone.
3. Run `$generate-synthetic-data` with `--dry-run` and inspect the role/stage summary.
4. Generate the candidate dataset and generation report.
5. Run `$evaluate-synthetic-data` with the original, candidate, policy, and generation report.
6. If gates fail, use [remediation.md](references/remediation.md), regenerate into a new workspace, and reevaluate.
7. Return the candidate only with its policy, generation report, evaluation report, failed/passed gate summary, engine version, and DP checkpoint evidence when private columns exist.

If the request starts from an existing synthetic reference or from schema and aggregate statistics, let
`$generate-synthetic-data` select and preserve that input mode first. Aggregate-proxy candidates also require the
constraint evaluation report; synthetic-reference candidates retain unresolved original-source claims unless bound
original evidence is available.

## Required Guarantees

- Use only the pinned permissive dependency boundary in the sibling scripts.
- Treat `public` as a deliberate no-privacy choice.
- Require a recorded epsilon/delta for every private-stage release candidate.
- Never describe a passing proxy metric as a formal privacy guarantee.
- Preserve failed reports; they are evidence, not disposable noise.

For a first run, prefer the `fast` profile to validate mechanics, then use `balanced` or `high` for release candidates.

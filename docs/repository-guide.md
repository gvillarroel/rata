# Rata Synthetic Data Skills: repository guide

Four self-contained skills for planning, generating, and evaluating tabular synthetic data with explicit column-level privacy policy. The workflow uses the mostlyai-engine SDK and keeps generation separate from release evaluation.

## Layout

| Path | Responsibility |
| --- | --- |
| `skills/` | Planning, generation, evaluation, and end-to-end workflow bundles. |
| `tools/` | Installation, public-data acquisition, and audit utilities. |
| `tests/` | Privacy, provenance, and generation contract tests. |
| `docs/` | User commands, privacy model, architecture, and validation. |
| `.specs/` | Requirements, ADRs, issues, and spikes. |
| `evaluations/` | Protocols and explicitly reviewed publication evidence. |

## Documentation policy

- Keep the root `README.md` focused on purpose, critical constraints, and the first useful action. Put detailed procedures in `docs/`.
- Maintain `docs/README.md` as the navigation index whenever a guide is added or moved.
- Preserve existing specification, ADR, skill-contract, and evidence locations. Link to their owners instead of copying authoritative content.
- Keep implementation, configuration, source data, and generated output separate. Do not create empty folder hierarchies without a concrete need.
- Use portable relative links. Update both outgoing links and inbound references when moving a document.
- Document prerequisites, commands, expected outcomes, and limitations. Never describe an unrun check as verified.

## Change workflow

1. Read `AGENTS.md`, this index, and the relevant source contract.
2. Inspect `git status` and preserve pre-existing changes and staged files.
3. Make a focused change and update affected documentation in the same change.
4. Run the applicable checks below, inspect the diff, and record any unavailable prerequisite.
5. Stage explicit paths. Publish only when authorized; do not force-push or merge unrelated work.

## Validation

```sh
uv run ruff check skills tests tools
uv run ruff format --check skills tests tools
uv run pytest
uv run python tools/audit_licenses.py
```

Also check the changed standalone script lockfiles and use the installation dry run. Consult the command reference for complete generation/evaluation gates.

## Data and operating boundaries

Keep row-level source data, generated datasets, model workspaces, and private study artifacts out of Git. Retain generation-report binding and all role semantics. Published aggregate evidence must remain separate from native traces and sealed validation data.

[Back to the documentation index](README.md).

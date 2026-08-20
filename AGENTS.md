## Table Of Contents

- [User Preferences](#user-preferences)
- [Project Documentation Map](#project-documentation-map)
- [Development Commands](#development-commands)
- [Specification Locations](#specification-locations)

## User Preferences

- If another validation, coverage test, manual verification, or research step can improve the result, do it without asking for confirmation.
- Write always in English.
- Preserve failed generation and evaluation reports as evidence.
- Never weaken a privacy role or gate merely to obtain a passing candidate.
- Use `.specs/adr/*.md` for ADRs, `.specs/issues/*.md` for issues, `.specs/requirements/*.md` for requirements, `.specs/spikes/$SPIKE_FOLDER` for spikes, and `docs/` for official user documentation.

## Project Documentation Map

- [Root README](README.md): onboarding, skill catalog, and validation.
- [Docs Index](docs/README.md): documentation entry point.
- [Architecture](docs/architecture.md): staged generation and package layout.
- [Command Reference](docs/commands.md): script options and examples.
- [Privacy Model](docs/privacy-model.md): role semantics, DP claims, and release gates.
- [Licensing](docs/licensing.md): permissive SDK boundary and dependency review.
- [Validation Record](docs/validation.md): automated and mixed-type end-to-end evidence.

## Development Commands

```powershell
uv sync --python 3.12 --locked
uv run ruff check skills tests tools
uv run ruff format --check skills tests tools
uv run pytest
uv run python tools/audit_licenses.py
uv lock --check --script skills/plan-synthetic-data/scripts/plan.py
uv lock --check --script skills/generate-synthetic-data/scripts/generate.py
uv lock --check --script skills/evaluate-synthetic-data/scripts/evaluate.py
python tools/install_skills.py --destination .local-skill-test --dry-run
```

## Specification Locations

- `.specs/requirements/*.md`: product and engineering requirements.
- `.specs/adr/*.md`: architecture decision records.
- `.specs/issues/*.md`: actionable issues and review follow-ups.
- `.specs/spikes/$SPIKE_FOLDER`: research notes and exploratory work.

## Update Access Scope

- Writable project root: `C:\Users\villa\dev\rata`.
- Agents may create, modify, move, or delete files only inside this root and its descendants when the task requires it.
- Treat paths outside this root as read-only unless the user explicitly authorizes a broader scope.
- A reference to another repository or shared tool does not grant write access to it.

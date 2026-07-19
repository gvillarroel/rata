## Table Of Contents

- [User Preferences](#user-preferences)
- [Project Documentation Map](#project-documentation-map)
- [Specification Locations](#specification-locations)

## User Preferences

- If there is another step to improve progress, another stage, a validation that can be done, coverage test, unit testing, manual verification using Playwright, or research to better understand the best way to proceed, do not ask for confirmation. Do the best effort to make the work as polished as possible.
- Write always in English.
- Use `.specs/adr/*.md` for ADRs.
- Use `.specs/issues/*.md` for issues.
- Use `.specs/requirements/*.md` for requirements.
- Use `.specs/spikes/$SPIKE_FOLDER` for spikes.
- Use `docs/` for official documentation for users.

## Project Documentation Map

- [Root README](README.md): source-based onboarding and validation commands.
- [Docs Index](docs/README.md): entry point for user documentation.
- [Architecture](docs/architecture.md): repository structure, project order, and runtime flow.
- [Command Reference](docs/commands.md): CLI commands and options.
- [Privacy Review](docs/privacy-review.md): privacy findings from current synthetic-data methods and test fixtures.
- [Repository Review](docs/repository-review.md): current review findings and roadmap.

## Specification Locations

- `.specs/requirements/*.md`: product and engineering requirements.
- `.specs/adr/*.md`: architecture decision records.
- `.specs/issues/*.md`: actionable issues and review follow-ups.
- `.specs/spikes/$SPIKE_FOLDER`: research notes and exploratory work.

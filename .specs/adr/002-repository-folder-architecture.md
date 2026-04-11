# ADR 002: Repository Folder Architecture

## Status

Accepted

## Context

The project will implement a Rust core with Python and TypeScript bindings.

The repository needs a folder structure that keeps the Rust core isolated, makes bindings explicit, separates test assets from implementation code, and leaves space for user-facing documentation and project specifications.

## Decision

The repository will use the following top-level folder architecture:

- `crates/`
  - Rust crates owned by the repository.
- `bindings/`
  - Language bindings built on top of the Rust core.
- `tests/`
  - Cross-language and end-to-end test assets and suites.
- `datasets/`
  - Downloaded local datasets for manual and automated testing. Ignored by git except for keep files.
- `scripts/`
  - Development and automation scripts such as dataset download helpers.
- `docs/`
  - Official documentation for users.
- `.specs/requirements/`
  - Product and engineering requirements.
- `.specs/adr/`
  - Architecture Decision Records.
- `.specs/issues/`
  - Project issues tracked as specification artifacts.

The initial concrete structure will be:

- `crates/rata-core/`
  - Rust implementation of dataset loading and statistics extraction.
- `bindings/python/`
  - Python package and Rust binding integration.
- `bindings/typescript/`
  - TypeScript package and Rust binding integration.
- `tests/integration/`
  - End-to-end tests across formats and public APIs.
- `tests/fixtures/`
  - Small tracked test fixtures that are safe to commit.

## Rationale

- `crates/` keeps the Rust core scalable if additional Rust crates are introduced later.
- `bindings/` makes Python and TypeScript integration first-class instead of mixing them into the Rust workspace.
- `tests/fixtures/` and `datasets/` separate committed fixtures from large downloaded samples.
- `docs/` stays reserved for official user-facing documentation, aligned with repository policy.
- `.specs/` keeps architectural and product decisions separate from executable code.

## Consequences

- The Rust workspace should be rooted under `crates/`.
- Binding packaging and release workflows should target `bindings/python/` and `bindings/typescript/`.
- Downloaded test data must continue to stay out of version control.
- Small deterministic fixtures should be committed under `tests/fixtures/` instead of `datasets/`.

## Alternatives Considered

- Flat top-level layout with `rust/`, `python/`, and `typescript/`.
- Monorepo packages without a dedicated `crates/` folder.
- Storing all test datasets in version control.

These alternatives were rejected because they scale less cleanly or mix tracked source with large generated artifacts.

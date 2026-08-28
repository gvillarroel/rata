# Documentation

## Start here

- [Usage and setup](getting-started.md)
- [Repository layout, maintenance, and validation](repository-guide.md)
- [Agent instructions](../AGENTS.md)
- [Command reference](commands.md)
- [Privacy model](privacy-model.md)
- [Architecture](architecture.md)
- [Validation evidence](validation.md)
- [Public dataset catalog](public-data-sources.md)


## Downloads and datasets

- [Public-data download catalog](public-data-sources.md): all official source and landing-page links, local artifact
  handling, privacy minimization, source keys, and validation evidence.
- [Public-data examples](public-data-examples.md): verified examples for the original 11 categories, the added
  privacy-safe realism category, and all local source-manifest artifacts.
- [Command reference](commands.md#download-public-calibration-data-and-examples): full-bundle, realism-only,
  individual-source, example-generation, and audit commands.

## User and developer guides

- [Architecture](architecture.md): skill boundaries and staged data flow.
- [Commands](commands.md): planner, generator, and evaluator reference.
- [Privacy model](privacy-model.md): column roles, DP evidence, metrics, and limitations.
- [Licensing](licensing.md): selected SDK and dependency license policy.
- [Validation record](validation.md): automated coverage and mixed-type end-to-end evidence.
- [Evaluation state of the art](evaluation-state-of-art.md): ordered tabular and tabular-plus-text real-run evidence.
- [Harbor study publication index](../evaluations/harbor-studies/generate-synthetic-data-v1/publication/index.md):
  source-path-free benchmark status and evidence digests.

## Specifications and decisions

- [Requirement 001](../.specs/requirements/001-column-level-private-synthetic-data.md): normative behavior.
- [Requirement 002](../.specs/requirements/002-multi-input-synthetic-data-generation.md): multi-input provenance and
  aggregate-statistics behavior.
- [Requirement 003](../.specs/requirements/003-public-dataset-replication.md): public-dataset replication contracts
  and test coverage.
- [Requirement 004](../.specs/requirements/004-data-quality-and-evaluation-readiness.md): calibration-data quality and
  hardware/runtime readiness gates.
- [Requirement 005](../.specs/requirements/005-realism-calibration.md): privacy-safe name, address-component, and
  language-distribution calibration.
- [ADR 001](../.specs/adr/001-skill-based-staged-synthesis.md): architecture decision.
- [ADR 002](../.specs/adr/002-aggregate-proxy-input-mode.md): aggregate-proxy and synthetic-reference decision.

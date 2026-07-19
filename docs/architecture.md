# Architecture

This document describes the repository structure, ownership order, and intended workflow for Rata.

## Repository Structure

```mermaid
flowchart TD
    repo["Repository root"]

    repo --> specs[".specs/"]
    specs --> req["requirements/ product and engineering requirements"]
    specs --> adr["adr/ accepted architecture decisions"]
    specs --> issues["issues/ tracked engineering follow-ups"]
    specs --> spikes["spikes/ research and experiments"]

    repo --> crates["crates/"]
    crates --> core["rata-core/ Rust source of truth"]
    core --> cli["src/bin/rata.rs CLI entrypoint"]
    core --> lib["src/lib.rs dataset APIs, stats, schemas, transforms, synthetic helpers"]
    core --> diffusion["src/diffusion/ diffusion model modules"]

    repo --> bindings["bindings/"]
    bindings --> python["python/ future Python binding package"]
    bindings --> typescript["typescript/ future TypeScript binding package"]

    repo --> tests["tests/"]
    tests --> fixtures["fixtures/ small tracked fixtures"]
    tests --> integration["integration/ cross-format and CLI tests"]

    repo --> datasets["datasets/ ignored local datasets"]
    repo --> models["models/ local or tracked model artifacts"]
    repo --> scripts["scripts/ development automation"]
    repo --> docs["docs/ official user documentation"]
    docs --> reports["reports/ generated sample reports"]
```

## Project Order

The project should move from intent to implementation to validation in this order:

```mermaid
flowchart LR
    requirements["1. Requirements"]
    decisions["2. ADRs"]
    spikes["3. Spikes when uncertainty is high"]
    implementation["4. Rust core implementation"]
    cli["5. CLI surface"]
    tests["6. Unit and integration tests"]
    scripts["7. Automation scripts"]
    docs["8. User documentation"]
    reports["9. Generated reports and evaluation outputs"]
    bindings["10. Language bindings"]

    requirements --> decisions
    decisions --> spikes
    spikes --> implementation
    decisions --> implementation
    implementation --> cli
    implementation --> tests
    cli --> tests
    cli --> scripts
    tests --> docs
    scripts --> reports
    implementation --> bindings
    docs --> bindings
```

## Runtime Flow

```mermaid
flowchart TD
    user["User or automation"]
    command["rata CLI command"]
    detect["Detect dataset format"]
    load["Load records"]
    operation{"Selected operation"}
    stats["Compute statistics"]
    schema["Infer schema"]
    transform["Transform output format"]
    synthetic["Generate synthetic data"]
    render["Render Markdown or JSON report"]
    write["Write output dataset, model, or report"]

    user --> command
    command --> detect
    detect --> load
    load --> operation
    operation --> stats
    operation --> schema
    operation --> transform
    operation --> synthetic
    stats --> render
    schema --> render
    transform --> write
    synthetic --> write
    render --> user
    write --> user
```

## Ownership Rules

- `.specs/requirements/` defines what the project must do.
- `.specs/adr/` defines durable architectural decisions.
- `.specs/issues/` tracks review findings and planned improvements.
- `crates/rata-core/` is the canonical implementation boundary.
- `docs/` is the official user-facing documentation surface.
- `datasets/` is for ignored local data; small deterministic test assets belong in `tests/fixtures/`.
- `bindings/` should stay thin and reuse the Rust core rather than duplicating behavior.

## Current Architectural Notes

- The Rust core is currently the only implemented runtime surface.
- Python and TypeScript bindings are planned by ADR but not implemented yet.
- The current stats path is eager and full-dataset oriented; future large-dataset work should introduce bounded preview readers and streaming or sampled statistics.
- The diffusion module already uses a clearer module split than the rest of the core and is a useful direction for future refactors.

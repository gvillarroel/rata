# ADR 001: Rust Core with Python and TypeScript Bindings

## Status

Accepted

## Context

The first project capability is extracting statistics from datasets in Parquet, Avro, CSV, JSONL, and JSON formats.

The implementation must support reuse across multiple language environments while keeping performance and consistency in the core execution path.

## Decision

The core implementation will be written in Rust.

The project will expose bindings for:

- Python
- TypeScript

## Rationale

- Rust provides strong performance characteristics for dataset processing.
- Rust enables a single core implementation for parsing and statistics extraction logic.
- Python bindings allow integration with data and analytics workflows.
- TypeScript bindings allow integration with JavaScript and Node.js ecosystems.
- A shared Rust core reduces behavioral drift between language interfaces.

## Consequences

- The project must define and maintain an FFI or binding strategy for Python and TypeScript.
- Build, packaging, and release workflows will need to support Rust artifacts and language-specific distribution.
- The Rust core becomes the source of truth for dataset statistics behavior.

## Alternatives Considered

- Implement the core separately in Python and TypeScript.
- Implement the core in a different systems language.

These alternatives were rejected because they increase duplication or reduce alignment with the performance and reuse goals.

# Rata

Rata is a Rust CLI and core library for inspecting datasets, inferring schemas, converting formats, and generating synthetic tabular data.

Supported dataset formats:

- CSV
- JSON
- JSONL / NDJSON
- Parquet
- Avro

## Quick Start From Source

```powershell
cargo test --workspace
cargo run -p rata-core --bin rata -- head datasets\iris.csv
cargo run -p rata-core --bin rata -- stats datasets\iris.csv
cargo run -p rata-core --bin rata -- schema datasets\iris.csv --format json-schema
```

Most user docs show commands with the shorter `rata` binary name. From a fresh checkout, use `cargo run -p rata-core --bin rata -- ...` until you install or otherwise expose the binary on your `PATH`.

## Docs

- [Docs Index](docs/README.md)
- [Getting Started](docs/getting-started.md)
- [Command Reference](docs/commands.md)
- [Privacy Review](docs/privacy-review.md)
- [Repository Review](docs/repository-review.md)

## Development Checks

```powershell
cargo fmt --all -- --check
cargo test --workspace
cargo doc --workspace --no-deps
cargo clippy --workspace --all-targets -- -D warnings
```

Formatting, tests, rustdoc, and strict clippy are expected to pass from the current worktree.

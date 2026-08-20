# ADR 001: Skill-Based Staged Synthesis

Status: Accepted

## Context

The previous Rust CLI implemented a narrow numeric diffusion experiment and copied categorical values. It could not express column-level privacy, provide a mature DP training accountant, or independently gate release quality and replay risk.

## Decision

Replace the application with four self-contained Codex skills for planning, generation, evaluation, and orchestration. Use `mostlyai-engine==2.6.2` directly because its engine SDK is Apache-2.0 and supports mixed-type TabularARGN modeling, value protection, flexible seeded generation, and DP-SGD checkpoint accounting.

Split generation into public resampling, non-DP protected modeling, DP private modeling, identifier replacement, and field removal. Keep evaluation independent of generation and make its report the release decision.

## Consequences

- Privacy intent is explicit and reviewable per column.
- Public values can preserve exact utility without creating a false privacy claim.
- Private columns have formal DP budget evidence, while proxy diagnostics remain clearly labeled.
- High-cardinality or difficult fields may need stronger encoding, longer training, or removal from a release profile.
- Python 3.12 and a substantial CPU ML dependency set replace the previous Rust build.
- The source repository selects permissive SDKs; transitive file-level licenses remain documented and audited separately.

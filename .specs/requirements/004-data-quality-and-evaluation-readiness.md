# Requirement 004: Data Quality and Evaluation Readiness

Status: Accepted

## Objective

Make calibration-data quality and evaluation capacity independently auditable before interpreting synthetic-data
skill results. Hardware readiness must never be confused with candidate quality, and neither can waive privacy or
release gates.

## Requirements

1. Every retained public-data artifact shall be checked against its manifest byte size and SHA-256 digest.
2. Archives and workbooks shall pass container-integrity checks; structured data shall expose the required source
   columns and parse without malformed rows.
3. Critical codes, numeric measures, aggregate weights, and privacy-minimized schemas shall be validated using
   source-aware contracts. Valid publisher encodings and suppression markers shall not be treated as corruption.
4. Full-scan record counts shall reconcile to the independent coverage report. Sampling mode may support quick
   diagnostics but is not final evidence.
5. Missing high-value dimensions and known source-population limitations shall remain warnings in the report rather
   than being silently imputed or omitted.
6. Local evaluation readiness shall require at least 8 logical CPUs, 16 GiB physical memory, 20 GiB free workspace
   storage, Python 3.12, the locked runtime packages, and successful execution of the real planner/generator/evaluator
   matrix. These are the repository's smoke/low-volume baseline, not a universal production sizing claim.
7. A GPU shall remain optional for the current CPU-capable tabular workflow. GPU availability shall be reported when
   detected, but absence alone shall not fail local readiness.
8. Harbor readiness shall be reported separately and shall require a working Docker server in addition to local
   readiness and the checked-in Harbor configuration.
9. A completed workload with failed quality/privacy gates establishes compute capacity but remains a failed
   candidate. All failed generation and evaluation reports shall be retained as evidence.

## Acceptance

- The full public-data quality audit covers all 40 manifest artifacts and reconciles every covered record count.
- Unit tests prove type, pattern, aggregate-grain, weight, and capacity-versus-quality behavior.
- An actual ordered skill matrix records generation duration, candidate gates, and rejected leaky controls.
- Documentation records local readiness, Harbor readiness, dataset warnings, and skill-quality failures without
  weakening a privacy or release threshold.

# Validation Record

## Automated checks

Run the locked suite with:

```powershell
uv sync --python 3.12 --locked
uv run ruff check skills tests tools
uv run ruff format --check skills tests tools
uv run pytest
uv run python tools/audit_licenses.py
uv lock --check --script skills/plan-synthetic-data/scripts/plan.py
uv lock --check --script skills/generate-synthetic-data/scripts/generate.py
uv lock --check --script skills/generate-synthetic-data/scripts/materialize_spec.py
uv lock --check --script skills/generate-synthetic-data/scripts/evaluate_spec.py
uv lock --check --script skills/evaluate-synthetic-data/scripts/evaluate.py
```

The tests cover policy inference and user overrides, invalid policy rejection, all five table containers, identifier generation, DP checkpoint selection, datetime semantics, quality/privacy metrics, failed-schema report preservation, per-column gates, report binding and tamper detection, skill metadata/links, documentation links, installation, and licensing rules.

They also cover aggregate proxy materialization, conservative role defaults, weighted categories, correlated numeric
statistics, constraint evaluation, `synthetic-reference` provenance, and bound aggregate-spec hashes.

## Public-data example coverage

On 2026-08-27, `tools/generate_public_data_examples.py` generated and verified examples for the original 11 categories
in the email **“public data to find”** plus the privacy-safe realism and relational/mixed-type capability families. The
result covered all 48 U.S.-only manifest artifacts plus two official gap examples from USAspending and U.S. Courts: 50
CSV files and 250 example rows in total.

The verifier checked exact source/category coverage, file containment, nonempty rows, catalog row counts, SHA-256
checksums, and forbidden identifier/contact columns. It found zero forbidden columns. Federal-contract coverage is a
partial public-award proxy for the SAM entity registry, and public-record coverage is limited to aggregate bankruptcy
counts; those limitations are explicit in [the example catalog](public-data-examples.md).

## Public-dataset replication contract coverage

On 2026-08-22, a deterministic aggregate-specification matrix exercised the real materializer, policy builder,
generator, CSV boundary, and constraint evaluator for all 11 public-data categories. Each profile generated 2,000
rows and passed its schema, numeric-type, missingness, marginal, integer, declared-domain, code-pattern, joint,
derived-arithmetic, identifier, datetime, and correlation gates when applicable. CSV tests specifically preserve
leading-zero categorical codes and identifiers from policy-directed type inference.

The complete validation run passed 149 tests, all four skill-package validations, lint and format checks, the
dependency-license audit, all five standalone script-lock checks, and the four-skill installer dry run.

Negative controls reject and preserve reports for malformed codes, nonnumeric and fractional integer values,
undeclared categories, invalid code/description combinations, and broken row totals. Public roles remain explicit;
row-level public-data financial fields retain conservative planner defaults. The coverage does not claim support for
cross-table foreign keys, conditional numeric distributions, nested records, or native identifier checksum/format
semantics; these remain explicit design gaps in
[Requirement 003](../.specs/requirements/003-public-dataset-replication.md).

## Data-quality and evaluation-readiness audit

On 2026-08-27, `tools/audit_public_data_quality.py` hash-checked 217,302,198 retained bytes and fully value-profiled
10,787,077 rows across all 48 U.S.-scope manifest artifacts. Archive integrity, required schemas, critical
numeric/code and U.S.-country validity, aggregate-grain uniqueness, positive aggregate weights, privacy-minimized
column exclusions, and coverage-count reconciliation passed with zero hard failures. Three source-quality warnings
remain visible: 40.28% of FMCSA aggregate groups lack `business_org_desc`, and the official NYC name file contains
8,073 duplicate dimension rows. Exact NYC duplicates are removed before name calibration. The official USDA
Foundation Foods archive also contains 33 unresolved nutrient references (0.019%) and 273 portion-to-food references
(2.493%); the audit records both below its explicit 5% hard-failure threshold, while the derivative uses valid inner
joins only. The documented population/scope limitations remain attached to the result.

The geographic audit retired both Corporations Canada feeds and their four generated data/example artifacts. Their
replacement is the official [Colorado Business Entities](https://data.colorado.gov/Business/Business-Entities-in-Colorado/4ykn-tg5h/about_data)
source with a publisher-side `principalcountry = 'US'` filter: 2,998,731 of 3,098,534 current source entities (96.8%)
are represented in 85,185 retained aggregate groups. The FMCSA query now independently enforces
`phy_country = 'US'`. Iowa's state-registry transform now retains the 330,340 U.S.-home-office entities from its
347,200-row input (95.1%) and drops foreign or missing-country rows before legal-name aggregation. Every retained
country column in the bundle now contains only `US`.

## Privacy-safe realism calibration

The realism profile uses Census surname counts, NYC civil-registration given-name counts, USPS suffix standards, a
six-county TIGER road sample, SEC company-name tokens, Census ZBP city/state/ZIP relationships, and CFPB narrative
unigrams/length bands. It retains no person-name pairs, household addresses, road geometry, narrative rows, phrases,
or token order. The 1.35 GiB staged CFPB archive was deleted after aggregation; no staging directory remained.

At 10,000 rows, the uniform-weight negative control failed nine distribution gates. Public-distribution calibration
passed every benchmark gate and reduced TV from 0.583 to 0.012 for narrative tokens, 0.889 to 0.018 for street
suffixes, 0.440 to 0.074 for surnames, and 0.410 to 0.104 for given names. The real materialize/generate workflow also
passed ordinary evaluation and the final aggregate constraint evaluation: zero template violations, zero identifier
overlap, token TV 0.018, length TV 0.005, and component TVs at or below 0.110. The output remains labeled synthetic;
component recombination cannot guarantee that a generated name or address does not exist in the real world.

On 2026-08-23, the hardened 10,000-row rerun additionally passed complete-policy provenance binding, zero-tolerance
semantic-type validation, identifier nonmissingness/uniqueness, ordinary policy-aware evaluation, and aggregate
constraint evaluation. An explicit missing-generation-report negative control failed only
`generation_report_binding`. Behavioral tests also prove that identifier/drop columns never enter either model stage,
malformed DP checkpoints fail closed, and materialization/generation/evaluation runtime failures preserve new
hash-bound reports without replacing earlier evidence.

The real ordered planner/generator/evaluator matrix completed both 120-row, two-epoch scenarios in 56.17 seconds of
generation time. The tabular candidate passed every gate (numeric KS 0.067, categorical TV 0.064, propensity AUC
0.524, zero exact replay, zero identifier overlap), and its leaky control was rejected. The mixed-text candidate was
correctly retained as a failure: protected rare-value replay, text-length KS (1.0), and character TF-IDF distance
(0.862) exceeded their gates. This is a skill-quality limitation, not a hardware failure.

The 2026-08-23 hardened matrix rerun completed generation in 57.08 seconds, passed the tabular candidate, rejected both
leaky controls, and reproduced the same protected replay and text-quality failures in the mixed-text candidate. All
candidate and control evaluations used complete-policy fingerprints and mandatory bound generation evidence. Local
compute readiness therefore remains true while matrix quality remains false; the failed candidate and reports remain
preserved.

The local readiness audit passed with 16 logical CPUs, 31.4 GiB RAM, 98.3 GiB free workspace storage, Python 3.12.13,
the locked runtime, and an optional RTX 5060 Laptop GPU with 8.0 GiB VRAM. Harbor readiness remains **false** because
Docker is not installed; no Harbor holdout or model-call completion is claimed. See
[Requirement 004](../.specs/requirements/004-data-quality-and-evaluation-readiness.md) for the separation between data,
compute, Harbor, and candidate-quality evidence.

## Direct repository installation

On 2026-08-21, the Codex GitHub skill installer downloaded all four declared paths directly from
`gvillarroel/rata@main` with its public-repository download method into an isolated destination. The installed
`plan-synthetic-data`, `generate-synthetic-data`, `evaluate-synthetic-data`, and `run-synthetic-data-workflow`
directories all contained their `SKILL.md` manifests and complete bundled payloads. The isolated destination was
removed after verification.

The unit suite also compares every file copied by the local installer with its source package, so missing references,
scripts, lockfiles, or agent metadata fail validation before release.

## GitHub download catalog and skill-package validation

On 2026-08-27, the repository landing page download center covers the complete skill bundle, official public
datasets, verified examples, documentation, and evaluation evidence. The detailed catalog exposes all 35 registered
source keys with their direct-download and publisher links; a unit test now requires every downloader-registry entry
to remain present there.

A live refresh downloaded the new Colorado U.S.-only aggregate and the revised FMCSA U.S.-only aggregate, and reached
the Colorado publisher page. The already documented opt-in SSA national-name source still remains outside the
reproducible default. The default is now 34 U.S.-aligned sources and does not silently use a mirror.

The full local quality audit reran successfully across 48 retained artifacts and 10,787,077 scanned rows with zero
failed artifacts. The coverage audit counted 10,933,879 local aligned core records, or 15,329,657 with the U.S.-only
FMCSA server-side aggregate, and the example verifier passed all 13 categories, 50 files, and 250 rows.

All four skill packages passed the skill manifest validator and installer dry run. The final suite passed 149 tests,
and a coverage run measured 58% across all skill and tool scripts; the changed generation and evaluation scripts
ranged from 81% to 90% statement coverage. Lint, formatting, license, script-lock, and Git diff checks also passed.

## Harbor skill benchmark

On 2026-08-20, Harbor 0.18.0 and GEPA 0.1.2 validated a seven-task evolution plan: three development requests, two
validation requests, and two byte-locked holdouts. Native `--print-config` validation passed for every task, and the
evolution dry-run verified exact skill/task digests and split disjointness.

The live evolution doctor stopped before model calls because Docker is not installed. The append-only study preserves
that infrastructure failure, keeps holdout sealed, and records no candidate or promotion claim. See the
[safe publication index](../evaluations/harbor-studies/generate-synthetic-data-v1/publication/index.md).

## Aggregate-only end-to-end evidence

On 2026-08-20, an 800-row aggregate specification with protected age, private income, explicit-public region, an
identifier, and a requested age-income correlation of 0.60 completed proxy materialization, real protected/private
`mostlyai-engine` training, sampling, generation binding, ordinary evaluation, and constraint evaluation.

The two-epoch candidate recorded DP checkpoint ε 1.59 / δ 1e-5 but was rejected for numeric KS and correlation. A new
ten-epoch workspace recorded ε 1.96 / δ 1e-5 and removed the KS failure, but correlation remained only 0.077, so both
the ordinary correlation gates and the aggregate constraint gate still rejected it. Both failed generations and reports
are preserved under ignored local evidence. No privacy or quality threshold was weakened.

## Mixed-type end-to-end run

On 2026-07-19, the complete workflow ran against a local 1,000-row, 13-column Parquet fixture with all five roles:

- `public`: `gender`, `country`
- `protected`: `registration_dttm`
- `private`: `salary`
- `identifier`: `id`, `first_name`, `last_name`, `email`, `ip_address`, `cc`
- `drop`: `birthdate`, `title`, `comments`

The fast profile used 10 epochs, a two-minute stage ceiling, maximum epsilon 8, delta 1e-5, and explicit per-column KS limits of 0.25 for salary and 0.15 for registration time. The generated 1,000-row candidate passed all configured gates:

| Evidence | Result |
| --- | ---: |
| Generation report binding checks | All passed |
| DP checkpoint | epsilon 2.01; delta 1e-5 |
| Mean / worst numeric KS | 0.116 / 0.190 |
| Mean / worst categorical TV | 0.056 / 0.103 |
| Worst missing-rate delta | 0.065 |
| Worst correlation delta | 0.009 |
| Propensity AUC | 0.501 |
| Exact modeled-row replay | 0 |
| Private rare-value replay | 0 |
| Protected rare-value replay | 0.029 |
| Maximum identifier overlap | 0 |

A negative control evaluated the same candidate with a generation report from another run. It exited with code 2 and failed both `generation_report_binding` and `dp_checkpoint_evidence` due mismatched policy, source, and output hashes.

These results establish that the workflow and gates operate end to end on the fixture. They do not generalize the measured utility or privacy diagnostics to a different dataset; every candidate requires its own policy and evaluation report.

## Ordered tabular and text matrix

On 2026-07-26, `tools/run_evaluation_matrix.py` ran the real planner, generator, evaluator, and a leaky negative
control for the ordered `tabular` and `tabular-text` scenarios. The tabular candidate passed all gates. The two-epoch
mixed-text smoke candidate was rejected for protected rare-value replay, text-length KS, and text TF-IDF distance.
Both source-as-candidate controls were rejected for binding, exact replay, identifier overlap, and protected
rare-value replay.

See the [state-of-the-art report](evaluation-state-of-art.md) and
[machine-readable evidence](../evaluations/results/2026-07-26.json) for measured values, hashes, limitations, and next
stages. The failed mixed candidate is retained as evidence; no privacy threshold was weakened.

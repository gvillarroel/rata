# Requirement 005: Privacy-safe realism calibration

## Objective

Improve name, address, business-name, and short-text realism from authoritative public aggregate distributions without
reconstructing public-source rows or weakening identifier, replay, or DP gates.

## Requirements

1. Given and surname sources must be published frequency tables with publisher suppression or a documented minimum
   count. Person-name pairings must never be retained.
2. Address calibration may use road-name, standard suffix, and geography reference data, but must discard geometry,
   address ranges, and road-name/suffix/geography pairings before generation.
3. Public narratives may be processed only after publisher consent/scrubbing safeguards are documented. Retained
   language artifacts must contain high-document-frequency unigrams and coarse length distributions, never narratives,
   phrases, token order, complaint identifiers, companies, or locations.
4. Realistic names, business names, and address-shaped fields remain `identifier` columns excluded from training.
   Weighted templates must be unique, must not reference another identifier or dropped field, and must pass component
   distribution and template-shape gates.
5. Token-sequence fields must pass unigram and length-distribution gates. Passing those gates must not be described as
   grammatical, factual, or semantic quality.
6. A benchmark must compare the calibrated generator with a uniform-weight baseline against the same target
   distributions. Failed benchmark and generation reports remain evidence.
7. Documentation must state geographic and temporal bias and warn that a recombined value may coincidentally match a
   real person, business, or deliverable address.

## Acceptance

- Official sources and direct links are recorded in the public-data manifest.
- Privacy-sensitive source rows are absent after successful processing.
- End-to-end tests prove expected weighted-template/token-sequence success and deliberate-drift failure.
- The calibrated candidate passes all declared privacy and fidelity gates and materially reduces at least one total-
  variation metric by 0.05 versus the uniform baseline.

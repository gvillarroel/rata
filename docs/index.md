---
layout: home
title: Rata
---

<section class="hero" aria-labelledby="rata-title">
  <p class="eyebrow">Synthetic data, with evidence</p>
  <h1 id="rata-title">Build useful synthetic data without relaxing privacy gates.</h1>
  <p class="hero-copy">
    Rata packages planning, generation, evaluation, and end-to-end workflow skills with reproducible public
    calibration data, explicit provenance, and fail-closed release checks.
  </p>
  <div class="hero-actions">
    <a class="button button-primary" href="README.md">Read the documentation</a>
    <a class="button" href="https://github.com/gvillarroel/rata">View on GitHub</a>
  </div>
</section>

<section class="metrics" aria-label="Project highlights">
  <article>
    <strong>30</strong>
    <span>default U.S.-aligned sources</span>
  </article>
  <article>
    <strong>100%</strong>
    <span>U.S. geographic-scope gate</span>
  </article>
  <article>
    <strong>4</strong>
    <span>installable Codex skills</span>
  </article>
</section>

## Explore the project

<div class="card-grid">
  <article class="doc-card">
    <p class="card-kicker">Data</p>
    <h3><a href="public-data-sources.md">U.S. calibration sources</a></h3>
    <p>Official Census, BLS, Colorado, Iowa, FMCSA, CMS, SEC, SBA, CFPB, USPS, SSA, and U.S. Courts sources.</p>
  </article>
  <article class="doc-card">
    <p class="card-kicker">Assurance</p>
    <h3><a href="privacy-model.md">Privacy model</a></h3>
    <p>Column roles, identifier isolation, provenance binding, differential-privacy evidence, and release gates.</p>
  </article>
  <article class="doc-card">
    <p class="card-kicker">Evidence</p>
    <h3><a href="validation.md">Validation record</a></h3>
    <p>Automated checks, negative controls, public-data coverage, quality audits, and documented limitations.</p>
  </article>
  <article class="doc-card">
    <p class="card-kicker">Usage</p>
    <h3><a href="commands.md">Command reference</a></h3>
    <p>Install, plan, generate, evaluate, reproduce the public-data bundle, and run the full workflow.</p>
  </article>
</div>

## U.S. data alignment

The default source catalog is U.S.-only. Every generated manifest row declares `United States` scope. Sources with
country fields are filtered to `US`, and the quality audit rejects any retained row outside that boundary. The
former Canadian registry feeds were replaced with an official Colorado Department of State aggregate covering
entities with U.S. principal addresses.

[Review the complete source and provenance catalog →](public-data-sources.md)

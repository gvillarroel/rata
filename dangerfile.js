/* eslint-disable no-undef */
// Lightweight repository-agnostic PR guardrails.
// Keep this file dependency-free so every repository can run it via `npx danger@13 ci`.

const modified = danger.git.modified_files || [];
const created = danger.git.created_files || [];
const deleted = danger.git.deleted_files || [];
const changed = [...new Set([...modified, ...created, ...deleted])];
const pr = danger.github.pr;

const has = (patterns) => changed.some((file) => patterns.some((pattern) => pattern.test(file)));
const countBy = (patterns) => changed.filter((file) => patterns.some((pattern) => pattern.test(file))).length;

const sourcePatterns = [
  /(^|\/)(src|lib|app|packages|crates|scripts)\//,
  /\.(js|jsx|ts|tsx|mjs|cjs|py|rs|go|sh|bash|zsh)$/,
  /(^|\/)Cargo\.toml$/,
  /(^|\/)pyproject\.toml$/,
  /(^|\/)package\.json$/,
];
const testPatterns = [
  /(^|\/)(test|tests|spec|specs|__tests__)\//,
  /\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs|py)$/,
  /(^|\/)pytest\.ini$/,
];
const docsPatterns = [
  /(^|\/)(README|CHANGELOG|CONTRIBUTING|AGENTS)\.md$/i,
  /(^|\/)docs\//,
  /\.md$/,
];
const workflowPatterns = [/(^|\/)\.github\/workflows\//];
const secretRiskPatterns = [
  /(^|\/)\.env$/,
  /(^|\/)\.env\.(local|production|prod|staging|dev)$/,
  /(^|\/)(secrets?|credentials?|tokens?)\.(json|ya?ml|toml|ini|txt)$/i,
  /(^|\/)(id_rsa|id_ed25519|.*\.pem|.*\.key)$/i,
];

const sourceChanged = has(sourcePatterns);
const testsChanged = has(testPatterns);
const docsChanged = has(docsPatterns);
const workflowsChanged = has(workflowPatterns);
const riskySecrets = changed.filter((file) => secretRiskPatterns.some((pattern) => pattern.test(file)) && !/\.example$/i.test(file));

if (pr.draft) {
  markdown('ℹ️ Draft PR: quality gate is running in advisory mode until the PR is ready for review.');
}

if (!pr.body || pr.body.trim().length < 80) {
  warn('Please add a useful PR description with context, implementation notes, and verification evidence.');
}

const additions = pr.additions || 0;
const deletions = pr.deletions || 0;
const totalChangedLines = additions + deletions;
if (totalChangedLines > 1500) {
  fail(`This PR changes ${totalChangedLines} lines. Split it or document why a large atomic change is necessary.`);
} else if (totalChangedLines > 500) {
  warn(`This PR changes ${totalChangedLines} lines. Consider splitting if review scope is broad.`);
}

if (changed.length > 40) {
  warn(`This PR touches ${changed.length} files. Consider splitting by concern if possible.`);
}

if (riskySecrets.length > 0) {
  fail(`Potential secret-bearing files changed: ${riskySecrets.join(', ')}. Use examples/templates or a secret manager instead.`);
}

if (sourceChanged && !testsChanged) {
  warn('Source/config changed without test changes. Add tests or explain why existing coverage is sufficient.');
}

if (sourceChanged && !docsChanged) {
  warn('Source/config changed without docs/README/changelog updates. Add docs or explain why none are needed.');
}

if (workflowsChanged && !docsChanged) {
  warn('GitHub Actions changed without documentation updates. Consider documenting the CI behavior or operational impact.');
}

const packageJsonChanged = changed.includes('package.json');
const packageLockChanged = changed.includes('package-lock.json') || changed.includes('pnpm-lock.yaml') || changed.includes('yarn.lock');
if (packageJsonChanged && !packageLockChanged) {
  warn('package.json changed without a lockfile update. Confirm this repository intentionally does not use a lockfile.');
}
if (!packageJsonChanged && packageLockChanged) {
  warn('Lockfile changed without package.json. Confirm this is expected.');
}

const cargoTomlChanged = changed.includes('Cargo.toml');
const cargoLockChanged = changed.includes('Cargo.lock');
if (cargoTomlChanged && !cargoLockChanged) {
  warn('Cargo.toml changed without Cargo.lock. Confirm this is expected for this Rust crate.');
}

markdown([
  '### DangerJS quality summary',
  `- Changed files: ${changed.length}`,
  `- Source/config files: ${countBy(sourcePatterns)}`,
  `- Tests/spec files: ${countBy(testPatterns)}`,
  `- Docs files: ${countBy(docsPatterns)}`,
  `- Changed lines: +${additions} / -${deletions}`,
].join('\n'));

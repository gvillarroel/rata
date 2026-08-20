# Licensing Boundary

Rata is Apache-2.0. Its selected synthesis SDK, `mostlyai-engine==2.6.2`, is also Apache-2.0. The repository uses only the engine package, not the broader `mostlyai[local]` extra; that avoids connector dependencies outside the intended permissive SDK boundary.

Runtime and evaluation packages are pinned in `pyproject.toml`, the PEP 723 script headers, adjacent script lockfiles, and the root `uv.lock`. `tools/audit_licenses.py` rejects GPL, AGPL, LGPL, SSPL, and other strong/network-copyleft package metadata.

Two transitive utility/data packages currently contain file-level MPL-2.0 notices: `certifi` (the CA certificate bundle used by HTTP clients) and portions of `tqdm`; `tqdm` also contains MIT-licensed work. They are not selected synthesis SDKs, are not modified or redistributed by this source repository, and are reported by the audit for review rather than hidden. Organizations that require a dependency closure with no reciprocal license of any kind must make a separate packaging decision before distributing a bundled environment.

Run the audit after every lockfile change:

```powershell
uv run python tools/audit_licenses.py
```

This documentation is an engineering inventory, not legal advice.

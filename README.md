# Rata Synthetic Data Skills

Four self-contained synthetic-data skills plus one Harbor dataset-authoring
skill. The workflow uses the mostlyai-engine SDK, keeps generation separate
from release evaluation, and keeps optimizer-visible development tasks
separate from sealed validation.

A passing evaluation is evidence against configured gates, not proof of anonymization. Preserve failed reports; never weaken privacy roles or release criteria to obtain a pass.

## Get started

Install the five independent skills from GitHub by asking Codex:

```text
Use $skill-installer to install all of these paths from gvillarroel/rata at ref main:
- skills/plan-synthetic-data
- skills/generate-synthetic-data
- skills/evaluate-synthetic-data
- skills/run-synthetic-data-workflow
- skills/harbor-author-evaluation-datasets
```

The scripts use uv and pinned Python environments. For source development and
local installation, follow the [setup guide](docs/getting-started.md).
Read the [privacy model](docs/privacy-model.md) before generating or releasing data.

## Download center

- [Repository ZIP](https://github.com/gvillarroel/rata/archive/refs/heads/main.zip)
- [Official public-data sources and download commands](docs/public-data-sources.md)
- [Small verified public-data examples](docs/public-data-examples.md)

## Documentation

- [Documentation index](docs/README.md)
- [Usage and operations](docs/getting-started.md)
- [Repository layout and validation](docs/repository-guide.md)
- [Command reference](docs/commands.md)
- [Privacy model](docs/privacy-model.md)
- [Architecture](docs/architecture.md)
- [AGENTS.md](AGENTS.md)

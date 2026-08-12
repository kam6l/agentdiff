---
title: Installation
description: Install the AgentDiff alpha from source with Python 3.14 and uv.
---

<span class="ad-doc-eyebrow">Getting started</span>

# Installation

<div class="ad-doc-lede">AgentDiff is currently a source-distributed technical alpha. The repository is the authoritative installation source; packaged binaries and container images are not published yet.</div>

## Requirements

| Requirement | Current support |
| --- | --- |
| Python | 3.14 or newer |
| Package workflow | `uv` recommended |
| Linux | Primary supported environment |
| macOS | Supported for local observation; platform evidence varies |
| WSL2 | Suitable for Linux-mode evaluation |
| Native Windows | Alpha; filesystem parity work remains |

## Install as a CLI tool

`uv tool install` creates an isolated environment and places `agentdiff` on your path:

```bash
uv python install 3.14
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv tool install .

agentdiff --help
agentdiff doctor
```

If `~/.local/bin` is not on your path, follow the instruction printed by `uv tool ensurepath`, then open a new shell.

## Contributor installation

Use the locked development environment when changing AgentDiff itself:

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --all-groups

uv run agentdiff --help
uv run pytest
uv run ruff check src tests
uv run mypy
```

## Run without installing globally

Inside a cloned checkout, every command can be invoked through `uv`:

```bash
uv run agentdiff doctor
uv run agentdiff policy init --output /path/to/project/agentdiff.yaml
uv run agentdiff run --root /path/to/project -- python3 /path/to/project/task.py
```

## Verify runtime capabilities

```bash
agentdiff doctor
```

The doctor report distinguishes implemented behavior from capability boundaries, including:

- local subprocess observation;
- filesystem mutation capture;
- owned-descendant process observation;
- machine-wide port observation;
- optional Anthropic Sandbox Runtime availability;
- policy and rollback behavior.

Use JSON when integrating the report into automation:

```bash
agentdiff doctor --format json
```

## Upgrade or remove

From a fresh checkout of the revision you trust:

```bash
uv tool install --force .
```

Remove the isolated tool environment with:

```bash
uv tool uninstall agentdiff
```

## Distribution status

<div class="ad-doc-notice ad-doc-notice--neutral" markdown>
**Not currently published:** PyPI releases, standalone binaries, Docker images, Homebrew formulae, and Scoop packages. Avoid install commands from third-party pages that imply otherwise. Track release work on [GitHub](https://github.com/kam6l/agentdiff/releases).
</div>

## Next steps

- [Run the quickstart](quickstart.md)
- [Read the runtime capability model](concepts/runtime.md)
- [Review the CLI](cli/index.md)

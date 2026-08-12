---
title: Installation
description: Install the AgentDiff 0.1.0 beta from source on Python 3.12 or newer.
---

<span class="ad-doc-eyebrow">Getting started</span>

# Installation

<div class="ad-doc-lede">AgentDiff is source-distributed beta software. It is not currently published to PyPI, a container registry, Homebrew, Scoop, or a binary release channel.</div>

## Requirements

| Requirement | Current support |
|---|---|
| Python | 3.12, 3.13, or 3.14 |
| Package workflow | `uv` recommended |
| Linux | Beta local runtime |
| macOS | Beta local runtime; observation detail depends on OS permissions |
| Native Windows | Beta local runtime; no dedicated process session |

## Install the CLI

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv tool install .

agentdiff --help
agentdiff doctor
```

`uv tool install` creates an isolated environment and exposes the `agentdiff` command. If the executable directory is not on `PATH`, run `uv tool ensurepath` and open a new terminal.

## Contributor setup

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --locked --all-groups

uv run pytest
uv run ruff format --check src tests examples benchmarks
uv run ruff check src tests examples benchmarks
uv run mypy src/agentdiff
```

## Upgrade or remove

From a fresh checkout of the revision you trust:

```bash
uv tool install --force .
```

Remove it with:

```bash
uv tool uninstall agentdiff
```

## Verify the boundary

Run `agentdiff doctor --format json` on each target machine. The report distinguishes filesystem observation, best-effort process evidence, machine-wide port observation, local non-enforcement, recovery scope, and optional external-runtime detection.

## Next steps

- [Run the quickstart](quickstart.md)
- [Read the runtime model](concepts/runtime.md)
- [Review the CLI](cli/index.md)

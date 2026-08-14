---
title: Quickstart
description: Record a real AgentDiff transaction and selectively recover collateral.
---

<span class="ad-doc-eyebrow">Getting started</span>

# Quickstart

<div class="ad-doc-lede">Run an intentionally risky command, inspect its independent evidence, and remove only unchanged collateral while preserving the allowed edit.</div>

## 1. Install from source

You need Python 3.14 (or 3.12+) and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv tool install .
```

## 2. Create a disposable project

```bash
mkdir agentdiff-quickstart
cd agentdiff-quickstart
agentdiff policy init
```

The generated `agentdiff.yaml` allows `src/**`, reviews dependency metadata, denies common secret paths, observes network-related state without blocking traffic, and enables bounded recovery backups.

## 3. Create the task

Save this as `agent_task.py`:

```python
from pathlib import Path

Path("src").mkdir(exist_ok=True)
Path("src/parser.py").write_text("def parse(value):\n    return value.strip()\n")
Path("pyproject.toml").write_text('[project]\nname = "demo"\n')
Path(".env").write_text("API_TOKEN=demo-only\n")
```

The values are synthetic, but use only a disposable workspace for the walkthrough.

## 4. Run under observation

```bash
agentdiff run --task "Update the parser" -- python agent_task.py
```

The human summary now leads with the outcome:

```text
Task completed

Expected changes:   1
Unexpected changes: 1
Protected changes:  1

Blast Radius: CRITICAL (81/100)
Recovery available: YES
Policy outcome: DENY
```

The process completed, but the transaction returns exit code `3` because a protected mutation was observed. Local mode records the write after execution; it does not intercept or block it.

## 5. Inspect and verify

Copy the run ID printed below the summary:

```bash
agentdiff inspect <run-id>
agentdiff verify <run-id>
```

## 6. Recover only collateral

```bash
agentdiff rollback <run-id> --safe-only
```

Expected result:

```text
Actions: 2
  removed  .env
  removed  pyproject.toml
Conflicts: 0
Skipped: 1
```

`src/parser.py` stays because policy allowed it. If a person or later process changed a collateral path, AgentDiff records a conflict and preserves the current path.

## Next steps

- [Understand the runtime and limits](concepts/runtime.md)
- [Customize mutation policy](concepts/policy.md)
- [Connect Cortex to Claude, Codex, or Ollama](concepts/cortex.md)
- [Review every CLI command](cli/index.md)

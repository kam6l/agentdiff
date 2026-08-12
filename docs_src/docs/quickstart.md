---
title: Quickstart
description: Install AgentDiff, record a real transaction, inspect its evidence, and selectively recover collateral.
---

<span class="ad-doc-eyebrow">Getting started</span>

# Quickstart

<div class="ad-doc-lede">Run an intentionally risky local command, inspect the durable evidence it produces, and remove only the collateral while preserving the allowed change.</div>

## Prerequisites

- Python **3.14 or newer**
- [`uv`](https://docs.astral.sh/uv/) for the recommended installation path
- Linux or macOS; WSL2 is suitable for evaluation, but native Windows parity is not complete

## 1. Install from source

```bash
# Clone and install AgentDiff as an isolated command
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv tool install .

# Confirm the implemented command surface
agentdiff --help
```

For contributor setup instead, use `uv sync --all-groups` and prefix commands with `uv run`.

## 2. Create a policy

Move to a disposable project and generate AgentDiff's conservative starter policy:

```bash
mkdir agentdiff-quickstart
cd agentdiff-quickstart
agentdiff policy init
```

The command writes `agentdiff.yaml`. This shortened example preserves source changes, reviews dependency metadata, and denies environment files:

```yaml
version: 1
filesystem:
  allow_write:
    - "src/**"
  review:
    - "pyproject.toml"
  deny:
    - ".env"
    - ".env.*"
    - ".git/**"
  default: review
process:
  allow:
    - "python*"
  default: review
network:
  # Observation only in the local runtime; traffic is not blocked.
  mode: observe
rollback:
  enabled: true
  max_backup_file_mb: 25
```

Validate before using it:

```bash
agentdiff policy validate --policy agentdiff.yaml
agentdiff policy explain .env --policy agentdiff.yaml
```

## 3. Create an intentionally risky task

Create `agent_task.py`:

```python
from pathlib import Path

Path("src").mkdir(exist_ok=True)

# Intended change — allowed by src/**
Path("src/parser.py").write_text(
    "def parse(value):\n    return value.strip()\n",
    encoding="utf-8",
)

# Collateral changes — review and deny
Path("pyproject.toml").write_text(
    '[project]\nname = "demo"\n',
    encoding="utf-8",
)
Path(".env").write_text("API_TOKEN=demo-only\n", encoding="utf-8")
```

## 4. Run under observation

```bash
agentdiff run \
  --task "Update the parser" \
  --format summary \
  -- python3 agent_task.py
```

A representative output from this exact example:

```text
Run: <run-id>
Status: denied (deny)
Blast radius: 81/100 (critical)
Runtime: local-observe (observation)
Mutations: 3
  deny   created  .env
  review created  pyproject.toml
  allow  created  src/parser.py
```

!!! note "A denied transaction still records evidence"
    The subprocess completed successfully, but AgentDiff returned a non-zero policy status because a deny mutation was observed. Local observation does not retroactively block the write.

## 5. Inspect and verify

Copy the run ID from the output:

```bash
agentdiff inspect <run-id>
agentdiff verify <run-id>
```

`inspect` summarizes the durable capsule. `verify` checks the capsule's checksum manifest before you trust or transport it.

## 6. Recover only the collateral

```bash
agentdiff rollback <run-id> --safe-only
```

For this example, the result is:

```text
Actions: 2
  removed  .env
  removed  pyproject.toml
Conflicts: 0
Skipped: 1
```

`src/parser.py` remains because policy allowed it. If a current path no longer matches the recorded post-run state, AgentDiff reports a conflict instead of overwriting the later edit.

## What you now have

<div class="ad-doc-checklist" markdown>
- [x] A no-follow before/after filesystem manifest
- [x] An allow, review, or deny decision for each mutation
- [x] An explainable 0–100 blast-radius score
- [x] A checksum-verified local run capsule
- [x] A recorded, conflict-checked recovery result
</div>

## Next steps

- [Understand the runtime and its limits](concepts/runtime.md)
- [Customize mutation policy](concepts/policy.md)
- [Learn how the score is calculated](concepts/blast-radius.md)
- [Review every CLI command](cli/index.md)

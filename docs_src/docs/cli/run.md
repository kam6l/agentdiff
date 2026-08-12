---
title: Run a transaction
description: Wrap an explicit command with AgentDiff local observation or Anthropic Sandbox Runtime enforcement.
---

<span class="ad-doc-eyebrow">CLI · Transactions</span>

# Run a transaction

`agentdiff run` captures baseline state, executes an explicit argv, evaluates the resulting evidence, and persists the complete capsule.

```bash
agentdiff run [options] -- <command> [arguments...]
```

## Minimal example

```bash
agentdiff run \
  --task "Fix the parser" \
  -- python3 agent_task.py
```

Everything after `--` is treated as the subprocess argv. AgentDiff does not invoke a shell unless the argv explicitly launches one.

## Options

| Option | Meaning |
| --- | --- |
| `--root PATH` | Project root and `.agentdiff` evidence location. Defaults to `.`. |
| `--policy PATH` | YAML or JSON policy. Defaults to `<root>/agentdiff.yaml` when present. |
| `--task TEXT` | Human-readable intended task stored in the capsule. |
| `--timeout SECONDS` | Maximum runtime before AgentDiff terminates the observed command. |
| `--runtime local\|srt` | Local observation or Anthropic Sandbox Runtime. |
| `--srt-executable PATH` | Sandbox Runtime executable used with `--runtime srt`. |
| `--srt-settings PATH` | Sandbox Runtime settings JSON. |
| `--format summary\|json` | Human or machine-readable result. |
| `--fail-on never\|review\|deny` | Policy outcome that produces a non-zero CLI status. Defaults to `deny`. |

## Local observation

```bash
agentdiff run \
  --root /workspace/project \
  --policy /workspace/project/agentdiff.yaml \
  --runtime local \
  --format json \
  -- python3 /workspace/project/task.py
```

The local backend observes the subprocess and state around it. It does **not** block network traffic or provide a kernel containment boundary.

## Sandbox Runtime

```bash
agentdiff run \
  --runtime srt \
  --srt-executable srt \
  --srt-settings sandbox-settings.json \
  -- python3 agent_task.py
```

AgentDiff still owns the evidence and policy result; the selected external runtime owns enforcement. See [Anthropic Sandbox Runtime](../integrations/sandbox-runtime.md).

## Automation

Use JSON and select the policy threshold explicitly:

```bash
agentdiff run \
  --format json \
  --fail-on review \
  -- python3 agent_task.py > agentdiff-result.json
```

!!! warning "A local deny is an observed outcome"
    In local observation mode, a denied filesystem mutation may already exist when the transaction ends. Use [safe rollback](rollback.md) or an enforcement-capable runtime as appropriate.

---
title: Recover safely
description: Conflict-check current state and selectively recover AgentDiff transaction changes.
---

<span class="ad-doc-eyebrow">CLI · Recovery</span>

# Recover safely

Rollback compares the current path with the exact state recorded after the run. If they differ, AgentDiff reports a conflict instead of overwriting a later edit.

```bash
agentdiff rollback <run-id> (--safe-only | --all) [options]
```

## Selective recovery

```bash
agentdiff rollback <run-id> --safe-only
```

`--safe-only` targets eligible **review** and **deny** mutations. Allowed work is skipped.

```text
Actions: 2
  removed  .env
  removed  pyproject.toml
Conflicts: 0
Skipped: 1
```

## Full recovery

```bash
agentdiff rollback <run-id> --all
```

`--all` includes allowed changes when recovery evidence exists and the current-state comparison is safe. It is not a force flag: conflicts still protect later edits.

## Limit recovery to paths

Repeat `--path` to select relative paths:

```bash
agentdiff rollback <run-id> \
  --safe-only \
  --path .env \
  --path pyproject.toml
```

## Options

| Option | Meaning |
| --- | --- |
| `--root PATH` | Project root containing the capsule. |
| `--safe-only` | Recover eligible review and deny changes only. |
| `--all` | Recover every eligible policy class. |
| `--path RELATIVE_PATH` | Limit selection; repeat for multiple paths. |
| `--format summary\|json` | Human or machine-readable result. |

## Conflict model

For a file created during the run, removal is eligible only when the current file still matches the recorded post-run digest. Modified and deleted files use equivalent current-state checks against stored evidence.

!!! danger "Rollback is evidence-dependent"
    Files that exceeded backup limits, unsupported filesystem entries, or missing/corrupt evidence cannot be recovered safely. Inspect the JSON result and capsule integrity before relying on automation.

## Recovery audit trail

AgentDiff records the rollback result and appends recovery events to the capsule. Run `agentdiff verify <run-id>` again after recovery to validate the updated integrity manifest.

---
title: Operations
description: List, verify, clean up, and diagnose AgentDiff runs; plus the legacy snapshot evaluator commands.
---

<span class="ad-doc-eyebrow">CLI · Operations</span>

# Operations

## List run capsules

```bash
agentdiff runs [--root PATH] [--limit N] [--format summary|json]
```

```bash
agentdiff runs --root /workspace/project --limit 10
```

Runs are read from `<root>/.agentdiff/runs/` and ordered for recent inspection.

## Verify capsule integrity

```bash
agentdiff verify <run-id> [--root PATH] [--format summary|json]
```

Use this before automated recovery or evidence transport. It validates checksums; it is not a cryptographic signature.

## Clean stored process identities

```bash
agentdiff cleanup <run-id> \
  [--root PATH] \
  [--grace-period SECONDS] \
  [--format summary|json]
```

Cleanup works from stored PID and process-create-time identities so PID reuse does not silently target an unrelated process.

## Report runtime capabilities

```bash
agentdiff doctor [--format summary|json]
```

The report is intentionally explicit about observation versus enforcement. Include it in bug reports involving platform behavior.

## Legacy evaluator commands

The transaction workflow above is the primary interface. These commands remain available for the earlier snapshot/trajectory evaluator.

### Capture a snapshot

```bash
agentdiff snapshot \
  [--root PATH] \
  [--ignore GLOBS] \
  [--max-size BYTES] \
  [--no-env] [--no-proc] [--no-ports] \
  [--output FILE]
```

### Diff two snapshots

```bash
agentdiff diff pre.json post.json \
  [--root PATH] \
  [--format summary|json]
```

### Evaluate a trajectory

```bash
agentdiff eval trajectory.json \
  [--pre pre.json] \
  [--post post.json] \
  [--root PATH] \
  [--target path-a,path-b] \
  [--threshold NUMBER] \
  [--format summary|json] \
  [--fail-on-failure]
```

!!! note
    Legacy snapshot evaluation and durable run transactions are separate data paths. Do not assume one command's artifact is accepted by the other without checking the schema.

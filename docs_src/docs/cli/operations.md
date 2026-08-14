---
title: Operations
description: List, verify, clean up, and diagnose AgentDiff transaction runs.
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

The former `snapshot`, `diff`, and `eval` commands are no longer public CLI verbs. The earlier evaluator modules remain internal compatibility imports while the transaction surface stabilizes.

---
title: Inspect evidence
description: Inspect and verify durable AgentDiff run capsules.
---

<span class="ad-doc-eyebrow">CLI · Evidence</span>

# Inspect evidence

Every transaction receives a time-ordered run ID and a durable capsule under `<root>/.agentdiff/runs/`.

## Inspect a capsule

```bash
agentdiff inspect <run-id> [--root PATH] [--format summary|json]
```

Summary output includes the intended task, command, process return code, safety outcome, blast radius, runtime mode, creation time, and capsule-integrity state.

```bash
agentdiff inspect 20260811T110755Z-e45c0d69a41e \
  --root /workspace/project
```

```text
Run: 20260811T110755Z-e45c0d69a41e
Task: Update the parser
Status: denied (deny)
Blast radius: 81/100
Return code: 0
Capsule integrity: true
```

## Inspect as JSON

```bash
agentdiff inspect <run-id> --format json > run.json
```

Prefer JSON for CI, regression analysis, or a future evidence viewer. Do not parse the presentation-oriented summary text.

## Verify before trusting

```bash
agentdiff verify <run-id> --root /workspace/project
```

`verify` checks the capsule checksum manifest and fails when a recorded file is missing or no longer matches its digest.

```text
Capsule integrity: valid
Files checked: 9
```

## Capsule contents

The exact set varies by backend and run, but transaction capsules include evidence such as:

| File | Purpose |
| --- | --- |
| `before.json` / `after.json` | Secure filesystem manifests |
| `metadata.json` | Run identity, task, command, and timestamps |
| `policy.json` | Versioned policy used for evaluation |
| `runtime.json` | Process/runtime observations |
| `result.json` | Mutations, decisions, score, and outcome |
| `events.jsonl` | Append-oriented runtime evidence |
| `integrity.json` | Checksum manifest for capsule files |
| `recovery-events.jsonl` | Recovery audit events when rollback runs |

!!! note
    Integrity is tamper-evidence, not a signature or remote attestation. Anyone who can rewrite the capsule and its checksum manifest can produce a new internally consistent capsule.

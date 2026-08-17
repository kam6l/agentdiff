---
title: Capsule reference
description: Files and trust properties of an AgentDiff 0.2.x run capsule.
---

# Capsule reference

Each transaction writes a local capsule below:

```text
<project>/.agentdiff/runs/<run-id>/
```

This is a filesystem artifact format, not an HTTP API.

## Core files

| File | Contents |
|---|---|
| `metadata.json` | Run ID, task, redacted command, creation time, schema version |
| `policy.json` | Exact version-1 policy used for the run |
| `before.json` / `after.json` | No-follow filesystem manifests |
| `runtime.json` | Backend, argv evidence, exit state, process cleanup, and port observation |
| `result.json` | Classified changes, limit violations, warnings, score, status |
| `events.jsonl` | Redacted transaction events |
| `integrity.json` | SHA-256 manifest covering sealed capsule artifacts |
| `backups/` | Bounded before-state content for eligible regular files |

Rollback can add `rollback-result.json` and recovery events after the original seal. Use `agentdiff verify <run-id>` before trusting or recovering a capsule.

## Result shape

`result.json` and `agentdiff run --format json` expose:

```json
{
  "schema_version": 1,
  "run_id": "<run-id>",
  "status": "denied",
  "safety_outcome": "deny",
  "command_decision": {},
  "changes": [],
  "limit_violations": [],
  "observation_warnings": [],
  "blast_radius": {},
  "runtime": {},
  "execution_error": null
}
```

Each change includes the root-relative path, `created` / `modified` / `deleted` type, policy decision and provenance, and whether verified recovery evidence is available.

## Status values

| Status | Meaning |
|---|---|
| `passed` | Command succeeded and policy outcome was `allow` |
| `review` | Command succeeded with review evidence or warnings |
| `denied` | Command succeeded but at least one outcome was `deny` |
| `blocked` | Command policy denied launch |
| `failed` | The subprocess returned non-zero |
| `timed_out` | Runtime timeout elapsed |
| `error` | AgentDiff could not launch the command |

## Trust properties

- Capsule checksums detect ordinary mutation; they are not signatures or remote attestation.
- Stored command and event fields use central redaction, but a workspace file can still contain secrets.
- Symlinks are recorded without traversal and are not recoverable.
- Recovery changes a path only when current state equals the recorded post-run state.
- Port differences are machine-wide point-in-time observations, not causal attribution.

See the [Python API](sdk-reference.md), [inspection commands](cli/inspect.md), and [security limits](trust.md).

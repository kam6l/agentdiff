---
title: Automatic repair loop
description: Verified retries until proof passes or the trust boundary changes.
---

# Automatic repair loop

When proof fails, AgentDiff does **not** immediately ask the developer. It
creates a small deterministic **failure packet** and sends it back to the same
agent for a bounded repair attempt:

```text
attempt 1
  → proof fails
  → failure packet: failed phases, failed tests, changed files, policy,
    allowed scope, risk evidence, patch digest
  → same agent runs a bounded repair attempt
attempt 2
  → proof passes
  → REPAIRED
```

```bash
agentdiff repair RUN_ID [--max-attempts 2] [--max-runtime 1800]
```

## Failure packet

The packet is written to `.agentdiff/repair/<run-id>/attempt-<n>-packet.json`
and contains exactly what the repair is allowed to see:

- failed verification phases and test counts
- changed files with their policy decisions
- the immutable policy and the allowed write scope
- immediate and future blast radius evidence
- proof reasons, patch digest, base digest

## Hard limits (non-negotiable)

- `max_attempts` — no infinite retry loops
- `max_runtime_seconds` — a monotonic budget (blocked when exceeded)
- no silent scope expansion — any dependency/CI/config/security change,
  any `review`/`deny` policy action, or high future risk stops the loop
- no permission escalation — repair runs under the same policy and sandbox
- the agent can never approve its own permissions

Each repair attempt runs in a **fresh workspace** derived from the same trusted
base, so proof always verifies a clean base plus the repaired patch.

## Human Attention Router

`HumanAttentionRouter` classifies every outcome deterministically:

| Kind | Condition |
|---|---|
| `AUTO` | normal source change, proof passes |
| `RETRY` | proof fails, repair stays in scope |
| `HUMAN` | dependency added, CI changed, review/deny action, high future risk |

Repair loop outcomes: `REPAIRED`, `FAILED`, `NEEDS_HUMAN`, `NEEDS_AGENT`
(no repair command configured — packet written), `BLOCKED` (budget exceeded).

## Repair drivers

The default driver re-invokes the **same agent CLI** with the bounded repair
prompt (prompt-taking CLIs such as `codex exec`, `claude -p`, `gemini -p`
have their prompt argument replaced; other commands get the prompt appended).
Programmatic callers can inject a custom `repair_command_builder`.

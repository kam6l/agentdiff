---
title: Zero-touch automation
description: Run coding agents through AgentDiff without manual run/prove/promote steps.
---

# Zero-touch automation

AgentDiff can become a **Human Attention Router** between a coding agent and
the repository. Instead of manually running `agentdiff run`, `agentdiff prove`,
and `agentdiff promote`, normal use becomes:

```bash
agentdiff init                # compile the canonical trust configuration
agentdiff wrap -- codex exec "Fix authentication timeout"
```

or, with the sidecar running:

```bash
agentdiff init --daemon       # compile trust config and start the sidecar
codex exec "Fix authentication timeout"
```

AgentDiff then automatically:

1. understands the repository (bootstrap trust compiler),
2. prepares a private warm workspace (immutable base, copy-on-write clone),
3. observes and enforces the agent's work with the canonical policy,
4. detects scope/risk deterministically,
5. runs the minimum strong proof (impact-aware, cache-backed),
6. retries failures automatically while the repair stays in scope,
7. asks the human only when the trust boundary changes,
8. promotes the proven result to the repository and attaches evidence.

## The routing contract

| Outcome | Action |
|---|---|
| Normal source change + proof passes | **AUTO** (promote + notify) |
| Proof fails, repair stays in scope | **RETRY** (bounded automatic repair) |
| Dependency added / CI changed / config changed | **HUMAN** review |
| Agent requests new scope | **HUMAN** |
| Unexpected high future risk | **HUMAN** |

No model decides a trust verdict. Every AUTO/RETRY/HUMAN decision is computed
from deterministic policy, path classification, and proof results.

## Commands

| Command | Purpose |
|---|---|
| `agentdiff init` | Bootstrap trust configuration (+ `--daemon` starts the sidecar) |
| `agentdiff wrap -- <agent argv>` | Run one agent through the full pipeline |
| `agentdiff serve [--daemon]` | Start the local sidecar daemon |
| `agentdiff status` / `stop` | Sidecar lifecycle |
| `agentdiff hook <event>` | Send lifecycle/tool events to the sidecar |
| `agentdiff repair <run-id>` | Run the automatic repair loop on a failed proof |
| `agentdiff prove <run-id>` | Deterministic clean-room proof (cache-aware) |
| `agentdiff promote <run-id>` | Conflict-safe promotion to the host repository |

## Wrap pipeline

`agentdiff wrap` runs these stages in order:

```text
agent argv
  → warm workspace (private CoW clone of the trusted base)
  → observed/enforced transaction (canonical policy)
  → clean-room proof (impact plan + proof cache)
  → on failure: failure packet → bounded repair attempt → re-prove
  → promotion gate (host state must still equal the recorded base)
  → evidence capsule + local notifications
```

The host repository is never writable inside the agent sandbox: the agent works
on a private clone, and only the proven patch is promoted.

## Sidecar

The sidecar is a small local HTTP daemon bound to `127.0.0.1` with a per
repository bearer token stored under `.agentdiff/sidecar/`. It exposes
`/v1/run`, `/v1/prove`, `/v1/repair`, `/v1/promote`, `/v1/session/*`, and
`/v1/notify`. There is no hosted service and no network exposure.

Agent adapters (MCP tool calls, CLI wrappers) send lifecycle events through
`agentdiff hook`; the sidecar evaluates tool calls with the deterministic
`MCPPolicyHook` and records every decision.

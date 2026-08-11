# Home

Welcome to AgentDiff — the runtime evidence layer for autonomous agents.

## Quick Links

- **[Quickstart](quickstart.md)** — Run your first observed transaction in 2 minutes
- **[Installation](installation.md)** — Binary install, from source, or Docker
- **[CLI Reference](cli.md)** — Complete command documentation
- **[Concepts](concepts/runtime.md)** — Deep dive into the runtime model

## What is AgentDiff?

AgentDiff is a local-first runtime layer that wraps any command an agent runs. It captures a secure **no-follow filesystem manifest** before and after execution, evaluates every mutation against a **versioned policy** (allow · review · deny), computes an **explainable blast-radius score**, and offers **conflict-safe selective recovery** — keeping intended changes while reverting only unchanged collateral.

## Core Concepts

| Concept | Description |
|---------|-------------|
| **[Runtime Model](concepts/runtime.md)** | Secure manifests, owned-process evidence, machine-wide port observation |
| **[Mutation Policy](concepts/policy.md)** | Versioned allow/review/deny rules with exact rule provenance |
| **[Blast-Radius Scoring](concepts/blast-radius.md)** | Deterministic additive weights, capped at 100, fully explainable |
| **[Selective Recovery](concepts/recovery.md)** | Conflict-safe rollback that preserves later edits to reverted files |

## Quick Example

```bash
# Initialize a starter policy
agentdiff policy init

# Explain what a path would match
agentdiff policy explain .env

# Run any command under observation
agentdiff run \
  --task "Fix the parser" \
  -- python3 agent.py

# Inspect the run capsule
agentdiff inspect <run-id>

# Recover only safe collateral
agentdiff rollback <run-id> --safe-only
```
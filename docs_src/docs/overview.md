# AgentDiff Documentation

**Runtime evidence and conflict-safe recovery for autonomous agents.**

---

## What is AgentDiff?

AgentDiff is a local-first runtime layer that wraps any command an agent runs. It captures a secure **no-follow filesystem manifest** before and after execution, evaluates every mutation against a **versioned policy** (allow · review · deny), computes an **explainable blast-radius score**, and offers **conflict-safe selective recovery** — keeping intended changes while reverting only unchanged collateral.

## Why AgentDiff?

| Traditional Evaluation | AgentDiff |
|------------------------|-----------|
| "Did tests pass?" | "What exactly changed?" |
| Binary pass/fail | Quantified blast radius (0-100) |
| No visibility into side effects | Every mutation has a policy decision |
| All-or-nothing rollback | Keep intended work, revert only collateral |
| Framework-specific | Framework-neutral (wraps any argv) |

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

## Next Steps

- **[Quickstart](quickstart.md)** — Run your first observed transaction in 2 minutes
- **[Installation](installation.md)** — Binary install, from source, or Docker
- **[Concepts](concepts/runtime.md)** — Deep dive into the runtime model
- **[CLI Reference](cli.md)** — Complete command documentation
---
title: Trust pipeline
description: The explicit Runtime to Safety to Evidence to Risk to Proof to Promotion lifecycle.
---

# The AgentDiff trust pipeline

AgentDiff is a trust boundary between an autonomous coding agent and the real repository:

```text
AI agent
  → runtime
  → isolation
  → live safety controller
  → state observation
  → deterministic policy
  → immediate blast radius
  → future blast radius
  → clean-room proof
  → promotion gate
  → real repository
  → evidence capsule
```

Each decision is deterministic. Cortex may read verified evidence and suggest remediation, but cannot decide policy, risk, proof, promotion, or rollback safety.

## Responsibility map

| Owner | Responsibility |
|---|---|
| `runtime/` | Exact argv execution and honest backend capabilities |
| `safety/` | Live observations and terminate/continue decisions |
| `state/` | No-follow filesystem manifests |
| `policy/` | Command, path, and budget decisions |
| `scoring/` | Immediate Blast Radius |
| `analyzers/` | Future Blast Radius plugins |
| `evidence/` | Sealed source snapshot and exact patch payload |
| `proof/` | Fresh base-plus-patch verification |
| `promotion/` | Current-host conflict check and selective apply |
| `transaction/` | Lifecycle orchestration and durable capsule |
| `recovery` | Conflict-safe local rollback |

The `0.1` flat artifacts remain readable. New `0.2` runs add structured pipeline evidence and identify `pipeline_schema_version: 2` in metadata.

## Verdict rules

`PROVEN` requires all of the following:

1. the original run completed successfully;
2. deterministic policy is `ALLOW`;
3. the sealed base source and patch are complete;
4. a fresh Docker clean room starts;
5. all configured setup/build/test argv return zero; and
6. at least one test phase actually runs.

Promotion then requires valid immutable and proof integrity, the same patch digest, and current host paths that still equal the recorded base. No model output can waive a failed condition.

## Status

- **Beta:** source/patch evidence, proof, promotion, separate risk results, Docker private workspace.
- **Experimental:** user-space live filesystem polling and the in-repository composite Action.
- **Planned:** signed evidence, stronger syscall interception, standalone `agentdiff-action@v1`.

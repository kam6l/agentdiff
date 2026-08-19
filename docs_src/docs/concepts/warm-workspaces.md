---
title: Warm workspaces
description: Immutable trusted base snapshots and private copy-on-write workspaces for every agent run.
---

# Trusted warm workspace factory

Repeated agent runs should not copy the entire repository, install
dependencies, and prepare everything from zero every time.

AgentDiff keeps **immutable trusted base snapshots** under
`.agentdiff/warm/bases/` and gives every agent a **private copy-on-write
workspace** under `.agentdiff/warm/agents/`.

## Workspace identity

A base snapshot is identified by every input that can change the meaning of
the environment:

- git/base digest (HEAD + dirty-file set)
- dependency lock digest (lockfile digests from the trust lock)
- runtime image digest
- toolchain digest (interpreter/manager versions)
- proof-plan digest

When the identity matches, an existing snapshot is reused. Any input change
produces a different identity and therefore a different (fresh) snapshot —
invalidation is automatic and content-addressed.

## Guarantees

- **No writable state sharing** between the host, the base snapshot, or other
  agents: each agent workspace is a private clone.
- **Immutable bases**: base trees are made read-only and carry a SHA-256
  manifest; a stale or tampered base is detected and rebuilt.
- **Fast reuse**: copy-on-write (reflink where the filesystem supports it,
  plain copy otherwise) makes per-agent creation cheap.
- **Pruning**: stale bases beyond the configured cap are removed
  (`agentdiff workspace prune`).

## Commands

```bash
agentdiff workspace status   # list warm base snapshots
agentdiff workspace warm     # materialize the base for the current identity
agentdiff workspace prune    # remove stale bases
```

## Integration

The wrap pipeline (`agentdiff wrap`) uses the factory automatically: the agent
runs in a private clone, proof materializes from the same base, and repair
attempts start from a fresh clone of the same base.

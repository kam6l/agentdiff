---
title: Impact-aware proof and cache
description: Run the minimum strong proof for each patch with a content-addressed, safely invalidated cache.
---

# Impact-aware proof and cache

Running the entire repository test suite for every small patch is wasteful.
AgentDiff computes the **minimum strong proof** from the impact graph and
caches deterministic results.

## Proof levels

| Level | When | What runs |
|---|---|---|
| `static` | no test commands derivable | compile / vet / type-check only |
| `targeted` | normal source change | static checks + tests covering affected modules |
| `full` | high-risk change | the complete repository proof |

High-risk changes always widen to `full`:

- dependency files (`uv.lock`, `package.json`, `go.mod`, `Cargo.lock`, …)
- CI workflows (`.github/`)
- Dockerfiles, Makefiles, CMakeLists
- build-system files (`pyproject.toml`, `nx.json`, …)
- agent instruction files (`AGENTS.md`, `CLAUDE.md`, `.codex/`, …)
- security paths (`.env*`, keys, credentials)

The decision is pure path/import classification:

```bash
agentdiff impact --paths src/auth.py     # targeted
agentdiff impact --paths uv.lock         # full
```

## Impact graph

The graph is compiled by `agentdiff bootstrap` (`.agentdiff/repo-graph.json`)
with static import analysis for Python, JavaScript/TypeScript, Go, and Rust:

```text
changed file → affected modules → affected tests → affected build targets
```

Existing project systems are integrated where present: npm/pnpm workspaces,
Nx, Bazel, Cargo workspaces, Go workspaces, uv workspaces.

## Deterministic proof cache

Proof results are cached under `.agentdiff/cache/proof` and are keyed by every
input that can influence the verdict:

- base digest (sealed pre-run source snapshot)
- patch digest (run-independent content digest of the exact mutation set)
- dependency lock digest (trust lock lockfile digests)
- runtime image digest
- proof plan digest (exact argv phases)
- target (static / targeted / full)

A cache hit is only possible when **every** input is byte-identical; any change
is a miss. Entries carry their own SHA-256 integrity manifest, and a tampered
entry is treated as a miss. Cache hits are surfaced in the proof result:

```text
Proof verdict: PROVEN
Cache:         HIT (from run 20260819T…)
```

```bash
agentdiff proof cache-status
```

## Safe optimization, not blind optimization

- High-risk changes never use a cached targeted result; they widen to `full`.
- The cache never skips integrity verification or promotion gates.
- Promotion still requires a `PROVEN` proof bound to the current run's
  immutable manifest — a cached verdict is re-sealed per run with the same
  phase digests.

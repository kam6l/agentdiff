---
title: Repository trust compiler
description: One canonical trust configuration compiled from deterministic repository inspection.
---

# Repository trust compiler

`agentdiff bootstrap` (or `agentdiff init`) inspects the repository once and
compiles **one canonical trust configuration** that becomes the single source
of truth for every agent adapter:

```text
agentdiff bootstrap
  ├─ agentdiff.yaml                 canonical policy (filesystem/process/network/limits/proof)
  ├─ .agentdiff/trust.lock          content-addressed trust identity
  ├─ .agentdiff/repo-graph.json     deterministic impact graph
  ├─ .agentdiff/proof-plan.json     proof plan (targeted + full) and high-risk triggers
  └─ .agentdiff/adapters/*.md       compiled agent instructions (CLAUDE.md, codex.md, …)
```

## What is inspected

| Category | Detection |
|---|---|
| Languages | Python, JavaScript/TypeScript, Go, Rust, Java, Ruby, C/C++, C#, Swift, Kotlin, Elixir, PHP |
| Package managers | uv, poetry, pip, npm, pnpm, yarn, bun, go, cargo, maven, gradle, bundler, composer, mix |
| Tests | pytest, tox, jest, vitest, mocha, go test, cargo test + deterministic commands |
| Builds | Makefile, Dockerfile, CMake, package scripts, nx, bazel |
| CI / ownership | `.github/workflows/*`, `CODEOWNERS` |
| Monorepo | npm/pnpm workspaces, nx, bazel, cargo workspace, go workspace |
| Agent configs | `AGENTS.md`, `CLAUDE.md`, `.codex/`, `.claude/`, `.gemini/`, `.copilot/` |
| Security paths | `.env*`, keys, credentials, `.ssh`, `.aws`, `.kube`, … |
| Lockfiles | sha256 digests for every dependency lockfile |

Everything is deterministic file inspection. No model is consulted.

## Derived policy

The compiled `agentdiff.yaml` is conservative:

- `allow_write` covers detected source/test trees;
- `review` covers dependency manifests, lockfiles, CI workflows, Dockerfiles,
  Makefiles, and agent configs;
- `deny` covers `.env*`, `.git/**`, `.ssh/**`, `.agentdiff/**`,
  `agentdiff.yaml`, keys, and credentials;
- `process.allow` covers the detected toolchain only;
- `proof` carries the deterministic setup/build/test commands and image.

## Compiled agent instructions

Instead of maintaining separate security rules for every agent, the trust
compiler emits `.agentdiff/adapters/agent-instructions.md`, `CLAUDE.md`,
`codex.md`, `gemini.md`, and `copilot.md` from the same data. `--agents`
appends a pointer section to `AGENTS.md`.

## Trust lock

`.agentdiff/trust.lock` binds the configuration to the repository state:

```json
{
  "schema_version": 1,
  "inspection_sha256": "…",
  "graph_sha256": "…",
  "proof_plan_sha256": "…",
  "policy_sha256": "…",
  "repository": {
    "git_head": "…",
    "lockfile_digests": {"uv.lock": "…"}
  }
}
```

The lock feeds the proof cache identity and the warm workspace identity, so
any relevant input change automatically invalidates caches and snapshots.

## Impact graph

`.agentdiff/repo-graph.json` is built from static import analysis (Python,
JavaScript/TypeScript, Go, Rust). It maps changed files → affected modules →
affected tests → build targets, and drives the impact-aware proof planner.

# AgentDiff project plan

## Product direction

AgentDiff is a framework-neutral runtime evidence and recovery layer:

> Independent real-state observation + deterministic intent policy + explainable blast radius + conflict-safe selective recovery.

The primary path is `agentdiff run --task "…" -- <command>`. Experimental memory and provider tools live under `agentdiff cortex`; the original snapshot, trajectory, and cleanliness evaluator is retained only as an internal compatibility import.

## Product principles

1. Evidence is captured independently of agent self-reporting.
2. Policy and scoring stay deterministic and versioned.
3. Recovery fails closed when identity, backup integrity, or post-state equality is ambiguous.
4. Safe recovery preserves allowed work.
5. Local observation is never described as sandboxing or network enforcement.
6. Evidence is redacted, bounded, and private by default.
7. Isolation, tracing, and agent protocols are integration seams, not features to rebuild.

## Current `0.2.x` surface

### Beta — trust pipeline

- No-follow filesystem manifests and private run capsules (spec v2; legacy v1 capsules remain verifiable under their original guarantees).
- Deterministic `allow`, `review`, and `deny` policy with provenance and live budget enforcement.
- Local shell-free execution with timeout, process, and port evidence; Docker runtime with a private writable workspace (never a writable host repo), cap-drop, no-new-privileges, and explicit network modes.
- Explainable, capped immediate blast-radius scoring; separate future-execution-risk analysis.
- Hybrid safety watcher: OS event hints feed dirty-path targeted checks, authoritative full reconciliation runs on schedule/overflow/force, and backend failures degrade to polling with recorded status.
- Clean-room proof: trusted verification plan from pre-run evidence, patched tests, and an independent baseline verifier (pre-run verifier files over patched product code) with deterministic proof-strength metadata (L0-L4).
- Crash-consistent promotion gate: write-ahead journal with per-entry state machine, persistent workspace lease (never-unlinked lock file), validated backup restore with digest/mode checks, and fail-closed recovery on corrupt or ambiguous state.
- Run listing, inspection, checksum verification, and exact-identity cleanup.
- Conflict-safe recovery for eligible regular files.
- Content-addressed immutable object store as the migration foundation for spec-v3 artifact references and future export/import.
- Linux, macOS, and native Windows CI on Python 3.12–3.14.

### Experimental

- Anthropic Sandbox Runtime argv adapter; enforcement belongs to the external runtime.
- Transport-neutral MCP-style pre-dispatch policy hook; no MCP server or proxy.
- LangChain callback and internal snapshot/diff/evaluator compatibility APIs.
- Five-case local recovery regression suite.

### Planned

- Published PyPI and signed release artifacts.
- Authenticated or signed evidence capsules.
- OpenTelemetry/OpenInference evidence export.
- One maintained hosted/disposable sandbox integration.
- Artifact migration and compatibility tooling.
- Larger external-state benchmark coverage.

An HTTP API, hosted dashboard, bundled sandbox, universal network blocking, and arbitrary external-state rollback are not implemented. The Docker backend implements the isolation boundary this plan targets; it is a capability-bearing container boundary, not a virtual machine.

## Release gates

### Completed for the current source release

- [x] Tests on Linux, macOS, and Windows.
- [x] Ruff formatting/lint, mypy, CodeQL, Bandit, and dependency audit.
- [x] Package build and clean-wheel smoke test.
- [x] Strict docs build plus internal link and asset validation.
- [x] Deterministic local recovery regression artifact.
- [x] Protected `main`, least-privilege workflow permissions, secret scanning, and Dependabot configuration.

### Required before a stable release

- [ ] Versioned policy and artifact migration strategy.
- [ ] Documented compatibility and deprecation policy.
- [ ] Independent security review of scanning, persistence, process handling, and recovery.
- [ ] Published-package ownership and provenance.
- [ ] Measured performance bounds on representative repositories.
- [ ] No documentation claim beyond tested behavior.

## Focused roadmap

### Credibility and distribution

1. Publish signed artifacts through PyPI Trusted Publishing after ownership and provenance are configured.
2. Keep the primary CLI limited to transaction, evidence, recovery, policy, and diagnostics.
3. Keep Cortex experimental, namespaced, and described as deterministic evidence tooling without autonomy claims.
4. Ship a thin GitHub Action that reports transaction evidence without creating a proprietary dashboard.

### Differentiated safety core

1. [x] Clean-room proof replays the captured patch in a fresh environment before promotion.
2. [x] Future execution risk analysis covers package scripts, GitHub Actions, Dockerfiles, Makefiles, hooks, and editor tasks.
3. [x] Docker runtime materializes a private workspace and the real repository is changed only by an explicit, policy-filtered promotion step.
4. Harden verifier independence further: external signed CI verification (proof strength L4) and verifier-file policy controls.

### Evidence moat

1. Add signed (authenticated) capsule support; current checksums are tamper-evident, not authenticated.
2. Add shareable capsule export/import (the CAS object store is the hydration foundation).
3. Add run attribution for changed lines and evidence-based comparison of parallel agent attempts.
4. Keep adversarial race, path, hardlink, redaction, promotion-crash, and rollback tests ahead of new claims.

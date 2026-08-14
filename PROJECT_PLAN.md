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

## Current `0.1.0` surface

### Beta

- No-follow filesystem manifests and private run capsules.
- Deterministic `allow`, `review`, and `deny` policy with provenance.
- Local shell-free command execution with timeout and best-effort process evidence.
- Explainable, capped blast-radius scoring.
- Run listing, inspection, checksum verification, and exact-identity cleanup.
- Conflict-safe recovery for eligible regular files.
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

An HTTP API, hosted dashboard, Docker backend, bundled sandbox, universal network blocking, and arbitrary external-state rollback are not implemented.

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

1. Add clean-room proof by replaying a captured patch in a fresh worktree before promotion.
2. Detect future execution risk in package scripts and GitHub Actions changes, then extend to Dockerfiles, Makefiles, hooks, and editor tasks.
3. Add an experimental copy-on-write Docker runtime where the real repository is changed only by an explicit, policy-filtered promotion step.

### Evidence moat

1. Add signed, shareable capsule export and standardized telemetry.
2. Add run attribution for changed lines and evidence-based comparison of parallel agent attempts.
3. Keep adversarial race, path, hardlink, redaction, and rollback tests ahead of new claims.

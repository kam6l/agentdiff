# AgentDiff project plan

## Product direction

AgentDiff is a framework-neutral runtime evidence and recovery layer:

> Independent real-state observation + deterministic intent policy + explainable blast radius + conflict-safe selective recovery.

The primary path is `agentdiff run --task "…" -- <command>`. The original snapshot, trajectory, and cleanliness evaluator remains available as an experimental compatibility surface.

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
- LangChain callback and the original snapshot/diff/evaluator APIs.
- Five-case local adversarial benchmark.

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
- [x] Deterministic Local SafetyBench artifact.
- [x] Protected `main`, least-privilege workflow permissions, secret scanning, and Dependabot configuration.

### Required before a stable release

- [ ] Versioned policy and artifact migration strategy.
- [ ] Documented compatibility and deprecation policy.
- [ ] Independent security review of scanning, persistence, process handling, and recovery.
- [ ] Published-package ownership and provenance.
- [ ] Measured performance bounds on representative repositories.
- [ ] No documentation claim beyond tested behavior.

## Highest-value contribution areas

1. Adversarial race, path, hardlink, redaction, and rollback tests.
2. Authenticated capsule format and migrations.
3. Measured large-repository scan performance.
4. A maintained sandbox integration with explicit guarantee mapping.
5. Standardized evidence export rather than a proprietary dashboard.

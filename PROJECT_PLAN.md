# AgentDiff project plan

## Product direction

AgentDiff is becoming a framework-neutral runtime evidence and recovery layer for autonomous agents. Its first production-shaped wedge is deliberately local and narrow:

> Wrap an arbitrary command, record what it changed, apply deterministic mutation policy, explain the blast radius, preserve evidence, and selectively recover eligible collateral file changes.

AgentDiff remains an evaluator as well: the original snapshot, trajectory, cleanliness, and side-effect APIs stay available for compatibility.

## Product principles

1. **Evidence before claims.** “Observed,” “intercepted,” “blocked,” “sandboxed,” and “rolled back” are distinct capabilities.
2. **Deterministic enforcement core.** Versioned policy and scoring do not depend on an LLM.
3. **Fail closed on destructive ambiguity.** Recovery preserves a current path when identity, backup integrity, or post-run equality cannot be established.
4. **Preserve intended work.** Safe-only rollback targets `review` and `deny` mutations rather than resetting the whole workspace.
5. **Local-first, backend-neutral.** The initial backend is an honest local subprocess runner, not a pretend sandbox.
6. **Private evidence by default.** Redaction, restrictive permissions, bounded capture, and terminal-safe display are part of correctness.
7. **Integrate rather than clone.** Isolation, observability, agent protocols, and external-state benchmarks should use maintained ecosystem boundaries.

## Current implementation

### Legacy evaluation core

- SHA-256 filesystem snapshots and semantic diffs.
- Fingerprinted environment observations with secret-like names excluded.
- Machine-wide PID and listening-port set observations.
- Trajectory steps, tool calls, failures, durations, loops, and token accounting.
- Cleanliness and efficiency metrics with side-effect classification.
- Framework-neutral sessions and an optional LangChain/LangGraph callback.
- `snapshot`, `diff`, and `eval` CLI workflows.

### Runtime transaction core (unreleased)

- No-follow filesystem manifests with bounded hashing and backups.
- Private, versioned `.agentdiff/runs/<run-id>/` capsules.
- SHA-256 capsule integrity manifests with explicit unauthenticated-tamper caveats.
- Strict policy schema with `allow`, `review`, and `deny` decisions.
- Rule provenance and explain commands.
- Local subprocess execution with timeout and process-identity evidence.
- Optional external Anthropic Sandbox Runtime delegation; no bundled sandbox implementation.
- Conservative cleanup using PID plus process creation time.
- Machine-wide port observation labeled as non-attributed.
- Explainable, configurable, capped blast-radius scoring.
- Run listing and inspection.
- Conflict-aware selective regular-file rollback.
- Central command, payload, environment, and terminal redaction.
- Transport-neutral MCP-style policy hook; no MCP proxy/server.

## Explicit non-goals for the local MVP

- Claiming local subprocesses are sandboxed.
- Universal network blocking.
- Complete process-tree provenance.
- Port ownership or causal attribution.
- Recovery of arbitrary external APIs, databases, cloud resources, or Git remotes.
- Recovery of symlinks, hardlinks, special files, or uncaptured oversized files.
- LLM decisions in the trusted enforcement path.
- A hosted dashboard or telemetry service.
- Broad first-class framework adapters without executable integration tests.

## Delivery roadmap

### v0.1 — evaluation core

- Snapshot/diff engine.
- Trajectory tracker.
- Cleanliness evaluator.
- CLI and Python API.
- LangChain callback.

### v0.2 — local runtime evidence and recovery

- [x] Secure transaction manifests and run capsules.
- [x] Deterministic policy loading and explanation.
- [x] Explainable blast-radius scoring.
- [x] Local command runtime and honest doctor report.
- [x] Process identity checks and conservative cleanup.
- [x] Run inspection.
- [x] Conflict-safe selective rollback.
- [x] CLI vertical slice and Python API.
- [x] Generic MCP-style pre-dispatch policy hook.
- [x] Optional Anthropic Sandbox Runtime adapter with tested argv/CLI contract.
- [ ] Cross-platform CI evidence on Linux, macOS, and Windows.
- [ ] Security/static/dependency quality gates.
- [x] Deterministic five-case Local SafetyBench scenario suite and JSON baseline.
- [ ] Final documentation, package, and release validation.

### Later — isolated backends and ecosystem seams

Candidates must be implemented and tested before they are advertised:

- one maintained sandbox backend (for example, E2B or another provider selected after evaluation);
- OpenTelemetry/OpenInference evidence export;
- an agent protocol integration such as ACP/OpenHands;
- external-state scenarios compatible with Agent Diff Bench;
- policy-aware interception adapters at tool transport boundaries;
- reproduction capsules with declared portability and provenance;
- richer causal attribution where the backend can actually supply it.

### Stable release criteria

- Versioned policy and artifact migration strategy.
- Tested Linux, macOS, and native Windows behavior.
- Documented compatibility and deprecation policy.
- Independent security review of scanning, persistence, process handling, and rollback.
- Published package ownership and provenance.
- Measured performance bounds on representative repositories.
- No known documentation claims that exceed tested behavior.

## Naming decision

“AgentDiff” has material project and search collisions. The exact PyPI and npm package endpoints were unoccupied when checked on 2026-08-10, but registry availability is not legal clearance and does not solve discoverability.

The repository will use the descriptor **AgentDiff Runtime** while the v0.2 work is evaluated. A final product/package name should be chosen deliberately before the first stable schema or public package release. See `docs_src/project/naming-analysis.md`.

## Contribution priorities

High-value contributions are:

1. adversarial path, symlink, hardlink, race, redaction, and rollback tests;
2. native Windows and macOS validation;
3. additional reproducible SafetyBench scenarios with clear expected side effects;
4. one deeply tested isolation backend;
5. artifact migration and schema compatibility tooling;
6. audited integration hooks at real command/tool dispatch boundaries.

Avoid placeholder adapters, invented comparison claims, or roadmap features exposed as empty CLI commands.

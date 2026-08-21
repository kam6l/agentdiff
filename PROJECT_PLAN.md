# AgentDiff project plan

## Product direction

**AgentDiff is the trust layer for self-maintaining APIs.**

When an API changes, AgentDiff finds affected customer code, generates or supervises the migration, independently proves the patch in a clean room, and opens a reviewable PR with a cryptographic Migration Certificate.

The trust engine underneath — independent real-state observation, deterministic policy, explainable blast radius, conflict-safe promotion, bounded repair, evidence capsules — is what makes verified migrations possible. The coding-agent automation (`agentdiff wrap`) is a powerful byproduct of the same infrastructure.

> Independent real-state observation + deterministic intent policy + explainable blast radius + conflict-safe selective recovery.

The primary product wedge is `agentdiff api scan/check/migrate` for Self-Maintaining APIs. The primary automation path is `agentdiff wrap -- <agent>` for zero-touch coding-agent trust.

## Product principles

1. Evidence is captured independently of agent self-reporting.
2. Policy and scoring stay deterministic and versioned.
3. Recovery fails closed when identity, backup integrity, or post-state equality is ambiguous.
4. Safe recovery preserves allowed work.
5. Local observation is never described as sandboxing or network enforcement.
6. Evidence is redacted, bounded, and private by default.
7. Isolation, tracing, and agent protocols are integration seams, not features to rebuild.
8. **The AI generates; AgentDiff verifies.** Probabilistic code generation is untrusted until deterministic proof passes.

## Current `0.3.0` surface (main branch)

### Beta

- No-follow filesystem manifests and private run capsules.
- Deterministic `allow`, `review`, and `deny` policy with provenance.
- Local shell-free command execution with timeout and best-effort process evidence.
- Explainable, capped blast-radius scoring.
- Run listing, inspection, checksum verification, and exact-identity cleanup.
- Conflict-safe recovery for eligible regular files.
- Linux, macOS, and native Windows CI on Python 3.12–3.13.
- **Self-Maintaining APIs: AST scanner, SDK version detector, breaking-change matcher, blast radius integration, `agentdiff api scan/check`**

### Experimental

- Anthropic Sandbox Runtime argv adapter; enforcement belongs to the external runtime.
- Transport-neutral MCP-style pre-dispatch policy hook; no MCP server or proxy.
- LangChain callback and internal snapshot/diff/evaluator compatibility APIs.
- Five-case local recovery regression suite.
- Cortex evidence memory and provider routing.

### Planned

- Published PyPI and signed release artifacts.
- Authenticated or signed evidence capsules.
- OpenTelemetry/OpenInference evidence export.
- One maintained hosted/disposable sandbox integration.
- Artifact migration and compatibility tooling.
- Larger external-state benchmark coverage.
- **Migration pipeline completion: real ProofEngine execution for migrations, rollback verification, failure evidence, GitHub PR delivery**

An HTTP API, hosted dashboard, Docker backend, bundled sandbox, universal network blocking, and arbitrary external-state rollback are not implemented.

## Release gates

### Completed for the current source release

- [x] Tests on Linux, macOS, and Windows.
- [x] Ruff formatting/lint, mypy, CodeQL, Bandit, and dependency audit.
- [x] Package build and clean-wheel smoke test.
- [x] Strict docs build plus internal link and asset validation.
- [x] Deterministic local recovery regression artifact.
- [x] Protected `main`, least-privilege workflow permissions, secret scanning, and Dependabot configuration.
- [x] CI on stable Python 3.12, 3.13 (3.14 tracked separately).

### Required before a stable release

- [ ] Versioned policy and artifact migration strategy.
- [ ] Documented compatibility and deprecation policy.
- [ ] Independent security review of scanning, persistence, process handling, and recovery.
- [ ] Published-package ownership and provenance.
- [ ] Measured performance bounds on representative repositories.
- [ ] No documentation claim beyond tested behavior.
- [ ] **Self-Maintaining APIs MVP: one real provider change, one affected repo, one verified migration PR**

## Focused roadmap

### Self-Maintaining APIs (primary wedge)

1. **API Change Manifest** — structured machine-readable upstream change format (YAML/JSON) for provider deprecations, SDK releases, model shutdowns. *(implemented)*
2. **Deterministic AST Transforms** — for known simple migrations (OpenAI Responses API, Stripe PaymentIntents, etc.); registry extensible by providers. *(implemented)*
3. **Migration Engine** — scan → match → plan → transform in private workspace → verify → certificate. *(implemented)*
4. **Provider Intelligence Layer** — parse changelogs, diff OpenAPI specs, analyze SDK releases, and accept AI suggestions as validated manifest candidates. AI output never touches code directly. *(implemented)*
5. **Provider Plugin System** — `agentdiff provider install/list`; providers ship `manifests/`, `transforms/`, `tests/`, `metadata.yaml` without core changes. *(implemented)*
6. **Verification Levels (V0–V5)** — syntax/type/build → targeted tests → full repo tests → API contract/mock tests → user-defined integration verification.
7. **Migration Certificate** — machine-readable artifact: provider change, affected usages, files changed, blast radius, policy result, tests executed, verification level, proof digest, capsule ID, rollback info. *(implemented)*
8. **GitHub PR Automation** — `--open-pr` delivers Migration Certificate in PR body; conflict-safe promotion; no auto-merge.
9. **API Knowledge Graph** — track Repository → API usage → SDK version → migration status; design scalable, no extra database yet.

### Credibility and distribution

1. Publish signed artifacts through PyPI Trusted Publishing after ownership and provenance are configured.
2. Keep the primary CLI limited to transaction, evidence, recovery, policy, diagnostics, and API migration.
3. Keep Cortex experimental, namespaced, and described as deterministic evidence tooling without autonomy claims.
4. Ship a thin GitHub Action that reports transaction evidence without creating a proprietary dashboard.

### Differentiated safety core

1. Clean-room proof by replaying a captured patch in a fresh worktree before promotion (implemented).
2. Detect future execution risk in package scripts and GitHub Actions changes, then extend to Dockerfiles, Makefiles, hooks, and editor tasks.
3. Experimental copy-on-write Docker runtime where the real repository is changed only by an explicit, policy-filtered promotion step.

### Evidence moat

1. Add signed, shareable capsule export and standardized telemetry.
2. Add run attribution for changed lines and evidence-based comparison of parallel agent attempts.
3. Keep adversarial race, path, hardlink, redaction, and rollback tests ahead of new claims.
4. **Migration Certificate as interoperability format** — providers can require it, customers can audit it, regulators can accept it.
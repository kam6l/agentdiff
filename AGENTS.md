# AgentDiff contributor map

AgentDiff is a deterministic trust layer around software-maintenance workers. A worker may propose code; only AgentDiff policy and proof may authorize the exact patch.

Read these short documents before changing behavior:

- [`docs/engineering/PRODUCT.md`](docs/engineering/PRODUCT.md) — product promise, scope, and capability labels.
- [`docs/engineering/ARCHITECTURE.md`](docs/engineering/ARCHITECTURE.md) — component and evidence flow.
- [`docs/engineering/SECURITY_INVARIANTS.md`](docs/engineering/SECURITY_INVARIANTS.md) — non-negotiable trust boundaries.
- [`docs/engineering/IMPLEMENTATION_STATUS.md`](docs/engineering/IMPLEMENTATION_STATUS.md) — what is available, foundational, or roadmap.
- [`docs/engineering/DEVELOPMENT.md`](docs/engineering/DEVELOPMENT.md) and [`TESTING.md`](docs/engineering/TESTING.md) — local workflow and release gates.
- [`docs/engineering/DESIGN_SYSTEM.md`](docs/engineering/DESIGN_SYSTEM.md) — website language and visual rules.

Repository map:

- `src/agentdiff/api/`: provider discovery, scan, migration, certificates, campaigns, and sealed PR delivery.
- `src/agentdiff/proof/`: authoritative clean-room proof plus composable proof-strength primitives.
- `src/agentdiff/maintenance/`: generic change, provenance graph, priority, and scheduling foundations.
- `src/agentdiff/runtime/`, `transaction/`, `policy/`, `evidence/`: execution observation and deterministic evidence core.
- `src/agentdiff/delivery/`, `outcome/`, `minimize/`, `repair/`: bounded lifecycle components.
- User-facing website and documentation are maintained in the private `agentdiff-web` repository and deployed separately to GitHub Pages.
- `demos/`: reproducible fixtures; never replace their output with invented success data.

Hard rules:

1. Remote content and generator output are untrusted.
2. The local runtime is observation, not a sandbox.
3. Custom generators fail closed when isolated execution is unavailable; never fall back to host execution.
4. Proof binds the exact base, patch, policy, plan, runtime, and evidence. Do not restamp or regenerate during delivery.
5. Incomplete, flaky, stale, or ambiguous evidence is not proof.
6. Do not add auto-merge, model self-approval, home-grown cryptography, hidden telemetry, fake metrics, or default production rollback.

Use a `codex/` branch, preserve unrelated work, add refusal-path tests for security changes, and run the checks in `docs/engineering/TESTING.md` before handoff.

# Changelog

AgentDiff is pre-release software. APIs and artifact schemas may change before the first stable release.

## 0.2.0

### Added

- **Proof Trust Provenance (P0 Security)**: Base-snapshot verification plan auto-discovery with deterministic tamper rejection when patches modify build or test configuration files (`package.json`, `pyproject.toml`, `conftest.py`, `Makefile`, etc.) without an explicit policy override.
- **Crash-Consistent Promotion Gate**: Multi-file promotion with advisory workspace lease locking (`WorkspaceLease`), write-ahead transaction logging (`PromotionJournal`), two-phase staging with `fsync` validation (`PromotionStager`), and automatic crash recovery (`PromotionRecovery`).
- **Policy Schema v2**: Added first-class `proof:` section supporting container image, network mode, setup, build, and test command sequences.
- **Capsule Spec v2 & Merkle Validation**: Structured integrity manifests, content-addressed blob references, deterministic Merkle root hashing, and backward compatibility with v1 flat capsules.
- **Hybrid Safety Watcher**: Blends filesystem notification hints with deterministic snapshot validation and budget enforcement.
- **High-Speed Workspace Materializer**: Fast copy-on-write / reflink / copy directory materializer for isolated container workspaces.

### Changed

- Deprecated legacy prototype modules (`agentdiff.diff_engine`, `agentdiff.evaluator`, `agentdiff.trajectory`) with `DeprecationWarning` notices pointing to `agentdiff.state`, `agentdiff.scoring`, `agentdiff.analyzers`, and `agentdiff.transaction`.
- Exported all core Trust Pipeline engines directly in top-level `agentdiff` namespace.

## 0.1.0

### Changed

- Renamed the public Cortex repair surface to `RemediationAdvisor` and `agentdiff cortex advise`; it produces advice and never claims to execute healing.
- Reframed deterministic skill output as evidence-backed skill cards, grouped all optional Cortex commands under `agentdiff cortex`, and removed legacy evaluator verbs from the public CLI.
- Replaced the simulated legacy evaluator demo with a real subprocess executed through `AgentRunTransaction`.
- Renamed the five-case public CI check to the local recovery regression suite.
- Prevented documentation search results from expanding full pages inside the command palette, standardized responsive tables and text rendering, and compacted article/footer spacing.
- Rebuilt documentation search as a responsive command palette with keyboard navigation, corrected result styling, and reliable index updates.
- Added an E2B-inspired GitHub repository badge with a current star count and reduced excess spacing before documentation footers.
- Replaced nonexistent HTTP-server and SDK documentation with implemented Python and capsule references.
- Corrected integration guides to match the tested Sandbox Runtime adapter, MCP policy hook, LangChain callback, and transaction API.
- Updated installation, README, project plan, examples, CLI output, and website copy to describe version `0.1.0` consistently.
- Expanded CI across Linux, macOS, and Windows on the supported Python range.
- Upgraded artifact and GitHub Pages actions to their Node 24-capable releases.

### Security

- Kept workflows least-privilege and third-party actions pinned to commit SHAs.
- Added Dependency Review to protected pull-request checks and enabled its required repository security settings.
- Preserved conflict checks, backup verification, no-follow capture, redaction, and exact process identity checks.

## 0.1.0

The source release includes local command transactions, deterministic mutation policy, explainable blast-radius scoring, durable run capsules, conflict-safe regular-file recovery, and the original trajectory evaluator compatibility APIs.

The local runtime is not a sandbox, does not block networking, and cannot recover external APIs, databases, cloud resources, network effects, symlinks, hardlinks, or unbacked files.

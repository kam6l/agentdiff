# Changelog

AgentDiff is pre-release software. APIs and artifact schemas may change before the first stable release.

## 0.2.1

### Security

- **Promotion crash window closed**: every filesystem mutation is now preceded by a persisted `APPLY_INTENT` journal entry and followed by post-state verification and a persisted `APPLIED` entry. Recovery distinguishes "mutation occurred", "mutation did not occur", and "ambiguous" by comparing current host state to the recorded base/result, and fails closed on ambiguity.
- **Workspace lease inode race fixed**: `promotion.lock` is a persistent lock file that is never unlinked; only the OS-level advisory lock (flock / msvcrt) is released, so concurrent AgentDiff promotions cannot both hold the lease.
- **Corrupt journal fails closed**: journal loading returns explicit `NO_JOURNAL` / `VALID_JOURNAL` / `CORRUPT_JOURNAL` outcomes; a corrupt journal blocks promotion instead of reading as "no journal". Legacy schema-2 journals remain recoverable under their old semantics.
- **Recovery path/digest hardening**: journal paths are validated (normalized, below root and the approved backup directory, no symlink parents, no AgentDiff-internal targets); backups are re-verified by SHA-256/size and opened identity before restore; restore writes through an fsynced temp and restores content plus mode. Legacy "applied: bool" journals map onto the new state machine.
- **Verifier independence (proof)**: proof now runs a baseline verification that restores the sealed pre-run verifier files over the patched product code, so agent-modified tests cannot silently weaken the verifier; PROVEN fails closed when verifier-related files were modified and the baseline cannot confirm.
- **Proof-strength metadata**: deterministic L0-L4 levels with WEAK/REVIEW/STRONG labels and verifier-independence ratings; the PROVEN/NOT_PROVEN verdict remains deterministic.
- **Terminology corrections**: `copy_file_range` is no longer described as a guaranteed reflink (CLONE = FICLONE only when supported, FAST_COPY = accelerated copy, STREAM_COPY = fallback); the capsule aggregate digest is renamed Capsule Root Digest, not "Merkle root".
- **Materializer mode preservation**: the executable bit and file modes are preserved on every copy strategy; symlinks, hardlinks, and special files are rejected instead of silently dropped; O_NOFOLLOW identity checks prevent source substitution.
- **Runtime capabilities**: explicit static `RuntimeCapabilities` (filesystem/network/process/privilege control levels, private workspace, live safety, source snapshot support) replace `hasattr`/`getattr` string sniffing before execution.
- **Hybrid safety watcher integrated**: OS event hints feed dirty-path targeted checks with periodic authoritative full reconciliation; backend failures degrade to polling with recorded status; final after-state always comes from an authoritative capture.
- **Capsule v1/v2 separation**: `verify_integrity` routes by capsule version; legacy v1 capsules verify under their original guarantees, and a schema-2 mirror without the structured manifest fails closed.
- **Content-addressed object store**: immutable `ObjectStore` (`.agentdiff/objects`) with write-once semantics, digest-validated paths, and fail-closed reads; capsule layout (spec v2) is unchanged, with the object store as the incremental spec-v3/export foundation.

### Changed

- `RuntimeBackend` protocol gains `capabilities`, `configure_source`, `configure_safety`, and `close`; all runtimes implement them.
- `WorkspaceMaterializer` strategies renamed (`CLONE`/`FAST_COPY`/`STREAM_COPY`; `REFLINK`/`COPY` retained as aliases) and reports the strategy actually used.
- Docker runtime materializes the private workspace through `WorkspaceMaterializer` and records materialization evidence in `runtime.json`.
- `agentdiff inspect` and proof JSON now include proof-strength, baseline-verifier, and watcher evidence.

### Tests

- Added adversarial promotion fault-injection coverage: corrupt/malformed journals, traversal, backup symlink/hardlink, crash at every write-ahead transition, mode restoration, ambiguous recovery, legacy journal recovery, cross-process lease exclusion.
- Added proof-strength matrix, verifier-mutation classifier, baseline overlay end-to-end, and tamper-blocking tests.
- Added materializer security tests (mode preservation per strategy, symlink/hardlink/special-file rejection, target symlink), capsule v1/v2 verification tests, CAS object-store tests, and hybrid watcher degradation/overflow tests.

## 0.2.0

### Added

- **Proof Trust Provenance (P0 Security)**: Base-snapshot verification plan auto-discovery with deterministic tamper rejection when patches modify build or test configuration files (`package.json`, `pyproject.toml`, `conftest.py`, `Makefile`, etc.) without an explicit policy override.
- **Crash-Consistent Promotion Gate**: Multi-file promotion with advisory workspace lease locking (`WorkspaceLease`), write-ahead transaction logging (`PromotionJournal`), two-phase staging with `fsync` validation (`PromotionStager`), and automatic crash recovery (`PromotionRecovery`).
- **Policy Schema v2**: Added first-class `proof:` section supporting container image, network mode, setup, build, and test command sequences.
- **Capsule Spec v2**: Structured integrity manifests, blob references, a deterministic Capsule Root Digest (flat aggregate — not a Merkle tree), and backward compatibility with v1 flat capsules.
- **Hybrid Safety Watcher**: Blends filesystem notification hints with deterministic snapshot validation and budget enforcement.
- **High-Speed Workspace Materializer**: Fast clone (FICLONE where supported) / accelerated copy / streaming directory materializer for isolated container workspaces.

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

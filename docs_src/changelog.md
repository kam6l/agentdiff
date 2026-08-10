# Changelog

Notable changes are documented here. AgentDiff is pre-release software; APIs and artifact schemas may change before the first published package release.

## Unreleased

### Added — runtime safety and recovery

- `agentdiff run` for shell-free local command transactions.
- `runs`, `inspect`, `rollback`, `cleanup`, and `doctor` CLI workflows.
- Version-1 YAML/JSON policy with strict validation and explainable rule provenance.
- Deterministic allow/review/deny decisions for filesystem paths and executables.
- No-follow filesystem manifests with bounded hashing and recoverable before-state capture.
- Private, versioned local run capsules under `.agentdiff/runs/`.
- Explainable and configurable 0–100 blast-radius scoring.
- Local subprocess timeout, observed-descendant identity evidence, and conservative cleanup.
- Optional Anthropic Sandbox Runtime delegation with explicit backend and enforcement evidence.
- Machine-wide listening-port observations explicitly marked as non-attributed.
- Conflict-safe selective rollback for eligible regular-file creations, modifications, and deletions.
- Run inspection and list APIs.
- SHA-256 capsule integrity manifests and `agentdiff verify`.
- Transport-neutral MCP-style pre-dispatch policy hook.
- Central command, nested-payload, environment, and terminal redaction utilities.
- Runtime, policy, scoring, recovery, security, competitive-analysis, and naming documentation.
- A deterministic five-case Local SafetyBench and CI artifact.

### Changed

- Environment observations now persist stable fingerprints rather than raw values.
- Legacy filesystem hashing uses no-follow opens where supported and rejects common replacement races.
- AgentDiff's primary positioning now emphasizes runtime evidence, deterministic mutation boundaries, and selective recovery while preserving evaluator compatibility.
- CLI help and docs distinguish local observation from sandboxing, network enforcement, process ownership, and port attribution.
- The canonical rollback size key is `max_backup_file_mb`; the initial unreleased `backup_max_file_mb` spelling is accepted as a compatibility alias.

### Security

- Filesystem scanning avoids symlink traversal and validates root-relative paths.
- Rollback requires current state to equal the recorded post-run state.
- Backup hashes are verified before restoration.
- Hardlinks, symlink surprises, path escapes, unsupported objects, corrupted backups, and ambiguous process identities fail closed.
- Command metadata and event payloads are redacted before persistence.
- Run directories and files request restrictive POSIX permissions.

### Limitations

- The local backend is not a sandbox and does not block networking.
- Port snapshots are machine-wide observations without causal attribution.
- Process-tree capture is best effort.
- Rollback does not cover symlinks, hardlinks, special files, oversized/unbacked files, external APIs, databases, cloud effects, or network traffic.

## 0.1.0

The initial source release includes filesystem and system-state snapshots, semantic diffs, trajectory recording, cleanliness and efficiency metrics, side-effect classification, a CLI, and a Python API.

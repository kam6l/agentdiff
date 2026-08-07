# Changelog

Notable changes are documented here. AgentDiff is pre-release software; APIs may still change before the first published package release.

## Unreleased

### Added

- Responsive AgentDiff documentation and product site.
- Framework-neutral `AgentDiffSession` lifecycle.
- Tested optional LangChain callback integration.
- Explicit CI gating through `--fail-on-failure`.
- Environment-variable deny patterns for secret-like names.
- Capture controls for environment variables, processes, and ports.
- Regression coverage for CLI snapshot round trips and JSON output.

### Changed

- Runtime, development, documentation, and build dependencies are separated.
- Relative intended targets resolve against the configured root in sessions and CLI evaluation.
- CLI help lists only implemented commands.
- Snapshot artifacts under `.agentdiff` are ignored by default.
- Project ownership and links use `kam6l/agentdiff`.

### Fixed

- Nested snapshots deserialize correctly for `diff` and `eval`.
- JSON diff output uses the domain model's serializer.
- Configured cleanliness thresholds now affect pass/fail decisions.
- `TrajectoryTracker.track_tool()` now retains results supplied by its setter.
- Snapshot disable flags now control their collectors.

### Security

- Secret-like environment variables are excluded from snapshots by default.

## 0.1.0

The initial source release includes filesystem and system-state snapshots, semantic diffs, trajectory recording, cleanliness and efficiency metrics, side-effect classification, a CLI, and a Python API.

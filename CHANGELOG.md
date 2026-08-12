# Changelog

AgentDiff is pre-release software. APIs and artifact schemas may change before the first stable release.

## Unreleased

### Added

- Outcome-first CLI summaries with expected, unexpected, and protected mutation counts.
- `python -m agentdiff` as a conventional CLI entry point.
- Python 3.12 and 3.13 support alongside Python 3.14.
- Built-site validation for internal links, anchors, scripts, stylesheets, and images.
- Explicit Beta, Experimental, and Planned feature labels.

### Changed

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

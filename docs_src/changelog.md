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

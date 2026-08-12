<p align="center">
  <a href="https://kam6l.github.io/agentdiff/">
    <img src="docs_src/assets/images/favicon.svg" width="72" alt="AgentDiff logo">
  </a>
</p>

<h1 align="center">AgentDiff</h1>

<p align="center">
  <strong>See what the agent changed. Undo only the collateral.</strong><br>
  Independent state observation, deterministic intent policy, explainable blast radius, and conflict-safe selective recovery for AI-agent commands.
</p>

<p align="center">
  <a href="https://github.com/kam6l/agentdiff/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/kam6l/agentdiff/ci.yml?branch=main&style=flat-square&label=CI"></a>
  <a href="https://github.com/kam6l/agentdiff/actions/workflows/deploy.yml"><img alt="Documentation deployment" src="https://img.shields.io/github/actions/workflow/status/kam6l/agentdiff/deploy.yml?branch=main&style=flat-square&label=docs"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/Python-3.12%2B-171916?style=flat-square&logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-f06a3c?style=flat-square"></a>
</p>

<p align="center">
  <a href="https://kam6l.github.io/agentdiff/"><strong>Website</strong></a> |
  <a href="https://kam6l.github.io/agentdiff/docs/"><strong>Documentation</strong></a> |
  <a href="https://kam6l.github.io/agentdiff/docs/quickstart/"><strong>Quickstart</strong></a> |
  <a href="https://kam6l.github.io/agentdiff/docs/trust/"><strong>Trust model</strong></a>
</p>

<p align="center">
  <a href="https://kam6l.github.io/agentdiff/">
    <img src="docs_src/assets/images/agentdiff-landing.png" alt="AgentDiff site showing a classified local transaction and blast-radius score" width="100%">
  </a>
</p>

> [!IMPORTANT]
> The local runtime observes a host subprocess; it is not a kernel sandbox and does not block network access. Recovery covers only eligible filesystem changes. Use a real isolation backend for untrusted code.

## Why install it?

A command can exit successfully while leaving one intended edit, one dependency change, and one protected secret file. AgentDiff records the real workspace state independently of the agent, classifies every mutation with deterministic policy, explains the risk score, and can recover eligible collateral without resetting allowed work.

## Start in under a minute

AgentDiff `0.1.0` requires Python 3.12+ and is currently installed from source:

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv tool install .
```

From the project you want to observe:

```bash
agentdiff policy init
agentdiff run --task "Fix authentication" -- codex
```

The summary leads with the decision you need:

```text
Task completed

Expected changes:   4
Unexpected changes: 3
Protected changes:  1

Blast Radius: HIGH (72/100)
Recovery available: YES
Policy outcome: DENY
```

Then inspect the durable capsule or recover unchanged collateral:

```bash
agentdiff inspect <run-id>
agentdiff verify <run-id>
agentdiff rollback <run-id> --safe-only
```

[Run the reproducible five-minute example](https://kam6l.github.io/agentdiff/docs/quickstart/)

## How it works

| Stage | Result |
|---|---|
| **Capture** | No-follow before-state manifest and bounded recovery backups |
| **Execute** | Exact argv, exit status, owned-process evidence, and machine-wide port observations |
| **Evaluate** | `allow` / `review` / `deny` decisions, rule provenance, warnings, and a 0-100 score |
| **Recover** | Exact post-state conflict checks before eligible collateral is changed |

## Feature status

| Status | Surface |
|---|---|
| **Beta** | Local transactions, policy, capsules, verification, scoring, and regular-file recovery (tested on Python 3.12-3.14) |
| **Experimental** | Anthropic `srt` adapter, transport-neutral MCP policy hook, LangChain callback, legacy evaluator |
| **Planned** | PyPI/binary releases, authenticated evidence, telemetry export, and a maintained hosted sandbox integration |

There is no HTTP server, hosted dashboard, Docker backend, bundled sandbox, or claimed PyPI release today.

## CLI

| Command | Purpose |
|---|---|
| `agentdiff run -- <cmd>` | Wrap an explicit argv in a transaction |
| `agentdiff runs` / `inspect` / `verify` | Find and validate local evidence capsules |
| `agentdiff rollback <id> --safe-only` | Recover eligible `review` and `deny` changes |
| `agentdiff cleanup <id>` | Signal exact PID/create-time identities recorded for a run |
| `agentdiff doctor` | Report implemented capabilities and limits |
| `agentdiff policy init/validate/explain` | Create and inspect versioned policy |

The compatibility commands `snapshot`, `diff`, and `eval` remain available but are not the primary product path.

## Trust boundary

AgentDiff records symlinks without traversing them, redacts common secret-bearing values, verifies backups and capsule checksums, and identifies processes by PID plus creation time. It does **not** authenticate a capsule against an attacker who can replace the whole directory, attribute machine-wide port changes to one process, or undo APIs, databases, network effects, hardlinks, symlinks, and unbacked files.

Read the [runtime model](https://kam6l.github.io/agentdiff/docs/concepts/runtime/), [recovery guarantees](https://kam6l.github.io/agentdiff/docs/concepts/recovery/), and [security limits](https://kam6l.github.io/agentdiff/docs/trust/).

<p align="center">
  <a href="https://kam6l.github.io/agentdiff/docs/cli/">
    <img src="docs_src/assets/images/agentdiff-docs.png" alt="AgentDiff CLI documentation" width="100%">
  </a>
</p>

AgentDiff is MIT-licensed beta software. [Security](SECURITY.md) | [Contributing](CONTRIBUTING.md) | [Changelog](CHANGELOG.md) | [Issues](https://github.com/kam6l/agentdiff/issues)

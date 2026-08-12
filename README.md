<p align="center">
  <a href="https://kam6l.github.io/agentdiff/">
    <img src="docs_src/assets/images/favicon.svg" width="72" alt="AgentDiff logo">
  </a>
</p>

<h1 align="center">AgentDiff</h1>

<p align="center">
  <strong>See what the agent changed. Undo only the collateral.</strong><br>
  A local-first runtime transaction system for AI-agent commands: filesystem evidence, deterministic policy, explainable blast-radius scoring, and conflict-safe recovery.
</p>

<p align="center">
  <a href="https://github.com/kam6l/agentdiff/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/kam6l/agentdiff/ci.yml?branch=main&style=flat-square&label=CI"></a>
  <a href="https://github.com/kam6l/agentdiff/actions/workflows/deploy.yml"><img alt="Documentation deployment" src="https://img.shields.io/github/actions/workflow/status/kam6l/agentdiff/deploy.yml?branch=main&style=flat-square&label=docs"></a>
  <img alt="Python 3.14+" src="https://img.shields.io/badge/Python-3.14%2B-171916?style=flat-square&logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-f06a3c?style=flat-square"></a>
</p>

<p align="center">
  <a href="https://kam6l.github.io/agentdiff/"><strong>Website</strong></a> ·
  <a href="https://kam6l.github.io/agentdiff/docs/"><strong>Documentation</strong></a> ·
  <a href="https://kam6l.github.io/agentdiff/docs/quickstart/"><strong>Quickstart</strong></a> ·
  <a href="https://kam6l.github.io/agentdiff/docs/trust/"><strong>Trust model</strong></a>
</p>

<p align="center">
  <a href="https://kam6l.github.io/agentdiff/">
    <img src="docs_src/assets/images/agentdiff-landing.png" alt="AgentDiff landing page showing a recorded transaction with three classified filesystem mutations and a blast-radius score" width="100%">
  </a>
</p>

<p align="center"><sub>Real Chromium render of the AgentDiff site. The transaction values come from an executed local run capsule—not a fabricated dashboard.</sub></p>

> [!IMPORTANT]
> AgentDiff's local runtime is an **observation and evidence layer, not a kernel sandbox**. It does not block network access and it cannot undo external APIs, databases, or arbitrary side effects. Use an explicit sandbox backend when you need isolation or network enforcement. Read the [security and capability limits](https://kam6l.github.io/agentdiff/docs/trust/) before using it around sensitive work.

## Why AgentDiff?

An autonomous command can exit successfully while leaving behind a protected environment file, an unexpected dependency edit, and one legitimate source change. A process exit code cannot tell those apart.

AgentDiff wraps an explicit command and gives every observed mutation a durable answer:

- **What changed?** A no-follow before/after filesystem manifest and runtime evidence.
- **Was it expected?** Deterministic `allow`, `review`, or `deny` policy with exact rule provenance.
- **How risky was the run?** An explainable 0–100 blast-radius score with component weights.
- **Can I undo the collateral?** Selective recovery that preserves later human edits and allowed work.
- **Can I trust the stored evidence?** A versioned capsule with an integrity manifest and verification command.

## The transaction loop

| Stage | AgentDiff does | You get |
|---|---|---|
| **Capture** | Records a secure baseline below one project root | Before-state manifest and recoverable file backups |
| **Execute** | Launches your exact argv under local observation or a selected sandbox adapter | Exit status, owned-process evidence, and machine-wide port observations |
| **Evaluate** | Diffs state, applies policy, and scores the blast radius | Path-level decisions, provenance, warnings, and a durable run capsule |
| **Recover** | Conflict-checks current state before changing anything | Conservative rollback of eligible collateral only |

## Quickstart

AgentDiff currently requires **Python 3.14+** and is installed from source:

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --locked --all-groups

# Generate a versioned starter policy
uv run agentdiff policy init

# Wrap any explicit command
uv run agentdiff run \
  --task "Update the parser" \
  -- python3 agent_task.py
```

The command prints a run ID. Use it to inspect and verify the durable evidence:

```bash
uv run agentdiff runs
uv run agentdiff inspect <run-id>
uv run agentdiff verify <run-id>
```

A real local demonstration used by the website produced:

```text
Status: denied (deny)
Process exit: 0
Blast radius: 81/100 (critical)
Mutations: 3

  deny    created  .env
  review  created  pyproject.toml
  allow   created  src/parser.py
```

The command itself succeeded. The **transaction** was denied because its resulting state crossed policy.

Recover only the collateral:

```bash
uv run agentdiff rollback <run-id> --safe-only
```

For the demonstrated capsule, AgentDiff removed `.env` and `pyproject.toml` while preserving the allowed `src/parser.py`. Rollback changes a path only when its current state still matches the post-run state AgentDiff recorded. A later edit becomes a conflict and is preserved.

[Follow the complete five-minute quickstart →](https://kam6l.github.io/agentdiff/docs/quickstart/)

## Policy with provenance

`agentdiff policy init` writes an explicit, versioned YAML policy:

```yaml
version: 1
filesystem:
  allow_write:
    - src/**
    - tests/**
  review:
    - docs/**
  deny:
    - .env
    - .env.*
    - .git/**
    - "**/*.pem"
    - "**/*.key"
  default: review
process:
  allow:
    - python*
    - node
  default: review
network:
  mode: observe
rollback:
  enabled: true
  max_backup_file_mb: 10
```

Rules resolve deterministically with precedence `deny > review > allow > default`. Explain a decision without running an agent:

```bash
uv run agentdiff policy validate
uv run agentdiff policy explain .env
```

Command policy is enforced before local subprocess launch. Filesystem policy is evaluated from the post-run diff; the local backend does not provide kernel-level interception.

## CLI surface

| Command | Purpose |
|---|---|
| `agentdiff run -- <cmd>` | Wrap an explicit argv in an evidence transaction |
| `agentdiff runs` | List durable run capsules below a project root |
| `agentdiff inspect <id>` | Read one capsule in summary or JSON form |
| `agentdiff verify <id>` | Validate the capsule checksum manifest |
| `agentdiff rollback <id> --safe-only` | Recover eligible `review` and `deny` mutations |
| `agentdiff cleanup <id>` | Signal owned processes still associated with a run |
| `agentdiff doctor` | Report implemented local runtime capabilities |
| `agentdiff policy init` | Generate a starter policy |
| `agentdiff policy validate` | Validate policy syntax and semantics |
| `agentdiff policy explain <path>` | Show the winning rule and provenance |

The package also preserves its original snapshot, diff, trajectory, and cleanliness evaluator commands. See the [implemented CLI reference](https://kam6l.github.io/agentdiff/docs/cli/) for exact options and exit behavior.

## Evidence and recovery boundaries

AgentDiff deliberately prefers conservative refusal over broad, unverifiable claims:

- Filesystem capture uses `lstat` and no-follow opens where available. Symlinks are recorded but never traversed.
- Capsules live at `.agentdiff/runs/<run-id>/` with versioned schemas, atomic JSON writes, redacted metadata, and restrictive POSIX permissions.
- Integrity verification detects ordinary artifact tampering; it is not authentication if an attacker can replace the entire capsule.
- Environment observations use stable fingerprints instead of raw values, and common credential-bearing arguments/events are redacted before persistence.
- Process cleanup checks PID plus creation time and refuses ambiguous PID-reuse cases.
- Port changes are machine-wide observations; AgentDiff does not claim run ownership for them.
- Recovery covers eligible regular files with verified backups. It does not roll back symlinks, hardlinks, oversized or unbacked files, APIs, databases, network effects, or arbitrary process side effects.

Read the precise [runtime model](https://kam6l.github.io/agentdiff/docs/concepts/runtime/), [recovery guarantees](https://kam6l.github.io/agentdiff/docs/concepts/recovery/), and [trust model](https://kam6l.github.io/agentdiff/docs/trust/).

## Where it fits

AgentDiff complements rather than replaces the surrounding stack:

| Existing tool | What it is strong at | AgentDiff adds |
|---|---|---|
| LLM tracing platforms | Prompts, generations, spans, and evaluations | Local filesystem/process evidence and mutation recovery |
| E2B, Modal, or Daytona | Isolation and hosted execution | Deterministic policy, durable evidence, and selective rollback inside or outside a sandbox |
| Datadog or Honeycomb | General application observability | Agent-specific mutation semantics and recovery decisions |
| Agent frameworks | Planning and task execution | A framework-neutral transaction boundary around arbitrary argv |
| Git | Versioned source history | Runtime context, non-repository files, policy provenance, and conflict-safe collateral recovery |

## Integration seams

- **Arbitrary commands:** `agentdiff run -- <command>`
- **Python:** `AgentRunTransaction`
- **External enforcement:** optional Anthropic `SandboxRuntime` / `--runtime srt` adapter
- **MCP-style dispatch:** `MCPPolicyHook`, a transport-neutral pre-dispatch hook—not an MCP proxy or server
- **LangChain / LangGraph:** optional callback integration through the `langchain` extra
- **Legacy evaluation:** `AgentDiffSession`, `DiffEngine`, `TrajectoryTracker`, and `AgentDiffEvaluator`

<p align="center">
  <a href="https://kam6l.github.io/agentdiff/docs/cli/">
    <img src="docs_src/assets/images/agentdiff-docs.png" alt="AgentDiff CLI documentation with fixed navigation, command cards, code examples, and a table of contents" width="100%">
  </a>
</p>

<p align="center"><sub>The documentation site is built from this repository with MkDocs Material and deployed through GitHub Pages.</sub></p>

## Project status

AgentDiff is **alpha software**. The runtime format, policy schema, command surface, and recovery behavior may change before a stable package release. There is currently no claimed PyPI, Docker, Homebrew, Scoop, or standalone binary distribution; the verified path is installation from source.

- [Documentation](https://kam6l.github.io/agentdiff/docs/)
- [CLI reference](https://kam6l.github.io/agentdiff/docs/cli/)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Report an issue](https://github.com/kam6l/agentdiff/issues)

## License

MIT licensed. Built by [kam6l](https://github.com/kam6l) and contributors.

<p align="center">
  <img src="docs_src/assets/images/favicon.svg" width="78" alt="AgentDiff logo">
</p>

<h1 align="center">AgentDiff</h1>

<p align="center"><strong>Runtime evidence and conflict-safe recovery for autonomous agents.</strong><br>See what a command changed, decide whether it crossed policy, and selectively undo collateral filesystem mutations.</p>

<p align="center">
  <a href="https://github.com/kam6l/agentdiff/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/kam6l/agentdiff/ci.yml?branch=main&style=flat-square&label=CI"></a>
  <a href="https://kam6l.github.io/agentdiff/"><img alt="Docs" src="https://img.shields.io/github/actions/workflow/status/kam6l/agentdiff/deploy.yml?branch=main&style=flat-square&label=docs"></a>
  <img alt="Python 3.14+" src="https://img.shields.io/badge/Python-3.14%2B-171916?style=flat-square&logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-f06a3c?style=flat-square"></a>
</p>

> [!IMPORTANT]
> AgentDiff is alpha software. Its local backend is **not a sandbox**, does not block network access, and currently recovers only eligible regular files below one project root. Read the [trust model](SECURITY.md) before using it around sensitive work.

## What it does

`agentdiff run` wraps any local command with a transaction:

1. securely records a no-follow filesystem manifest and recoverable before-state;
2. evaluates the command against a deterministic, versioned policy;
3. executes it as a monitored local subprocess;
4. records post-run mutations, owned-process evidence, and machine-wide port observations;
5. assigns every path an `allow`, `review`, or `deny` decision with rule provenance;
6. produces an explainable 0–100 blast-radius score;
7. stores a private local run capsule; and
8. can roll back selected collateral file mutations without overwriting later edits.

AgentDiff preserves its original snapshot, trajectory, and cleanliness evaluator APIs. The transaction runtime extends them; it does not silently replace them.

## Run it

AgentDiff is installed from source; there is no published PyPI package yet.

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --locked --all-groups

uv run agentdiff policy init
uv run agentdiff run --task "Run my coding agent" -- python3 agent.py
```

The command prints a run ID. Inspect the durable evidence:

```bash
uv run agentdiff runs
uv run agentdiff inspect <run-id>
uv run agentdiff verify <run-id>
```

If the run touched protected paths, revert only `review` and `deny` mutations:

```bash
uv run agentdiff rollback <run-id> --safe-only
```

Rollback changes a path only when its current state still equals the state AgentDiff recorded immediately after the run. A later human edit becomes a conflict and is preserved.

### Optional external enforcement

The default local backend is observation-only. If [Anthropic Sandbox Runtime](https://github.com/anthropic-experimental/sandbox-runtime) is installed and configured, AgentDiff can retain the same evidence transaction while delegating execution to `srt`:

```bash
uv run agentdiff run \
  --runtime srt \
  --srt-settings /absolute/path/to/srt-settings.json \
  -- python3 agent.py
```

SRT owns the operating-system enforcement. AgentDiff does not derive SRT restrictions from its mutation policy or certify the supplied settings.

## Policy

`agentdiff policy init` creates an explicit versioned policy:

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
  mode: observe  # observation only; not enforcement
rollback:
  enabled: true
  max_backup_file_mb: 10
```

Rules are evaluated deterministically with precedence `deny > review > allow > default`. Explain a decision without running anything:

```bash
uv run agentdiff policy validate
uv run agentdiff policy explain .env
```

Command policy is enforced before local subprocess launch. Filesystem policy is evaluated from the post-run diff; local mode does not provide kernel-level interception.

## Evidence and recovery guarantees

- Filesystem scanning uses `lstat` and no-follow file opens where available. Symlinks are recorded but never traversed.
- Run capsules live at `.agentdiff/runs/<run-id>/` with restrictive POSIX permissions, atomic JSON writes, redacted command metadata, and versioned schemas.
- Completed capsules include an integrity manifest. Verification detects ordinary artifact tampering but is not authentication when an attacker can replace the whole capsule.
- Environment observations use stable fingerprints instead of raw values; common credential-bearing arguments and nested event fields are redacted before persistence.
- Process cleanup uses PID plus creation time and refuses ambiguous PID-reuse cases.
- Port changes are machine-wide observations. AgentDiff does **not** claim process or run ownership for them.
- Recovery is limited to eligible regular files with verified backups. Symlinks, hardlinks, oversized/unbacked files, external APIs, databases, and network effects are not rolled back.

See [Security](SECURITY.md), [Runtime model](https://kam6l.github.io/agentdiff/concepts/runtime/), and [Recovery](https://kam6l.github.io/agentdiff/concepts/recovery/) for the precise boundary.

## Integration seams

- **Arbitrary commands:** `agentdiff run -- <command>`
- **Python:** `AgentRunTransaction`
- **External enforcement:** optional Anthropic `SandboxRuntime` / `--runtime srt` adapter
- **MCP-style dispatch:** `MCPPolicyHook` is a transport-neutral pre-dispatch hook; it is not an MCP proxy or server
- **Legacy evaluation:** `AgentDiffSession`, `DiffEngine`, `TrajectoryTracker`, and `AgentDiffEvaluator`
- **LangChain/LangGraph:** optional callback integration through the `langchain` extra

## Legacy evaluator

```python
from agentdiff import AgentDiffConfig, AgentDiffSession

config = AgentDiffConfig(root=".", target_paths=["src/evaluator.py"])
with AgentDiffSession("Fix the evaluator", config) as run:
    your_agent()
    run.record("Applied the fix", "edit_file", {"path": "src/evaluator.py"})

result = run.evaluate()
print(f"cleanliness={result.metrics.cleanliness_score:.0%} passed={result.passed}")
```

## Project status

The runtime format, policy schema, and recovery behavior are pre-release and may change before a stable package release. Current limitations are intentional: AgentDiff favors auditable evidence and conservative refusal over broad but unverifiable claims.

- [Documentation](https://kam6l.github.io/agentdiff/)
- [CLI reference](https://kam6l.github.io/agentdiff/cli/)
- [Local SafetyBench](https://kam6l.github.io/agentdiff/project/safetybench/)
- [Competitive analysis](https://kam6l.github.io/agentdiff/competitive-analysis/)
- [Naming analysis](https://kam6l.github.io/agentdiff/project/naming-analysis/)
- [Contributing](CONTRIBUTING.md)
- [Report an issue](https://github.com/kam6l/agentdiff/issues)

<p align="center"><sub>MIT licensed · built by <a href="https://github.com/kam6l">kam6l</a> and contributors</sub></p>

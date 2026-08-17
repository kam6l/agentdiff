<p align="center">
  <a href="https://kam6l.github.io/agentdiff/">
    <img src="docs_src/assets/images/favicon.svg" width="72" alt="AgentDiff logo">
  </a>
</p>

<h1 align="center">AgentDiff</h1>

<p align="center">
  <strong>DON'T TRUST AN AI PATCH. PROVE IT.</strong><br>
  Isolate the agent, observe real state, enforce deterministic policy, reproduce the patch in a clean room, and promote only proven work through a crash-consistent gate.
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

The documentation shell is responsive across desktop and mobile, with an indexed command-palette search (`Ctrl K` or `/`) and a live link to the GitHub repository and star count.

> [!IMPORTANT]
> The local runtime observes a host subprocess; it is not a kernel sandbox and does not block network access. Recovery covers only eligible filesystem changes. Use a real isolation backend for untrusted code.

## Why install it?

A command can exit successfully while leaving one intended edit, one dependency change, and one protected secret file. AgentDiff records the real workspace state independently of the agent, classifies every mutation with deterministic policy, explains the risk score, and can recover eligible collateral without resetting allowed work.

## Start in under a minute

AgentDiff `0.2.x` requires Python 3.12+ and is currently installed from source:

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv tool install .
```

From the project you want to guard, run the agent inside an isolated private
workspace, prove the result in a clean room, then promote only proven work
through the crash-consistent gate:

```bash
agentdiff policy init

agentdiff run \
  --runtime docker \
  --task "Fix authentication" \
  -- codex

agentdiff inspect <run-id>

agentdiff prove <run-id>

agentdiff promote <run-id> --dry-run --safe-only
agentdiff promote <run-id> --safe-only

agentdiff verify <run-id>
```

`agentdiff prove` reproduces the base-plus-patch workspace in a clean Docker
container, runs the **patched** tests, then re-runs the trusted **baseline**
tests (the pre-run verifier files restored over the patched product code) so
an agent cannot hide behind weakened tests. `agentdiff promote` applies only
proven, policy-selected changes with a write-ahead journal and automatic
crash recovery; `--safe-only` selects only `ALLOW` changes.

The trust report shows immediate vs future blast radius, verifier changes,
proof strength, and a single deterministic verdict:

```text
Runtime              Docker / private isolated workspace
Policy               ALLOW
Immediate Blast      12 / LOW
Future Blast          6 / LOW
Trusted Plan         YES
Baseline Tests       184 / 184
Patched Tests        191 / 191
Verifier Changes     2
Proof Strength       L3 / STRONG
Promotion            CRASH-CONSISTENT / SAFE
                     ✓ PROVEN
```

For lower isolation, `--runtime local` runs the agent directly on the host
with observation and recovery, not a sandbox.

[Run the reproducible example](https://kam6l.github.io/agentdiff/docs/quickstart/)

## How it works

| Stage | Result |
|---|---|
| **Isolate** | Docker private workspace (never a writable host repo) or observed local run |
| **Observe** | No-follow before/after manifests, live hybrid safety watcher, owned-process and port evidence |
| **Control** | Deterministic `allow` / `review` / `deny` policy plus budget enforcement |
| **Analyze** | Immediate and future blast radius stay separate |
| **Prove** | Clean-room reproduction with trusted baseline + patched verification |
| **Promote** | Write-ahead journal, crash-consistent recovery, workspace lease |
| **Evidence** | Tamper-evident sealed capsules (spec v2, v1 still verifiable) |

## Feature status

| Status | Surface |
|---|---|
| **Beta** | Transactions, policy, blast radius, capsules, clean-room proof, baseline verifier, promotion gate with crash recovery, and Docker/local runtimes (tested on Python 3.12-3.14, Linux/macOS/Windows) |
| **Experimental** | Cortex evidence memory and provider routing, Anthropic `srt` adapter, transport-neutral MCP policy hook, LangChain callback, content-addressed object store (spec-v3 migration foundation) |
| **Planned** | PyPI/binary releases, authenticated (signed) capsules, capsule export/import CLI, hosted dashboard, maintained hosted sandbox integration |

Capsule checksums are **tamper-evident, not authenticated**: they detect
accidental or modest modification but an attacker who can rewrite the whole
capsule can produce a new self-consistent one. Signing remains future work.
There is no HTTP server, hosted dashboard, or claimed PyPI release today.

## CLI

| Command | Purpose |
|---|---|
| `agentdiff run -- <cmd>` | Wrap an explicit argv in a transaction (`--runtime docker` for isolation) |
| `agentdiff runs` / `inspect` / `verify` | Find, inspect, and validate evidence capsules |
| `agentdiff prove <id>` | Clean-room reproduction + trusted baseline/patched verification |
| `agentdiff promote <id> [--dry-run] [--safe-only]` | Crash-consistent, proof-gated promotion |
| `agentdiff rollback <id> --safe-only` | Recover eligible `review` and `deny` changes |
| `agentdiff cleanup <id>` | Signal exact PID/create-time identities recorded for a run |
| `agentdiff doctor` | Report implemented capabilities and limits |
| `agentdiff policy init/validate/explain` | Create and inspect versioned policy |
| `agentdiff cortex ...` | Open the optional evidence-memory, skill-card, and provider tool namespace |

The earlier `snapshot`, `diff`, and `eval` implementation remains importable for compatibility testing but is no longer exposed as a public CLI path.

### Optional Cortex tools

Cortex is an experimental secondary surface. It can search completed transaction memory and send a bounded context pack through an API or installed client. Local Claude and Codex clients default to plan/read-only mode, and unverified model output is never written back into evidence memory.

```bash
agentdiff cortex memory search "authentication session regression"
agentdiff cortex agent ask --provider codex-cli --task "Plan the smallest safe fix"
agentdiff cortex agent ask --provider ollama-api --model qwen3.6 --task "Review the plan"
agentdiff cortex advise <run-id>
```

[Configure providers and optional local semantic memory](https://kam6l.github.io/agentdiff/docs/concepts/cortex/)

## Trust boundary

AgentDiff never trusts the agent's explanation, environment, verifier, or
generated state. It observes independent filesystem state, reproduces patches
with trusted pre-run verification commands, and promotes only when evidence
supports it. Promotion recovery fails closed when host state is ambiguous or
the journal is corrupt, and the workspace lease never deletes its lock file
(the OS lock itself is released instead), so concurrent promotions cannot
both hold the lock.

It does **not** authenticate a capsule against an attacker who can replace
the whole directory, attribute machine-wide port changes to one process, or
undo APIs, databases, network effects, hardlinks, symlinks, and unbacked
files. Cortex (the experimental LLM surface) can read verified evidence and
generate advice but never decides policy, proof, blast radius, or promotion
outcomes.

Read the [runtime model](https://kam6l.github.io/agentdiff/docs/concepts/runtime/), [recovery guarantees](https://kam6l.github.io/agentdiff/docs/concepts/recovery/), and [security limits](https://kam6l.github.io/agentdiff/docs/trust/).

<p align="center">
  <a href="https://kam6l.github.io/agentdiff/docs/">
    <img src="docs_src/assets/images/agentdiff-docs.png" alt="Responsive AgentDiff documentation with search and repository controls" width="100%">
  </a>
</p>

AgentDiff is MIT-licensed beta software. [Security](SECURITY.md) | [Contributing](CONTRIBUTING.md) | [Changelog](CHANGELOG.md) | [Issues](https://github.com/kam6l/agentdiff/issues)

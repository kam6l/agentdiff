<p align="center">
  <a href="https://kam6l.github.io/agentdiff/">
    <img src="docs_src/assets/images/favicon.svg" width="72" alt="AgentDiff logo">
  </a>
</p>

<h1 align="center">AgentDiff</h1>

<p align="center">
  <strong>The trust layer for self-maintaining APIs.</strong><br>
  When an API changes, AgentDiff finds affected customer code, generates or supervises the migration, independently proves the patch in a clean room, and opens a reviewable PR with evidence.
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

## Why AgentDiff?

API providers (Stripe, OpenAI, etc.) deprecate endpoints, shut down models, and release breaking SDK versions. Customers are left with broken integrations, manual migration guides, and no verification that the migration actually works.

AgentDiff solves this by making **verified migrations** the default:

1. **Scan** — AST-based detection of every API usage in customer code (provenance-tracked, no false positives)
2. **Match** — Deterministic matching against provider breaking-change catalogs with SDK version awareness
3. **Migrate** — Deterministic AST transforms for known migrations; coding agent for complex ones (all patches untrusted until proven)
4. **Prove** — Clean-room verification in isolated workspace: syntax, types, targeted tests, full repo tests
5. **Certify** — Machine-readable Migration Certificate with blast radius, test results, proof digest, rollback info
6. **Deliver** — Conflict-safe promotion to a GitHub PR with full evidence attached

The coding agent is probabilistic. AgentDiff is the deterministic verifier that decides whether the result is trustworthy.

## Self-Maintaining APIs

AgentDiff turns API changes into verified migrations. The pipeline is:

**Detect → Plan → Execute → Verify → Certify → Deliver**

```bash
# Scan repository for all external API calls
agentdiff api scan --root .

# Check for breaking changes, calculate impact, and report remediation
agentdiff api check --root . --fail-on high

# Generate + verify a migration in a private workspace, emit a certificate
agentdiff api migrate --provider openai --change chat_to_responses

# Turn upstream signals into validated manifest candidates
agentdiff api intel --provider openai --changelog CHANGELOG.md

# Install provider migration plugins
agentdiff provider install stripe ./providers/stripe
agentdiff provider list
```

### Provider Intelligence Layer

AgentDiff can ingest upstream signals and produce validated `APIChangeManifest`
candidates — **suggestion only, never applied directly**:

- `--changelog` — parse markdown changelogs for removals/deprecations/renames
- `--openapi-before/--openapi-after` — diff two OpenAPI specs for breaking changes
- `--release` — analyze SDK release notes
- AI-assisted suggestions are accepted as candidates that must still pass
  deterministic validation before they can drive a migration

### Provider Plugin System

Providers and community members ship migrations without touching core code:

```
providers/<name>/
    metadata.yaml     # name, library, version
    manifests/        # *.yaml APIChangeManifest files
    transforms/       # python modules registering AST transforms
    tests/            # optional plugin tests
```

### Trust model

The coding agent (or AST transform) generates the migration. AgentDiff decides
whether it is trustworthy — deterministic policy, blast radius, clean-room proof,
and a MigrationCertificate recording exactly what was verified. **The AI is
probabilistic; the trust decision is deterministic.**

## Zero-Touch Trust Engine (Foundation)

The same trust infrastructure that verifies API migrations also powers safe coding-agent automation:

```bash
agentdiff init                          # compile canonical trust configuration
agentdiff wrap -- codex exec "Fix authentication timeout"
```

AgentDiff automatically understands the repository, prepares a private warm workspace, observes and enforces the agent's work, runs the minimum strong proof (impact-aware, cache-backed), retries failures while the repair stays in scope, and promotes the proven result — interrupting the human only when the trust boundary changes.

| Outcome | Action |
|---|---|
| Normal source change + proof passes | **AUTO** promote + notify |
| Proof fails, repair stays in scope | **RETRY** bounded automatic repair |
| Dependency added / CI changed / config changed | **HUMAN** review |
| Agent requests new scope / high future risk | **HUMAN** |

The [trust pipeline](https://kam6l.github.io/agentdiff/docs/concepts/trust-pipeline/) remains the security foundation. Systems: [trust compiler](https://kam6l.github.io/agentdiff/docs/concepts/trust-compiler/), [impact-aware proof + cache](https://kam6l.github.io/agentdiff/docs/concepts/impact-proof/), [automatic repair loop](https://kam6l.github.io/agentdiff/docs/concepts/repair-loop/), [warm workspaces](https://kam6l.github.io/agentdiff/docs/concepts/warm-workspaces/), and the [zero-touch sidecar](https://kam6l.github.io/agentdiff/docs/concepts/zero-touch/).

## Start in under a minute

AgentDiff `0.3.0` requires Python 3.12+ and is currently installed from source:

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
| **Beta** | Local transactions, policy, capsules, verification, scoring, regular-file recovery, trust compiler, impact-aware proof + cache, warm workspaces, repair loop, sidecar (tested on Python 3.12-3.13) |
| **Experimental** | Cortex evidence memory and provider routing, Anthropic `srt` adapter, transport-neutral MCP policy hook, LangChain callback, and the in-repository composite Action |
| **Planned** | PyPI/binary releases, authenticated evidence, telemetry export, and a maintained hosted sandbox integration |

There is no hosted dashboard or hosted service: the sidecar is a local daemon, and all state stays under `<root>/.agentdiff`.

## CLI

| Command | Purpose |
|---|---|
| `agentdiff init` / `bootstrap` | Compile canonical trust configuration |
| `agentdiff wrap -- <agent>` | Run one agent through the full zero-touch pipeline |
| `agentdiff serve` / `status` / `stop` / `hook` | Local sidecar daemon + agent adapters |
| `agentdiff prove <id>` / `promote <id>` | Clean-room proof and conflict-safe promotion |
| `agentdiff repair <id>` | Verified automatic repair until proof passes |
| `agentdiff run -- <cmd>` | Wrap an explicit argv in a transaction |
| `agentdiff runs` / `inspect` / `verify` | Find and validate local evidence capsules |
| `agentdiff rollback <id> --safe-only` | Recover eligible `review` and `deny` changes |
| `agentdiff cleanup <id>` | Signal exact PID/create-time identities recorded for a run |
| `agentdiff doctor` | Report implemented capabilities and limits |
| `agentdiff trust` / `impact` / `proof cache-status` | Trust graph, impact plan, proof cache |
| `agentdiff workspace status/warm/prune` | Trusted warm workspace snapshots |
| `agentdiff policy init/validate/explain` | Create and inspect versioned policy |
| `agentdiff api scan` / `check` | Self-maintaining API usage scanner and breaking change checker |
| `agentdiff api migrate` | Generate and verify an API migration in a private workspace |
| `agentdiff api intel` | Analyze changelog/OpenAPI/release signals into manifest candidates |
| `agentdiff provider list` / `install` | Manage provider migration plugins |
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

AgentDiff records symlinks without traversing them, redacts common secret-bearing values, verifies backups and capsule checksums, and identifies processes by PID plus creation time. It does **not** authenticate a capsule against an attacker who can replace the whole directory, attribute machine-wide port changes to one process, or undo APIs, databases, network effects, hardlinks, symlinks, and unbacked files.

Read the [runtime model](https://kam6l.github.io/agentdiff/docs/concepts/runtime/), [recovery guarantees](https://kam6l.github.io/agentdiff/docs/concepts/recovery/), and [security limits](https://kam6l.github.io/agentdiff/docs/trust/).

<p align="center">
  <a href="https://kam6l.github.io/agentdiff/docs/">
    <img src="docs_src/assets/images/agentdiff-docs.png" alt="Responsive AgentDiff documentation with search and repository controls" width="100%">
  </a>
</p>

AgentDiff is MIT-licensed beta software. [Security](SECURITY.md) | [Contributing](CONTRIBUTING.md) | [Changelog](CHANGELOG.md) | [Issues](https://github.com/kam6l/agentdiff/issues)
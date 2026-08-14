---
title: CLI overview
description: The implemented AgentDiff command-line surface for transactions, evidence, recovery, memory, and provider routing.
---

<span class="ad-doc-eyebrow">CLI</span>

# Command-line interface

<div class="ad-doc-lede">The CLI wraps explicit argv, persists evidence under the project root, and exposes deterministic output suitable for both people and automation.</div>

```bash
agentdiff <command> --help
```

## Transaction workflow

<div class="ad-doc-command-grid">
<a href="run/"><code>run</code><span>Execute an argv inside an observed transaction.</span></a>
<a href="inspect/"><code>inspect</code><span>Read one durable run capsule.</span></a>
<a href="rollback/"><code>rollback</code><span>Conflict-check and recover eligible changes.</span></a>
<a href="operations/#verify-capsule-integrity"><code>verify</code><span>Validate the capsule checksum manifest.</span></a>
<a href="operations/#list-run-capsules"><code>runs</code><span>List durable capsules under a root.</span></a>
<a href="operations/#report-runtime-capabilities"><code>doctor</code><span>Report implemented runtime capabilities.</span></a>
</div>

## Policy workflow

```bash
agentdiff policy init
agentdiff policy validate --policy agentdiff.yaml
agentdiff policy explain .env --policy agentdiff.yaml
```

See [policy commands](policy.md) for the exact subcommand surface.

## Cortex workflow

```bash
agentdiff memory search "authentication regression"
agentdiff agent ask --provider codex-cli --task "Plan the smallest safe fix"
```

See [Cortex, memory, and provider commands](cortex.md) for Claude, Codex/OpenAI, Ollama, and optional local semantic indexing.

## Shared conventions

### Project root

Transaction commands default to the current directory. Use `--root` when the command and evidence store belong elsewhere:

```bash
agentdiff runs --root /workspace/project
agentdiff inspect <run-id> --root /workspace/project
```

Capsules are stored at `<root>/.agentdiff/runs/<run-id>/`.

### Output formats

Current transaction and operational commands support:

- `--format summary` — compact, human-readable output;
- `--format json` — complete machine-readable output.

### Exit behavior

`agentdiff run` preserves a non-zero subprocess exit code. For a successful subprocess, the default `--fail-on deny` policy maps observed safety outcomes as follows:

| Outcome | Default exit |
| --- | ---: |
| allow | `0` |
| review | `0` |
| deny | `3` |
| command blocked before launch | `126` |
| AgentDiff execution error | `1` |

Use `--fail-on never` to report policy only, or `--fail-on review` to make both review and deny outcomes non-zero.

## Full implemented command map

```text
agentdiff
├── run
├── inspect / runs / verify
├── rollback / cleanup / doctor
├── policy
│   └── init / validate / explain
├── memory
│   └── stats / search / index
├── agent
│   └── ask
├── skill
│   └── list / generate
├── context
│   └── pack
├── heal
└── snapshot / diff / eval    # legacy evaluator path
```

!!! tip "Trust the installed help"
    The command surface is beta and may evolve. `agentdiff <command> --help` is generated directly from the installed implementation.

---
title: Cortex, memory, and provider commands
description: CLI reference for memory search, semantic indexing, AI provider routing, skill synthesis, and remediation.
---

<p><span class="ad-doc-eyebrow">CLI reference</span></p>
# Cortex, memory, and provider commands

<div class="ad-doc-lede">Search verified repository memory and route a bounded context pack through Claude, Codex/OpenAI, or Ollama.</div>

## Ask an AI provider

### Codex client

Uses your installed Codex authentication. Cortex launches an ephemeral, read-only client run.

```bash
agentdiff agent ask \
  --provider codex-cli \
  --task "Plan the smallest safe parser fix"
```

### OpenAI / Codex API

```bash
export OPENAI_API_KEY="..."
agentdiff agent ask \
  --provider openai-api \
  --model gpt-5.6-terra \
  --task "Review the authentication recovery plan"
```

Continue a Responses API chain with:

```bash
agentdiff agent ask \
  --provider openai-api \
  --previous-response-id resp_123 \
  --task "Now minimize the proposed diff"
```

### Claude Code client

Uses your installed Claude Code authentication. Cortex uses non-persistent print mode and plan permissions.

```bash
agentdiff agent ask \
  --provider claude-cli \
  --task "Find the safest recovery boundary"
```

### Anthropic API

```bash
export ANTHROPIC_API_KEY="..."
agentdiff agent ask \
  --provider anthropic-api \
  --model claude-sonnet-5 \
  --task "Review the evidence capsule design"
```

### Ollama API or client

The model is always explicit because installed local models differ by machine.

```bash
agentdiff agent ask \
  --provider ollama-api \
  --model qwen3.6 \
  --task "Plan the parser repair"

agentdiff agent ask \
  --provider ollama-cli \
  --model qwen3.6 \
  --task "Review the rollback logic"
```

Use `--no-memory` for a provider-only request, `--max-memories` to change the default limit of four evidence cards, and `--format json` for the normalized provider response and usage fields. `--endpoint`, `--executable`, and `--api-key-env` support self-hosted or non-default configurations without putting a secret value on the command line.

## Search trajectory memory

```bash
agentdiff memory stats
agentdiff memory search "authentication session regression"
agentdiff memory search "src/auth/session.py" --limit 3 --format json
```

The search command is offline by default. It ranks compressed evidence cards by shared task/path terms, exact paths, recency, and policy risk.

## Add local semantic vectors

```bash
ollama pull embeddinggemma
agentdiff memory index --model embeddinggemma
agentdiff memory search \
  "authentication session regression" \
  --embedding-model embeddinggemma
```

`memory index` sends compressed memory cards to the configured Ollama embedding endpoint and stores the returned vectors locally. Re-run it after adding episodes or changing the embedding model.

To use semantic memory automatically during an AI request:

```bash
agentdiff agent ask \
  --provider ollama-api \
  --model qwen3.6 \
  --embedding-model embeddinggemma \
  --task "Plan a safe session middleware refactor"
```

## Pack context without calling a provider

```bash
agentdiff context pack --task "Fix payment gateway timeout"
```

The output includes matched skills, fragile paths, relevant verified runs, and the rule that rejected runs are warnings rather than successful examples.

## Synthesize a reusable skill

```bash
agentdiff skill list
agentdiff skill generate <run-id> --title "Postgres Connection Pooling"
```

The generated `.agentdiff/skills/<skill-slug>.md` remains traceable to its source capsule.

## Generate remediation

```bash
agentdiff heal <run-id>
agentdiff heal <run-id> --format json
```

The payload identifies collateral paths and the conflict-safe rollback command for an autonomous retry harness. It does not automatically execute recovery or retry the agent.

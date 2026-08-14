---
title: Cortex memory and AI providers
description: Evidence-aware repository memory and provider adapters for Claude, Codex/OpenAI, and Ollama.
---

<p><span class="ad-doc-eyebrow">Core concepts</span></p>
# Cortex memory and AI providers

<div class="ad-doc-lede">Route bounded, evidence-backed repository context to Claude, Codex/OpenAI, or Ollama without mixing unverified model output into trusted run memory.</div>

Cortex is AgentDiff's provider-neutral intelligence layer. It is not a second agent framework and it does not silently execute model output. It connects verified transaction evidence to an explicitly selected API or local client.

## Architecture

Each request passes through four isolated stages:

1. **Evidence memory** reads completed AgentDiff transaction cards from `.agentdiff/memory.json`.
2. **Hybrid retrieval** ranks cards using task and path overlap, recency, policy risk, and optional semantic vectors.
3. **Context packing** labels clean runs separately from prior `review` or `deny` findings and applies a strict result limit.
4. **Provider routing** sends the current task and context to exactly one configured provider.

This follows the useful provider-isolation pattern in [Hermes Agent memory providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers/), while applying an AgentDiff-specific trust rule: model responses are unverified and are **never** written into the evidence store. A later `agentdiff run` records the actual verified state instead.

## Supported providers

| Provider | Cortex adapter | Default behavior |
|---|---|---|
| OpenAI / Codex API | `openai-api` or `codex-api` | Responses API, `gpt-5.6-terra`, medium reasoning, persisted reasoning context |
| Codex client | `codex-cli` | Ephemeral `codex exec` session with a read-only sandbox |
| Anthropic API | `anthropic-api` or `claude-api` | Messages API, `claude-sonnet-5` |
| Claude Code client | `claude-cli` | Non-persistent print session in plan permission mode |
| Ollama API | `ollama-api` | Native `/api/chat`; the local model is required |
| Ollama client | `ollama-cli` | `ollama run`; the local model is required |

The OpenAI adapter uses the current [Responses API model guidance](https://developers.openai.com/api/docs/guides/latest-model), including `previous_response_id` for a continued response. Anthropic's current [model IDs](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions) use a dateless pinned format for Claude 4.6 and newer. Ollama uses its native [chat](https://docs.ollama.com/capabilities/tool-calling) and [embedding](https://docs.ollama.com/capabilities/embeddings) endpoints; its OpenAI-compatible Responses layer does not preserve `previous_response_id`, so Cortex does not pretend that it does.

## Memory trust classes

Cortex treats a previous run according to its recorded outcome:

- `ALLOW` is a verified clean-run example.
- `REVIEW` and `DENY` are warnings and never successful implementation examples.
- synthesized skills remain explicit files under `.agentdiff/skills/` and include their originating capsule ID.
- raw prompts, API keys, and provider responses are not added to trajectory memory.

This keeps useful long-term context without allowing a plausible model answer to become repository truth.

## Hybrid retrieval

Local retrieval works without a model or network connection. Its deterministic score combines:

- task and symbol/path term overlap;
- exact path matches;
- recency decay over recorded episodes; and
- higher visibility for risky historical findings.

Optional Ollama embeddings add semantic similarity to the score. They enrich the index; they do not replace deterministic evidence signals.

```bash
ollama pull embeddinggemma
agentdiff memory index --model embeddinggemma
agentdiff memory search "authentication session regression" --embedding-model embeddinggemma
```

The embedding vectors remain in `.agentdiff/memory.json`. The text sent to the local embedding endpoint is the compressed card—not the full evidence capsule or raw file contents.

## Per-turn hooks

`RepositoryMemoryProvider` exposes the same lifecycle a provider plugin needs:

```python
from agentdiff import CortexRouter, RepositoryMemoryProvider, create_provider

provider = create_provider("ollama-api", model="qwen3.6")
memory = RepositoryMemoryProvider(".", max_memories=4)
router = CortexRouter(provider, memory=memory, root=".")

result = router.ask("Plan the smallest safe authentication fix")
print(result.response.text)
router.shutdown()
```

`prefetch()` runs before the request, `sync_turn()` runs after it, and `shutdown()` releases provider resources. The built-in repository provider deliberately makes `sync_turn()` a no-op because the returned model text has not been verified.

## Safety boundary

API adapters return text and expose no execution tools. Local Claude and Codex clients can inspect the repository, but Cortex starts them in plan/read-only modes. To make changes, run an explicit agent command through the normal transaction boundary:

```bash
agentdiff run --task "Fix authentication" -- codex
```

Provider APIs can incur cost and send the packed task context to the configured service. Ollama stays local when its endpoint points to localhost. AgentDiff never copies API keys into memory, output JSON, or subprocess arguments.

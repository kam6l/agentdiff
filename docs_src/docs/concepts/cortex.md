---
title: AgentDiff Cortex & Skill Memory
description: Autonomous skill synthesis, compressed trajectory memory, and self-healing feedback loops for AI coding agents.
---

<p><span class="ad-doc-eyebrow">Core concepts</span></p>
# AgentDiff Cortex & Skill Memory

<div class="ad-doc-lede">Transform verified transaction capsules into reusable architectural skills, compressed trajectory memory cards, and machine-actionable self-healing directives.</div>

Building large, multi-module software systems with AI agents (Claude Code, Codex, Cursor, Devin, Hermes) frequently suffers from **agent amnesia**: as the project grows, agents lose architectural context, re-introduce regressions to earlier modules, and waste thousands of tokens per turn.

**AgentDiff Cortex** solves this by establishing persistent repository intelligence:

1. **Autonomous Skill Synthesis**: Converts clean, verified transaction runs into structured `SKILL.md` documents.
2. **Context Compression**: Compresses multi-turn diffs and logs into high-signal memory cards (<400 tokens).
3. **Dynamic Context Packing**: Injects relevant skills and fragility alerts into new agent prompts.
4. **Self-Healing Directives**: Emits machine-consumable JSON remediation instructions for autonomous retry loops.

---

## 1. Autonomous Skill Synthesis

Whenever an agent transaction finishes with an `ALLOW` policy decision and passing tests, Cortex can synthesize a reusable **Skill Manifest** (`.agentdiff/skills/<skill-name>.md`):

```bash
agentdiff skill generate <run-id> --title "FastAPI Session Auth"
```

The generated markdown skill captures:
- **Triggers**: Intent keywords determining when this skill should be injected into future agent prompts.
- **Hard Invariants**: Concrete architectural rules learned from the execution (e.g. *"Always use dependency injection singleton; never commit raw secrets"*).
- **Safe Path Mutex**: The verified whitelist of files allowed for this pattern.
- **Verification Recipe**: The exact automated test command required to validate correctness.

---

## 2. Compressed Trajectory Memory

Instead of feeding raw multi-megabyte git histories to LLMs, the Cortex **ContextCompressor** reduces execution episodes into dense, mathematically indexed memory cards:

```json
{
  "task": "Refactor authentication session handler",
  "outcome": "ALLOW",
  "blast_radius": 14,
  "modified_symbols_or_files": ["src/auth/session.py", "src/auth/handler.py"],
  "key_learnings": ["Clean transactional execution across 2 files"]
}
```

Memory cards are indexed in `.agentdiff/memory.json` alongside a dynamic **Fragility Map** that tracks modules frequently subject to collateral damage or rollback conflicts.

---

## 3. Dynamic Context Packing

Before launching an AI agent on a new feature or refactor, use `agentdiff context pack` to inject learned repository memory:

```bash
agentdiff context pack --task "Implement Stripe billing webhook"
```

Output:
```markdown
<!-- AGENTDIFF CONTEXT MEMORY PACK -->
## AgentDiff Execution Directives
**Target Task Intent**: Implement Stripe billing webhook

### RELEVANT ARCHITECTURAL SKILLS:
- **Webhook Handlers**: Verify HMAC signature before database mutation (Verify with `pytest tests/test_webhooks.py`)

### FRAGILE PATHS (Historically high collateral risk):
- `config/secrets.env` (Risk frequency: 3.0)

### Safety Mandate:
1. Stay strictly within the scope of `Implement Stripe billing webhook`.
2. Do not introduce collateral modifications to untouched modules.
3. Validate state before completion.
<!-- END CONTEXT PACK -->
```

---

## 4. Self-Healing Remediation Protocol

When an agent violates deterministic policy or exceeds blast-radius thresholds, `agentdiff heal` outputs a structured payload for autonomous agent harnesses:

```bash
agentdiff heal <run-id> --format json
```

Autonomous agents can consume this payload to selectively undo collateral and re-attempt the task within constrained boundaries without human intervention.

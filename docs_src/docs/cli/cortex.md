---
title: Cortex CLI Commands
description: CLI reference for skill synthesis, context packing, memory inspection, and self-healing.
---

<p><span class="ad-doc-eyebrow">CLI reference</span></p>
# Cortex & Memory Commands

<div class="ad-doc-lede">CLI commands for autonomous skill synthesis, prompt context packing, memory analytics, and self-healing.</div>

## 1. `agentdiff skill`

Manage and synthesize reusable skills from verified transaction runs.

### List Learned Skills
```bash
agentdiff skill list
agentdiff skill list --format json
```

### Synthesize a Reusable Skill
Extract a verified `SKILL.md` from a specific transaction capsule:
```bash
agentdiff skill generate <run-id>
agentdiff skill generate <run-id> --title "Postgres Connection Pooling"
```

The resulting skill document is saved into `.agentdiff/skills/<skill-slug>.md`.

---

## 2. `agentdiff context pack`

Package relevant architectural skills, fragility warnings, and safety constraints into a dense prompt context block:

```bash
agentdiff context pack --task "Fix payment gateway timeout"
```

Pass the output directly into Claude Code, Codex, Cursor, or Aider prompt context.

---

## 3. `agentdiff memory stats`

Inspect repository trajectory memory and identify high-risk fragile paths:

```bash
agentdiff memory stats
agentdiff memory stats --format json
```

Example output:
```text
AgentDiff Trajectory Memory Stats
  Total episodes recorded: 14
  Fragile paths tracked:   3
  Top Fragile Paths:
    - config/secrets.env (Risk score: 4.0)
    - src/auth/jwt.py (Risk score: 2.0)
```

---

## 4. `agentdiff heal`

Generate a machine-actionable remediation payload for autonomous agent retry loops:

```bash
agentdiff heal <run-id>
agentdiff heal <run-id> --format json
```

Example JSON response:
```json
{
  "run_id": "run-e45c0d69",
  "status": "REMEDIATION_REQUIRED",
  "decision": "DENY",
  "blast_radius_score": 72,
  "collateral_files_to_revert": [
    ".env",
    "config/keys.py"
  ],
  "recovery_command": "agentdiff rollback run-e45c0d69 --safe-only",
  "prompt_repair_directive": "Your previous attempt triggered a DENY verdict with blast-radius 72/100. Revert collateral in ['.env', 'config/keys.py'] and constrain edits."
}
```

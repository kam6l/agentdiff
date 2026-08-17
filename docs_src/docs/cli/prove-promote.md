---
title: Prove and promote
description: CLI reference for deterministic clean-room proof and conflict-safe promotion.
---

# Prove and promote

## `agentdiff prove`

```bash
agentdiff prove RUN_ID [--root PATH] [--timeout SECONDS] [--format summary|json]
```

Exit `0` means `PROVEN`; exit `7` means `NOT_PROVEN`. Setup, build, and test commands use exact argv and one timeout per phase.

## `agentdiff promote`

```bash
agentdiff promote RUN_ID \
  [--root PATH] \
  [--dry-run] \
  [--safe-only] \
  [--path RELATIVE_PATH ...] \
  [--format summary|json]
```

Exit `0` means the dry-run plan is safe or selected changes were promoted; exit `4` means plan conflicts; exit `8` means another refusal; exit `9` means promotion was blocked (missing/corrupt proof evidence or recovery could not establish a safe state). Promotion is unavailable without valid `PROVEN` evidence, and a corrupt or ambiguous recovery journal blocks promotion instead of being treated as absent.

`--safe-only` selects `ALLOW` entries. Without it, `REVIEW` entries still require explicit `--path`; `DENY` entries are never promotable. Use `--dry-run --safe-only` before any real promotion.

## Integrity

After proof or promotion:

```bash
agentdiff verify RUN_ID
```

`verify` checks the immutable capsule and every present proof/promotion extension manifest.

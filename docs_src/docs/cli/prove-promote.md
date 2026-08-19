---
title: Prove and promote
description: CLI reference for deterministic clean-room proof and conflict-safe promotion.
---

# Prove and promote

## `agentdiff prove`

```bash
agentdiff prove RUN_ID [--root PATH] [--timeout SECONDS] [--target static|targeted|full]
              [--no-cache] [--format summary|json]
```

Exit `0` means `PROVEN`; exit `7` means `NOT_PROVEN`. Setup, build, and test commands use exact argv and one timeout per phase.

`--target` selects the impact-aware proof level (`full` by default, `targeted`/`static` for smaller patches). The content-addressed proof cache is consulted automatically unless `--no-cache` is passed; cached verdicts are sealed per run and surfaced as `cache_hit` in the result.

## `agentdiff promote`

```bash
agentdiff promote RUN_ID \
  [--root PATH] \
  [--dry-run] \
  [--safe-only] \
  [--path RELATIVE_PATH ...] \
  [--format summary|json]
```

Exit `0` means the dry-run plan is safe or selected changes were promoted. Exit `8` means conflict/refusal. Promotion is unavailable without valid `PROVEN` evidence.

`--safe-only` selects `ALLOW` entries. Without it, `REVIEW` entries still require explicit `--path`; `DENY` entries are never promotable. Use `--dry-run --safe-only` before any real promotion.

## Integrity

After proof or promotion:

```bash
agentdiff verify RUN_ID
```

`verify` checks the immutable capsule and every present proof/promotion extension manifest.

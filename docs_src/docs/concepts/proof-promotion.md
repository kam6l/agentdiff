---
title: Clean-room proof and promotion
description: Deterministic replay, hidden-state detection, and unchanged-base host promotion.
---

# Clean-room proof and promotion

## Proof

`agentdiff prove RUN_ID` materializes the sealed pre-run source and applies only the sealed patch into an empty temporary directory. A new ephemeral Docker container runs setup, build, and test argv. It does not reuse the agent workspace, environment, virtualenv, installed packages, generated caches, or services.

Policy schema 2 can define exact argv:

```yaml
proof:
  image: "ghcr.io/astral-sh/uv:python3.12-bookworm-slim"
  network: false
  setup:
    - ["uv", "sync", "--frozen", "--no-cache"]
  build:
    - ["uv", "build"]
  tests:
    - ["uv", "run", "pytest", "-q"]
```

When all command lists are empty, AgentDiff uses conservative discovery for `uv.lock`, Python projects, or `package-lock.json`. No discoverable test command means `NOT_PROVEN`.

Proof output is reduced to status, return code, duration, output byte count/digest, and bounded test counts. Raw logs are not stored. A successful original run followed by a clean-room phase failure is labeled `POSSIBLE` hidden-state dependency.

## Promotion

```bash
agentdiff promote RUN_ID --dry-run --safe-only
agentdiff promote RUN_ID --safe-only
agentdiff promote RUN_ID --safe-only --path src/auth.py
```

Promotion checks:

- immutable capsule integrity;
- proof-extension integrity;
- `PROVEN` verdict;
- matching immutable and patch digests;
- policy selection (`ALLOW` only with `--safe-only`);
- normalized root-relative paths;
- single-link regular-file payloads; and
- exact current-host/base hash and mode equality.

It rejects symlinks, hardlinks, special files, path traversal, stale hashes, newer host work, incomplete patches, and ambiguous state. It applies only planned files through atomic create/replace primitives where supported and records every action/conflict/skip.

Do not run concurrent writers during promotion. User-space rechecks reduce but cannot eliminate all TOCTOU races. A late race can stop a multi-file operation after earlier verified paths were applied, producing `PARTIAL_CONFLICT` with an exact action log.

---
title: Zero-touch CLI reference
description: Commands for the zero-touch automation layer: init, bootstrap, prove, promote, repair, wrap, serve, hook, trust, impact, proof cache, workspace.
---

# Zero-touch CLI reference

## `agentdiff init`

Compile the canonical trust configuration and optionally start the sidecar.

```bash
agentdiff init [--root PATH] [--force] [--agents] [--daemon]
```

## `agentdiff bootstrap`

Compile the trust configuration from deterministic repository inspection
(see [Trust compiler](../concepts/trust-compiler.md)).

```bash
agentdiff bootstrap [--root PATH] [--force] [--dry-run] [--agents]
                    [--format json|summary]
```

Exit `0` on success, `2` when the configuration already exists without
`--force`.

## `agentdiff prove`

Run deterministic clean-room proof for a sealed run capsule. Supports the
impact-aware target and the content-addressed cache.

```bash
agentdiff prove RUN_ID [--root PATH] [--timeout SECONDS]
              [--target static|targeted|full] [--no-cache]
              [--format json|summary]
```

Exit `0` means `PROVEN`; exit `7` means `NOT_PROVEN`.

## `agentdiff promote`

Promote a proven patch to the host repository with conflict checks and a
write-ahead journal. `--store-root` promotes a capsule that lives in a
private workspace.

```bash
agentdiff promote RUN_ID [--root PATH] [--store-root PATH]
                [--dry-run] [--safe-only] [--path REL ...]
                [--format json|summary]
```

Exit `0` means promoted or dry-run safe; exit `8` means conflict/refusal.

## `agentdiff repair`

Run verified automatic repair until proof passes or the trust boundary
changes (see [Automatic repair loop](../concepts/repair-loop.md)).

```bash
agentdiff repair RUN_ID [--root PATH] [--policy FILE]
                [--max-attempts N] [--max-runtime SECONDS]
                [--no-cache] [--no-agent]
                [--agent-argv -- <agent argv>]
                [--format json|summary]
```

Exit codes: `0` repaired, `9` failed, `10` needs human, `11` needs agent,
`12` blocked.

## `agentdiff wrap`

Run one agent command through the full zero-touch pipeline: warm workspace →
transaction → impact-aware proof → bounded repair → promotion → notify.

```bash
agentdiff wrap [--root PATH] [--policy FILE] [--task TEXT]
         [--session ID] [--no-proof] [--no-repair] [--no-promote]
         [--no-cache] [--max-attempts N] [--max-repair-runtime SECONDS]
         [--format json|summary] -- <agent argv>
```

Example:

```bash
agentdiff wrap -- codex exec "Fix authentication timeout"
```

## Sidecar daemon

```bash
agentdiff serve [--root PATH] [--port N] [--daemon]
agentdiff status [--root PATH] [--format json|summary]
agentdiff stop  [--root PATH]
```

`agentdiff hook <event>` sends lifecycle/tool events to the sidecar:

```bash
agentdiff hook session-begin --task "Fix auth" --data '{"agent":"codex"}'
agentdiff hook tool-call --session-id SESSION --data '{"tool_name":"write_file","arguments":{"path":"src/a.py"}}'
agentdiff hook session-end --session-id SESSION
```

## Trust, impact, proof cache, workspace

```bash
agentdiff trust graph [--root PATH] [--format json|summary]
agentdiff trust status [--root PATH] [--format json|summary]
agentdiff impact --paths src/auth.py,src/app.py [--root PATH] [--format json|summary]
agentdiff proof cache-status [--root PATH] [--format json|summary]
agentdiff workspace status [--root PATH] [--format json|summary]
agentdiff workspace warm  [--root PATH] [--policy FILE] [--format json|summary]
agentdiff workspace prune [--root PATH] [--keep N]
```

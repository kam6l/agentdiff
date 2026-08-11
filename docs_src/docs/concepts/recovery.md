# Selective recovery

AgentDiff rollback is designed to preserve intended work while removing selected collateral filesystem changes. It is not a workspace reset and does not call `git reset`.

## Core safety invariant

For each selected path:

```text
restore or delete only when current state == recorded post-run state
```

If the path changed after the run, rollback records a conflict and leaves the current state untouched. This protects human edits, formatter changes, and subsequent runs from being silently overwritten.

## Safe-only rollback

```bash
agentdiff rollback <run-id> --safe-only
```

`--safe-only` selects `review` and `deny` file mutations. Paths classified `allow` are retained as intended work.

To attempt every recorded file mutation:

```bash
agentdiff rollback <run-id> --all
```

You can further restrict either mode:

```bash
agentdiff rollback <run-id> --safe-only --path .env --path debug.log
```

## Supported operations

For eligible regular files AgentDiff can:

- delete a file created by the run;
- restore a file modified by the run from its verified before-state backup; and
- restore a file deleted by the run from its verified before-state backup.

Mode metadata is restored with file contents where supported.

## Refusal and conflict cases

AgentDiff refuses or reports a conflict for conditions including:

- the current path does not match the recorded post-run state;
- an expected path became a symlink or unsupported object;
- path traversal or an absolute path appears in stored evidence;
- a backup is missing, oversized, malformed, or fails SHA-256 verification;
- the before-state file had multiple hardlinks;
- capture did not produce an eligible backup;
- the path is outside the recorded project root; or
- the run policy disabled rollback capture.

A conflict is a safe outcome. Investigate it manually rather than bypassing the equality check.

## Recovery report

Rollback writes `rollback-result.json` into the run capsule and appends a redacted event. The report distinguishes:

- restored actions;
- deleted actions;
- retained allowed paths;
- skipped/unsupported paths; and
- conflicts with reasons.

The CLI exits nonzero when conflicts remain.

## Process cleanup

`agentdiff cleanup <run-id>` rechecks stored owned-process identities and attempts conservative termination. PID plus process creation time must still match. PID reuse, access denial, or missing identity evidence causes refusal rather than a blind kill.

The local runner already attempts cleanup at timeout and after normal direct-child exit. The command exists for inspection and retry, not as proof that every descendant can be found.

## What rollback cannot undo

- API, database, cloud, package registry, issue tracker, email, or remote Git effects;
- network traffic or a port already used;
- symlink, hardlink, directory-tree, device, socket, or FIFO mutations as recoverable objects;
- ignored or uncaptured files;
- files larger than configured capture limits; or
- effects outside the project root.

For high-risk agents, combine AgentDiff with version control, disposable workspaces, backups, and a real sandbox.

---
title: Security & capability limits
description: AgentDiff's explicit trust model, observation guarantees, enforcement boundaries, capsule integrity, and rollback limits.
---

<span class="ad-doc-eyebrow">Trust model</span>

# Security & capability limits

<div class="ad-doc-lede">AgentDiff provides runtime evidence, deterministic policy decisions, conservative process cleanup, and selective regular-file recovery. Its default local backend is not an isolation boundary.</div>

<div class="ad-doc-notice" markdown>
For vulnerability reporting and the canonical security policy, read [`SECURITY.md`](https://github.com/kam6l/agentdiff/blob/main/SECURITY.md). Do not put credentials, private capsules, or exploit details in a public issue.
</div>

## Capability matrix

| Capability | Local runtime | `srt` adapter |
| --- | --- | --- |
| Command launch policy | AgentDiff can block a denied executable | AgentDiff evaluates before delegation |
| Filesystem mutation policy | Post-condition classification | Enforcement depends on external settings |
| Filesystem manifests | AgentDiff | AgentDiff |
| Process evidence | Best-effort owned-descendant observation | Adapter/runtime dependent |
| Port evidence | Machine-wide observation; no causality claim | Adapter/runtime dependent |
| Network blocking | **No** | External runtime responsibility |
| Kernel isolation | **No** | External runtime responsibility |
| Selective regular-file recovery | AgentDiff, when evidence is sufficient | AgentDiff, when evidence is sufficient |

## Filesystem evidence

The transaction scanner confines normalized paths to one resolved root, uses `lstat`, does not recurse through symlinks, requests `O_NOFOLLOW` where available, and compares identity around hashing to detect common replacement races.

These controls reduce link traversal and replacement risk. They cannot make a user-space directory walk fully race-free against a hostile same-user process.

## Capsule integrity

Completed capsules include a SHA-256 checksum manifest. `agentdiff verify` detects local changes to recorded artifacts.

!!! warning "Tamper-evident is not authentic"
    A process that can rewrite the entire capsule can also replace its checksum manifest. Keep or sign evidence outside the wrapped workspace when the child must not be able to rewrite it.

Capsules can contain sensitive paths, task text, platform details, process identities, policy rules, and listening endpoints. Review them before sharing.

## Process and network observations

- Process-tree attribution is best effort; short-lived or rapidly daemonized descendants may escape polling.
- Cleanup checks PID **and** process creation time before signaling, reducing PID-reuse risk.
- Port snapshots are machine-wide observations. AgentDiff does not claim that the child owns a changed endpoint.
- `network.mode: observe` does not block traffic. `network.mode: off` only disables observation.

## Recovery invariant

```text
change a path only when current state == recorded post-run state
```

Later edits become conflicts. Recovery also fails closed for unsupported types, symlink or hardlink surprises, path traversal, missing or changed backups, and files outside configured capture limits.

AgentDiff does not roll back databases, remote APIs, cloud resources, package registries, Git remotes, network traffic, or arbitrary process side effects.

## Safer operating guidance

1. Use an unprivileged disposable workspace.
2. Keep the workspace in version control, but account for untracked and ignored files too.
3. Use a reviewed external sandbox for untrusted commands.
4. Start with explicit write allowances and a conservative default.
5. Treat recovery conflicts as human-review events.
6. Keep `.agentdiff/` out of source control and unintended artifact uploads.
7. Run `agentdiff doctor` on every target platform.

## What AgentDiff complements

AgentDiff does not replace tests, Git, tracing, or sandboxes. It adds a deterministic state-and-recovery layer around them: tests assess expected behavior, Git tracks selected repository content, tracing records model/tool activity, and isolation constrains authority.

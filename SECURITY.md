# Security policy

## Supported versions

AgentDiff is pre-release software. Security fixes are applied to the latest commit on `main`; no stable release line is supported yet.

## Reporting a vulnerability

Do not publish credentials, private run capsules, filesystem contents, environment observations, or exploit details in a public issue.

Use **Report a vulnerability** on the repository Security tab. Private vulnerability reporting is enabled; do not open a public issue for exploit details.

## Trust model

AgentDiff Runtime provides **observation, deterministic policy decisions, evidence persistence, conservative process cleanup, and selective regular-file recovery**. The local backend is not an isolation boundary.

AgentDiff currently assumes:

- the project root and AgentDiff installation are trusted before launch;
- the user running AgentDiff is authorized to observe and modify the project;
- the operating system, Python runtime, and local storage are not compromised;
- run capsules remain local unless the user deliberately shares them; and
- the child command may be buggy or adversarial, but does not have privileges beyond the current user.

AgentDiff does **not** currently defend against a child process that can tamper with AgentDiff's own process memory, kill the monitor, bypass filesystem permissions, mount filesystems, or win every kernel-level time-of-check/time-of-use race.

## Capability boundaries

### Local execution is not sandboxing

By default, `agentdiff run` launches a normal local subprocess. It does not use namespaces, seccomp, containers, virtual machines, mandatory access control, or a remote sandbox. The child inherits the current user's operating-system authority.

Command policy can prevent a denied executable from being launched through AgentDiff. Filesystem policy in local mode is a **post-condition check**: changes are classified after execution, not blocked at the write syscall.

`--runtime srt` is an optional adapter for a separately installed Anthropic Sandbox Runtime. In that mode, the external tool owns OS enforcement and its settings are a separate security boundary. AgentDiff checks that the executable and optional settings path exist, preserves argv boundaries, and labels the delegated backend in evidence; it does not audit upstream code, validate that settings are sufficiently restrictive, or prove that host prerequisites enforce the declared policy. Current project tests use a fake wrapper and do not certify upstream isolation.

### Filesystem observation

The transaction scanner:

- confines normalized relative paths to one resolved project root;
- uses `lstat` and does not recurse through symlinks;
- opens regular files with `O_NOFOLLOW` when the platform exposes it;
- compares identity and metadata around hashing to detect common replacement races;
- excludes `.agentdiff` and common generated/cache directories by default; and
- reports unsupported or unreadable entries rather than treating them as safely captured.

These controls reduce link traversal and replacement risks but cannot make a user-space directory walk fully race-free against a hostile same-user process. Platform behavior differs where no-follow flags are unavailable.

### Run capsules

Runtime evidence is stored under `.agentdiff/runs/<run-id>/`. On POSIX, AgentDiff requests mode `0700` for directories and `0600` for files. Writes use temporary files and atomic replacement where supported. Run IDs and artifact names are validated before use.

Completed transactions include a SHA-256 manifest for immutable artifacts. `agentdiff verify` provides local tamper evidence, not authenticity: a process able to rewrite the entire capsule can also regenerate or replace the checksum manifest. Keep or sign evidence outside the wrapped workspace when an adversarial child must not be able to rewrite it.

Do not commit `.agentdiff/`. Filesystem metadata, paths, process IDs, process creation times, platform details, task text, policy rules, and machine-wide listening endpoints can still be sensitive even after credential redaction.

### Redaction

AgentDiff redacts common credential-bearing command flags and recursively redacts values under common sensitive keys before persistence. Environment observations use stable SHA-256-derived fingerprints rather than raw values. Terminal display escapes control characters.

Redaction is defense in depth, not a data-loss-prevention guarantee. Secrets can appear in filenames, task descriptions, source files, unknown argument formats, child output, or fields with nonstandard names. Child stdout/stderr is passed through and is not stored by the transaction runner, but it may still reach the user's terminal or surrounding CI logs.

Review capsules before sharing them.

### Process observation and cleanup

The local runtime records the launched process and descendants it observes. Cleanup checks both PID and process creation time before signaling a process, reducing PID-reuse risk. If identity cannot be verified or access is denied, refusal is preferred over killing an ambiguous process.

Process-tree observation is best effort. A very short-lived descendant may escape polling, and a process that daemonizes before observation may not remain attributable. AgentDiff does not claim complete process provenance.

### Network observation

`network.mode: observe` compares machine-wide listening socket snapshots before and after a run. This is observation only:

- it does not block outbound or inbound traffic;
- it does not prove that the child opened or closed an endpoint;
- it does not establish port ownership; and
- permissions may make the snapshot incomplete.

`network.mode: off` disables that observation. It does not disable networking.

### Rollback

Rollback supports selected regular-file creations, modifications, and deletions below the recorded root. Its core invariant is:

```text
change a path only when current state == recorded post-run state
```

If a person or another process edits a path after the run, AgentDiff reports a conflict and preserves the current state. Backups are integrity-checked before restoration. Path traversal, symlink surprises, hardlinked files, unsupported file types, missing backups, oversized files, and changed backup contents fail closed.

Rollback is not guaranteed for:

- symlinks, hardlinks, directories as first-class recoverable objects, devices, sockets, or FIFOs;
- files above configured capture limits or files that could not be hashed/backed up;
- database, API, cloud, package-registry, Git-remote, or other external effects;
- network traffic;
- process side effects beyond conservative cleanup; or
- concurrent hostile mutation at the kernel boundary.

Use version control, disposable workspaces, and real sandboxing alongside AgentDiff for high-risk runs.

## Safer operating guidance

1. Run agents in an unprivileged disposable workspace.
2. Keep the workspace in version control, but do not rely on Git alone for untracked or ignored files.
3. Use a reviewed external sandbox when the command is not trusted; the optional SRT adapter does not remove the need to audit its installation and settings.
4. Start with a deny-heavy policy and explicit write allowances.
5. Keep backup and hash size limits bounded.
6. Inspect denied/review changes before rollback.
7. Treat rollback conflicts as human-review events; do not force overwrite.
8. Keep `.agentdiff/` out of source control and artifact uploads unless explicitly required.
9. Run `agentdiff doctor` on each target platform and read its limitations.

## Security testing

Security-sensitive changes should include regression tests for path confinement, symlink behavior, identity checks, redaction, backup integrity, and post-run divergence. Pull requests run CodeQL, Bandit, `pip-audit`, Dependency Review, cross-platform tests, and package validation.

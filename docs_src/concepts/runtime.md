# Runtime model

AgentDiff Runtime wraps one command in an evidence transaction. It is designed to answer three concrete questions:

1. What changed below the project root?
2. Which observed changes crossed deterministic policy?
3. Which eligible collateral file changes can be undone without overwriting later work?

## Transaction lifecycle

```text
policy load → private run capsule → before manifest + backups
           → command policy decision → selected runtime backend
           → process/port observation → after manifest
           → path decisions → blast-radius score → durable result
```

The local runner launches the requested argument vector directly with `shell=False`. A denied executable is blocked before launch. A review decision is recorded but permitted by `agentdiff run`; CI can choose whether review findings fail the gate.

Filesystem decisions are post-condition decisions in local mode. AgentDiff does not intercept write syscalls and cannot prevent the child from making a write before it is observed.

## Filesystem boundary

The transaction scanner operates below one resolved project root. It:

- normalizes and validates relative paths;
- does not follow directory or file symlinks;
- hashes regular files in bounded chunks;
- records size, mode, mtime, device, inode, link count, and SHA-256 where eligible;
- records symlink targets as metadata without traversing them;
- captures verified before-state backups only for eligible regular files; and
- excludes the run store and common cache/build directories by default.

`.agentdiffignore` uses Git-style path patterns through `pathspec`. Ignored files are outside the observed transaction, so ignore rules are part of the security boundary and should be reviewed.

## Local runtime

The backend records:

- the direct child PID and creation time;
- descendants observed while the direct child runs;
- exit status, duration, and timeout state;
- identity-checked cleanup outcomes; and
- optional machine-wide listening endpoints observed before and after.

A local subprocess is **not sandboxed**. It inherits the current user's filesystem and network authority. AgentDiff does not enforce CPU, memory, syscall, mount, or outbound-network isolation.

Process ownership is best effort: polling can miss very short-lived or quickly daemonized descendants. Port observations are machine-wide and are never represented as owned by the child.

## Optional external enforcement

`SandboxRuntime` and `agentdiff run --runtime srt` can delegate execution to a preinstalled [Anthropic Sandbox Runtime](../integrations/sandbox-runtime.md). SRT owns the operating-system enforcement; AgentDiff retains its evidence transaction around the wrapper. The default remains the unsandboxed local backend.

## Run capsules

Each run is stored at:

```text
.agentdiff/runs/<run-id>/
├── metadata.json
├── policy.json
├── before.json
├── after.json
├── runtime.json
├── result.json
├── events.jsonl
├── integrity.json
└── backup/
```

Rollback and cleanup add recovery artifacts without modifying the sealed transaction evidence. Schemas carry explicit version numbers. Writes are atomic where the platform supports replacement, and POSIX permissions are restricted to the current user.

`agentdiff verify <run-id>` checks the sealed SHA-256 manifest. It detects ordinary corruption or partial tampering, but it is not signed or authenticated. A process that can rewrite the complete capsule can replace both an artifact and its recorded digest.

Capsules are evidence, not replay packages. They do not contain a complete environment, dependency graph, child stdout/stderr, external service state, or every file when capture limits apply.

## Status and exit behavior

A transaction has both an operational status and a safety outcome:

- `passed`: command succeeded and no review/deny evidence was found;
- `review`: command succeeded but review findings, warnings, or budget violations exist;
- `denied`: command succeeded but at least one denied mutation exists;
- `blocked`: command policy prevented launch;
- `failed`: the command failed or could not launch; and
- `timed_out`: the configured runtime deadline expired.

The default CLI gate fails denied/blocked findings while allowing review findings. Use `--fail-on review` for a stricter CI gate or `--fail-on never` when collecting evidence without a mutation-policy gate. Child failures and launch blocks remain nonzero.

## Honest capability report

Run:

```bash
agentdiff doctor
```

The report distinguishes default local observation from optional external-runtime detection. `sandboxed: false` and `network_enforcement: false` describe the selected default local backend; `sandbox_runtime_cli_detected` only reports whether `srt` is discoverable. Run doctor on each target platform because prerequisites differ.

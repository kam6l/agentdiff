# Mutation policy

AgentDiff policy is deterministic, versioned, strict, and independent of an LLM. Unknown keys and wrong types are rejected instead of silently ignored.

## Generate and validate

```bash
agentdiff policy init
agentdiff policy validate
agentdiff policy explain .env
```

By default, commands read `ROOT/agentdiff.yaml` when it exists. Without a file, `agentdiff run` uses a conservative built-in policy: common credential and Git paths are denied, other writes are reviewed, and command launch is allowed.

## Schema version 1

```yaml
version: 1
filesystem:
  allow_write:
    - src/**
    - tests/**
  review:
    - docs/**
  deny:
    - .env
    - .env.*
    - .git/**
    - "**/*.pem"
    - "**/*.key"
  default: review
process:
  allow:
    - python*
  review:
    - node
  deny:
    - curl
  default: review
network:
  mode: observe
limits:
  files_changed: 40
  processes_spawned: 8
  duration_seconds: 900
rollback:
  enabled: true
  max_backup_file_mb: 10
scoring:
  weights:
    sensitive_path: 40
```

Quote `"off"` when disabling network observation in YAML. PyYAML follows YAML 1.1 boolean rules, under which an unquoted `off` is parsed as `false` and is rejected by the strict policy schema.

### Filesystem decisions

Paths are project-relative POSIX-style paths. Absolute paths, `..` traversal, empty paths, and NUL bytes are rejected by the policy engine.

Glob decisions use fixed precedence:

```text
deny > review > allow_write > default
```

Precedence does not depend on YAML order. Every decision records the matching section, index, and pattern, for example `filesystem.deny[0]`.

### Process decisions

Process rules match the executable basename, not an arbitrary shell string. `agentdiff run` passes an argument vector directly and does not use a shell.

A `deny` process decision blocks launch. `review` is recorded and allowed by the CLI. Unknown shell command strings in the MCP-style hook are not parsed; they resolve to review.

### Network mode

- `observe`: compare machine-wide listening endpoints before and after.
- `off`: do not collect that observation.

Neither mode blocks network access.

### Limits

Limits are evaluated against captured evidence. `duration_seconds` also bounds the local runtime. Limits are not CPU or memory controls.

A limit violation is a review finding and contributes to the blast-radius score.

### Rollback

`rollback.enabled` controls whether transaction capture stores recoverable before-state. `max_backup_file_mb` bounds each backup candidate. Files that are too large, hardlinked, unreadable, or otherwise ineligible remain observable when possible but are not represented as safely recoverable.

### Scoring weights

Supported weight names are strict. Unknown names or negative/non-integer values are rejected. See [Blast-radius scoring](blast-radius.md) for defaults and interpretation.

## Explain before execution

```bash
agentdiff policy explain src/auth.py
agentdiff policy explain .env --format json
```

The output is suitable for review and CI because it contains the final action, normalized subject, exact rule provenance, matching pattern, and reason.

## Policy design guidance

- Start with `default: review` rather than a broad allow.
- Deny secrets, credentials, VCS control data, deploy keys, and generated evidence stores.
- Allow the smallest stable source/test paths your task needs.
- Keep policy files in version control, but never put secrets in them.
- Treat ignore patterns separately: an ignored path cannot be scored or recovered.
- Review policy diffs as security-sensitive code.

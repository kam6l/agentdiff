# CLI Reference

Complete command documentation for `agentdiff`.

## Global Flags

```bash
agentdiff [GLOBAL_FLAGS] <COMMAND> [COMMAND_FLAGS]

GLOBAL_FLAGS:
  --help, -h           Show help
  --version, -v        Show version
  --config PATH        Policy config file (default: agentdiff-policy.yaml)
  --root PATH          Working directory (default: cwd)
  --format FORMAT      Output format: text | json | yaml (default: text)
  --quiet, -q          Suppress non-essential output
  --verbose            Verbose logging
  --no-color           Disable ANSI colors
```

---

## Commands

### `agentdiff run`

Wrap a command under observation.

```bash
agentdiff run [FLAGS] -- <COMMAND> [ARGS...]
```

**Flags:**
| Flag | Description |
|------|-------------|
| `--task TEXT` | Human-readable task description (required) |
| `--dry-run` | Capture manifests and evaluate policy without executing |
| `--weights JSON` | Custom blast-radius weights |
| `--no-backup` | Disable backup creation |
| `--timeout SECONDS` | Command timeout (default: 300) |
| `--policy PATH` | Override policy file |

**Examples:**
```bash
# Basic usage
agentdiff run --task "Fix parser" -- python3 agent.py

# With custom policy
agentdiff run --task "Refactor" --policy ci-policy.yaml -- python3 agent.py

# Dry run (preview only)
agentdiff run --task "Test" --dry-run -- python3 agent.py

# Custom weights
agentdiff run --weights '{"denied_mutation": 50}' -- python3 agent.py
```

---

### `agentdiff inspect`

Inspect a run capsule.

```bash
agentdiff inspect <RUN_ID> [FLAGS]
```

**Flags:**
| Flag | Description |
|------|-------------|
| `--section SECTION` | Show only section: manifest, diff, policy, blast-radius, processes, ports |
| `--format FORMAT` | Output format: text | json | yaml |

**Examples:**
```bash
# Full human-readable
agentdiff inspect a1b2c3d4

# JSON for scripting
agentdiff inspect a1b2c3d4 --format json

# Just policy decisions
agentdiff inspect a1b2c3d4 --section policy

# Just blast radius components
agentdiff inspect a1b2c3d4 --section blast-radius
```

---

### `agentdiff rollback`

Recover from a run.

```bash
agentdiff rollback <RUN_ID> [FLAGS]
```

**Flags:**
| Flag | Description |
|------|-------------|
| `--safe-only` | Revert only DENY/REVIEW items unchanged since run (recommended) |
| `--decisions LIST` | Comma-separated: allow,review,deny (default: deny,review) |
| `--paths LIST` | Comma-separated paths to revert |
| `--dry-run` | Show what would be reverted without changes |
| `--status` | Show recovery status without changes |
| `--force` | Skip confirmation (full rollback only) |

**Examples:**
```bash
# Recommended: safe rollback
agentdiff rollback a1b2c3d4 --safe-only

# Dry run first
agentdiff rollback a1b2c3d4 --safe-only --dry-run

# Revert only DENY mutations
agentdiff rollback a1b2c3d4 --decisions deny

# Revert specific files
agentdiff rollback a1b2c3d4 --paths ".env,config.yaml"

# Check status
agentdiff rollback a1b2c3d4 --status
```

---

### `agentdiff restore`

Restore files from backup.

```bash
agentdiff restore <RUN_ID> [FLAGS]
```

**Flags:**
| Flag | Description |
|------|-------------|
| `--file PATH` | Restore specific file |
| `--list` | List available backups |
| `--all` | Restore all backed up files |

**Examples:**
```bash
# List backups
agentdiff restore a1b2c3d4 --list

# Restore one file
agentdiff restore a1b2c3d4 --file src/main.py

# Restore all
agentdiff restore a1b2c3d4 --all
```

---

### `agentdiff policy`

Policy management commands.

```bash
agentdiff policy <SUBCOMMAND> [FLAGS]
```

#### `init`
Create starter policy file.

```bash
agentdiff policy init [--force] [--output PATH]
```

#### `explain`
Show which rule matches a path.

```bash
agentdiff policy explain <PATH> [--policy PATH]
```

#### `validate`
Validate policy syntax and semantics.

```bash
agentdiff policy validate [--policy PATH]
```

#### `simulate`
Simulate current policy against historical runs.

```bash
agentdiff policy simulate --trajectory-dir PATH [--policy PATH]
```

---

### `agentdiff list`

List run capsules.

```bash
agentdiff list [FLAGS]
```

**Flags:**
| Flag | Description |
|------|-------------|
| `--limit N` | Maximum runs to show (default: 20) |
| `--since DATE` | Show runs after date (ISO 8601) |
| `--format FORMAT` | text | json | yaml |

---

### `agentdiff doctor`

Self-check diagnostics.

```bash
agentdiff doctor [FLAGS]
```

**Flags:**
| Flag | Description |
|------|-------------|
| `--verbose` | Detailed output |
| `--fix` | Attempt to fix issues |

---

### `agentdiff completion`

Generate shell completion.

```bash
agentdiff completion <SHELL>
# SHELL: bash | zsh | fish
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Policy violation (DENY mutation with `--fail-on-deny`) |
| 4 | Blast radius threshold exceeded (`--fail-on-blast-radius`) |
| 5 | Run not found |
| 6 | Backup missing/corrupted |
| 7 | Conflict detected (with `--fail-on-conflict`) |

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENTDIFF_POLICY` | Default policy file | `agentdiff-policy.yaml` |
| `AGENTDIFF_ROOT` | Default working directory | `cwd` |
| `AGENTDIFF_DATA_DIR` | Run capsule storage | `.agentdiff` |
| `AGENTDIFF_NO_COLOR` | Disable colors | `false` |
| `AGENTDIFF_LOG_LEVEL` | Log level: debug, info, warn, error | `info` |

---

## Configuration File Discovery

AgentDiff searches for policy config in order:

1. `--policy` flag
2. `AGENTDIFF_POLICY` env var
3. `agentdiff-policy.yaml` in current directory
4. `agentdiff-policy.yaml` in parent directories (up to root)
5. `.agentdiff/policy/default.yaml`
6. Built-in defaults

---

## Next Steps

- [Quickstart](quickstart.md) — Run your first transaction
- [Mutation Policy](concepts/policy.md) — Policy configuration
- [Blast-Radius Scoring](concepts/blast-radius.md) — Scoring model
- [Python API](api.md) — Programmatic usage
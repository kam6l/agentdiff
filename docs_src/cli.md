# CLI Reference

## Commands

### `agentdiff init`
Initialize configuration file.

```bash
agentdiff init [--force]
```

| Option | Description |
|--------|-------------|
| `--force` | Overwrite existing config |

---

### `agentdiff snapshot`
Capture environment snapshot.

```bash
agentdiff snapshot [--output FILE] [--root PATH] [--format json|yaml]
```

| Option | Description |
|--------|-------------|
| `-o, --output` | Output file (default: stdout) |
| `-r, --root` | Root path to watch (default: cwd) |
| `-f, --format` | Output format (default: json) |

---

### `agentdiff diff`
Diff two snapshots.

```bash
agentdiff diff --pre FILE --post FILE [--root PATH] [--format json|text]
```

| Option | Description |
|--------|-------------|
| `--pre` | Pre-snapshot file (required) |
| `--post` | Post-snapshot file (required) |
| `-r, --root` | Root path for relative paths |
| `-f, --format` | Output format (default: text) |

---

### `agentdiff eval`
Evaluate a trajectory.

```bash
agentdiff eval --trajectory FILE [--pre FILE] [--post FILE] [--root PATH] [--format json|text] [--fail-below FLOAT]
```

| Option | Description |
|--------|-------------|
| `-t, --trajectory` | Trajectory JSON file (required) |
| `--pre` | Pre-snapshot file |
| `--post` | Post-snapshot file |
| `-r, --root` | Root path for relative paths |
| `-f, --format` | Output format (default: text) |
| `--fail-below` | Exit code 1 if cleanliness below threshold |

---

### `agentdiff replay`
Replay trajectory steps.

```bash
agentdiff replay --trajectory FILE [--step INT] [--format json|text]
```

| Option | Description |
|--------|-------------|
| `-t, --trajectory` | Trajectory JSON file (required) |
| `-s, --step` | Start from specific step |
| `-f, --format` | Output format (default: text) |

---

### `agentdiff demo`
Run built-in demonstration.

```bash
agentdiff demo [--output-dir PATH]
```

| Option | Description |
|--------|-------------|
| `-o, --output-dir` | Directory for demo artifacts (default: temp) |

---

## Global Options

| Option | Description |
|--------|-------------|
| `-h, --help` | Show help |
| `-v, --verbose` | Verbose output |
| `--version` | Show version |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Evaluation failed (cleanliness below threshold) |
| 2 | Invalid arguments |
| 3 | File not found / IO error |
| 4 | Invalid JSON / data format |

---

## Examples

```bash
# Full workflow
agentdiff snapshot -o before.json
python run_agent.py
agentdiff snapshot -o after.json
agentdiff eval -t trajectory.json --pre before.json --post after.json --fail-below 0.8

# Just diff two snapshots
agentdiff diff --pre before.json --post after.json

# CI/CD integration
agentdiff eval -t run.json --pre before.json --post after.json --fail-below 0.85 || exit 1
```
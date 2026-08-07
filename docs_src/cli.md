# CLI reference

The `agentdiff` executable exposes three implemented commands. Run any command with `--help` for the installed version's exact interface.

## `snapshot`

Capture filesystem and optional system state into one JSON file.

```bash
agentdiff snapshot --root . -o before.json
```

| Option | Meaning |
| --- | --- |
| `--root PATH` | Directory to scan; defaults to the current directory |
| `--ignore GLOBS` | Comma-separated `pathlib` glob patterns |
| `--max-size BYTES` | Maximum file size considered for content hashing |
| `--no-env` | Do not capture environment-variable names and values |
| `--no-proc` | Do not capture process IDs |
| `--no-ports` | Do not capture listening ports |
| `-o, --output FILE` | Output path; otherwise a timestamped JSON file is created |

Secret-like environment names are denied by default. `.git`, `.agentdiff`, virtual environments, Python caches, and Node dependencies are ignored by the default collector.

## `diff`

Compare two snapshot files.

```bash
agentdiff diff before.json after.json
agentdiff diff before.json after.json --format json
```

The two snapshot paths are positional. `--format` accepts `summary` or `json`; `--root` controls the engine root used while producing the diff.

## `eval`

Evaluate a saved trajectory, optionally against a snapshot pair.

```bash
agentdiff eval trajectory.json \
  --pre before.json \
  --post after.json \
  --root . \
  --target src/evaluator.py,tests/test_evaluator.py \
  --threshold 0.8 \
  --format json \
  --fail-on-failure
```

| Option | Meaning |
| --- | --- |
| `--pre FILE` / `--post FILE` | Snapshot pair; provide both or neither |
| `--root PATH` | Base directory for relative target paths |
| `--target PATHS` | Comma-separated intended mutation paths |
| `--threshold FLOAT` | Required cleanliness score; default `0.8` |
| `--format summary|json` | Human or machine-readable result |
| `--fail-on-failure` | Exit 1 when evaluation fails |

`--fail-below-threshold` remains an alias for `--fail-on-failure`.

## Exit status

- `0`: command completed; or evaluation passed when gating is enabled
- `1`: gated evaluation failed
- `2`: invalid command-line arguments (from `argparse`)
- other nonzero status: invalid input or an operating-system error

AgentDiff deliberately does not advertise replay, report generation, YAML output, or configuration-file loading in version 0.1 because those capabilities are not implemented.

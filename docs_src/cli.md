# CLI reference

Run `agentdiff --help` or any subcommand with `--help` for the installed version's exact interface.

## Runtime commands

### `run`

Wrap an argument vector in an evidence transaction:

```bash
agentdiff run --task "Fix the parser" -- python3 agent.py
```

| Option | Meaning |
| --- | --- |
| `--root PATH` | Project root; defaults to `.` |
| `--policy FILE` | Policy YAML/JSON; otherwise uses `ROOT/agentdiff.yaml` when present, then the built-in default |
| `--task TEXT` | Human-readable intended task stored in metadata |
| `--timeout SECONDS` | Runtime deadline; combined with a policy duration limit |
| `--runtime local\|srt` | Execution backend; default `local` |
| `--srt-executable PATH` | External `srt` executable; used only with `--runtime srt` |
| `--srt-settings FILE` | External SRT settings JSON; used only with `--runtime srt` |
| `--format summary\|json` | Human summary or JSON result |
| `--fail-on never\|review\|deny` | Mutation-policy gate; default `deny` |
| `-- COMMAND...` | Command argument vector; no shell is used |

In JSON mode, child stdout/stderr is redirected to the CLI's stderr so stdout remains one machine-readable result object. Child output is not stored in the run capsule.

Local mode is observation-only. SRT mode delegates OS enforcement to the external Anthropic Sandbox Runtime and requires its independently reviewed installation and settings. AgentDiff does not derive SRT restrictions from `agentdiff.yaml`.

### `runs`

```bash
agentdiff runs --root .
agentdiff runs --root . --limit 20 --format json
```

Lists valid project-local runs newest first. Symlinked run directories are not followed.

### `inspect`

```bash
agentdiff inspect <run-id> --root .
agentdiff inspect <run-id> --root . --format json
```

Reads metadata, policy, manifests, runtime evidence, result, and any rollback/cleanup reports from the capsule.

### `verify`

```bash
agentdiff verify <run-id> --root .
agentdiff verify <run-id> --root . --format json
```

Checks the SHA-256 manifest sealed when the transaction completed. A valid manifest exits `0`; missing or mismatched integrity evidence exits `4`. This detects ordinary corruption or partial tampering, but it is not authentication when an attacker can replace the whole capsule.

### `rollback`

```bash
agentdiff rollback <run-id> --safe-only
agentdiff rollback <run-id> --all --path one.txt --path two.txt
```

Exactly one of `--safe-only` or `--all` is required. `--safe-only` selects review/deny mutations. `--path` narrows the selection. Conflicts are preserved and produce a nonzero status.

### `cleanup`

```bash
agentdiff cleanup <run-id> --grace-period 1.0
```

Rechecks stored PID plus creation-time identities before attempting process cleanup. It does not search the whole machine for guessed descendants.

### `doctor`

```bash
agentdiff doctor
agentdiff doctor --format json
```

Reports actual local backend capabilities and limitations plus optional external-runtime detection. `sandboxed: false` and `network_enforcement: false` describe the default local backend; `sandbox_runtime_cli_detected` reports whether `srt` is on `PATH`.

## Policy commands

### `policy init`

```bash
agentdiff policy init
agentdiff policy init --output custom.yaml
agentdiff policy init --force
```

Writes the version-1 starter YAML. Existing files are preserved unless `--force` is explicit.

### `policy validate`

```bash
agentdiff policy validate
agentdiff policy validate --policy custom.yaml
```

Loads the policy with strict key and type validation.

### `policy explain`

```bash
agentdiff policy explain .env
agentdiff policy explain src/app.py --format json
```

Returns the final action and exact matching rule provenance for one project-relative path.

## Legacy evaluation commands

### `snapshot`

Capture filesystem and optional legacy system observations into JSON:

```bash
agentdiff snapshot --root . -o before.json
```

| Option | Meaning |
| --- | --- |
| `--root PATH` | Directory to scan |
| `--ignore GLOBS` | Comma-separated `pathlib` glob patterns |
| `--max-size BYTES` | Maximum file size considered for content hashing |
| `--no-env` | Disable environment-name/fingerprint collection |
| `--no-proc` | Disable machine-wide PID-set collection |
| `--no-ports` | Disable machine-wide listening-port collection |
| `-o, --output FILE` | Output path |

Secret-like environment names are excluded and other environment values are stored as stable fingerprints, not raw values.

### `diff`

```bash
agentdiff diff before.json after.json
agentdiff diff before.json after.json --format json
```

Compares two saved snapshots.

### `eval`

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

`--pre` and `--post` must be supplied together. `--fail-below-threshold` remains an alias for `--fail-on-failure`.

## Exit status

Runtime commands use:

- `0`: command completed and the configured gate did not fail;
- `1`: operational failure, timeout, legacy evaluation failure, or uncleaned process cleanup;
- `2`: invalid CLI input, policy, artifact, or other user-facing error;
- `3`: runtime mutation gate failed at `deny`;
- `4`: rollback completed with conflicts;
- `126`: command policy blocked launch;
- another child status: the child command exited nonzero and its valid POSIX status was propagated.

AgentDiff does not expose replay, sandbox, report-server, or network-blocking commands because those capabilities are not implemented.

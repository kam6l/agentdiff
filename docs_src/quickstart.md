# Quickstart

AgentDiff is installed from source. A PyPI release is not available yet.

## Install

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --locked --all-groups
uv run agentdiff doctor
```

`doctor` should report `local_runtime` as true and `sandboxed` / `network_enforcement` as false. Those false values are expected for the default local backend.

## Create a policy

Create a disposable workspace and generate the starter policy:

```bash
WORKSPACE="$(mktemp -d)"
mkdir -p "$WORKSPACE/src"
uv run agentdiff policy init --output "$WORKSPACE/agentdiff.yaml"
uv run agentdiff policy validate --policy "$WORKSPACE/agentdiff.yaml"
```

The starter policy allows `src/**` and `tests/**`, reviews `docs/**`, denies common credential and Git-control paths, and reviews other writes.

Check a rule without executing anything:

```bash
uv run agentdiff policy explain .env --policy "$WORKSPACE/agentdiff.yaml"
uv run agentdiff policy explain src/result.txt --policy "$WORKSPACE/agentdiff.yaml"
```

## Run a transaction

```bash
uv run agentdiff run \
  --root "$WORKSPACE" \
  --policy "$WORKSPACE/agentdiff.yaml" \
  --task "Create an allowed result" \
  -- python3 -c 'from pathlib import Path; Path("src/result.txt").write_text("ok\n")'
```

The summary includes a run ID, command status, safety outcome, blast-radius score, and each observed path decision.

List and inspect local evidence:

```bash
uv run agentdiff runs --root "$WORKSPACE"
uv run agentdiff inspect <run-id> --root "$WORKSPACE"
uv run agentdiff inspect <run-id> --root "$WORKSPACE" --format json
```

Run capsules remain at `$WORKSPACE/.agentdiff/runs/<run-id>/`.

## Observe a denied mutation

```bash
uv run agentdiff run \
  --root "$WORKSPACE" \
  --policy "$WORKSPACE/agentdiff.yaml" \
  --task "Demonstrate collateral mutation" \
  -- python3 -c 'from pathlib import Path; Path(".env").write_text("DEMO_ONLY=yes\n")'
```

The default gate returns exit status `3` for the denied path. The example value is not a credential; do not put real secrets into tests or terminal history.

Remove only review/deny collateral changes while retaining allowed paths:

```bash
uv run agentdiff rollback <run-id> --root "$WORKSPACE" --safe-only
```

If the path changed after the run, rollback reports a conflict and preserves it.

## Python transaction API

```python
from pathlib import Path

from agentdiff.policy import load_policy_file
from agentdiff.transaction import AgentRunTransaction

root = Path("workspace")
policy = load_policy_file(root / "agentdiff.yaml")
result = AgentRunTransaction(
    root=root,
    policy=policy,
    task="Run my agent",
).run(["python3", "agent.py"], timeout_seconds=300)

print(result.run_id)
print(result.safety_outcome.value)
print(result.blast_radius.to_dict())
```

The transaction API accepts an argument vector and invokes it with `shell=False`.

## Optional external sandbox adapter

If Anthropic Sandbox Runtime is installed and configured, preserve the same AgentDiff transaction while delegating execution to `srt`:

```bash
uv run agentdiff run \
  --runtime srt \
  --srt-settings /absolute/path/to/srt-settings.json \
  --root "$WORKSPACE" \
  --policy "$WORKSPACE/agentdiff.yaml" \
  -- python3 agent.py
```

The external runtime owns enforcement; AgentDiff does not translate its policy into SRT settings or certify the supplied settings. See [Anthropic Sandbox Runtime](integrations/sandbox-runtime.md).

## Legacy evaluation workflow

The original explicit snapshot and trajectory evaluator remains available:

```bash
uv run agentdiff snapshot --root . -o before.json
# run your instrumented agent and save trajectory.json
uv run agentdiff snapshot --root . -o after.json
uv run agentdiff eval trajectory.json \
  --pre before.json \
  --post after.json \
  --root . \
  --target src/evaluator.py \
  --fail-on-failure
```

## Continue

- [Runtime model](concepts/runtime.md)
- [Policy](concepts/policy.md)
- [Blast-radius scoring](concepts/blast-radius.md)
- [Selective recovery](concepts/recovery.md)
- [CLI reference](cli.md)
- [Python API](api.md)
- [Security model](https://github.com/kam6l/agentdiff/blob/main/SECURITY.md)

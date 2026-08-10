# AgentDiff examples

These examples use synthetic data and explicit local workspaces. The local runtime is not a sandbox.

## Transaction API

```bash
WORKSPACE="$(mktemp -d)"
uv run python3 examples/run_transaction.py --workspace "$WORKSPACE"
uv run agentdiff runs --root "$WORKSPACE"
```

The script creates only `src/result.txt` below the supplied workspace and prints the JSON transaction result. Its run capsule remains in `$WORKSPACE/.agentdiff/runs/` for inspection.

## MCP-style policy hook

```bash
uv run python3 examples/mcp_policy_hook.py
```

This example evaluates three proposed tool calls and prints redacted decisions. It does not connect to or dispatch an MCP server.

## Policy

`examples/agentdiff.yaml` is a strict version-1 policy used by both examples. Copy and adapt it rather than widening the allow list blindly.

## Optional Anthropic Sandbox Runtime

With a separately installed and configured `srt`, wrap your own command with external OS enforcement:

```bash
uv run agentdiff run \
  --runtime srt \
  --srt-settings /absolute/path/to/srt-settings.json \
  --policy examples/agentdiff.yaml \
  -- python3 your_agent.py
```

AgentDiff does not translate `examples/agentdiff.yaml` into SRT settings; review both policies independently.

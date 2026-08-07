# Quickstart

AgentDiff is currently installed from source. A PyPI release is not available yet.

## Set up the project

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --locked --group dev
```

Run the bundled scripted demonstration:

```bash
uv run agentdiff-demo
```

Add `--json` when you want machine-readable output.

## Capture a real agent run

Create the baseline before the agent starts:

```bash
uv run agentdiff snapshot --root . -o before.json
```

Run your agent and save its trajectory as `trajectory.json`, then capture the final state:

```bash
uv run agentdiff snapshot --root . -o after.json
```

Inspect the raw state mutation summary:

```bash
uv run agentdiff diff before.json after.json
```

Evaluate the trajectory and declare the files the agent was meant to change:

```bash
uv run agentdiff eval trajectory.json \
  --pre before.json \
  --post after.json \
  --root . \
  --target src/evaluator.py \
  --threshold 0.8
```

For CI, add `--fail-on-failure`; AgentDiff exits with status 1 when the evaluation does not pass.

## Record a trajectory

```python
from agentdiff import TrajectoryTracker

tracker = TrajectoryTracker(task_description="Fix the evaluator")
tracker.start_step("Inspect the failing module")
tracker.record_tool_call(
    "read_file",
    {"path": "src/evaluator.py"},
    result="...",
    duration_ms=42,
)
tracker.end_step("Found the threshold bug")

trajectory = tracker.finish(final_result="Tests pass")
trajectory.save("trajectory.json")
```

For framework-neutral instrumentation with automatic state capture, use [`AgentDiffSession`](api.md#framework-neutral-session).

!!! note "Privacy defaults"
    Environment variables whose names resemble tokens, secrets, passwords, credentials, private keys, or API keys are excluded. Use `--no-env`, `--no-proc`, and `--no-ports` when those collectors are unnecessary.

## Continue

- [CLI reference](cli.md)
- [Python API](api.md)
- [LangChain callback](integrations/langchain.md)
- [CI quality gate](tutorials/ci-cd.md)

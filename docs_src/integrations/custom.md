# Custom frameworks

AgentDiff's runtime path is framework neutral. If a framework eventually launches a local command, the narrowest integration is the CLI:

```bash
agentdiff run --root /workspace --task "Run custom agent" -- python3 run_agent.py
```

This records filesystem and local-runtime evidence without importing the framework.

## Python transaction API

When orchestration already lives in Python, invoke the generic runner directly:

```python
from pathlib import Path

from agentdiff.policy import load_policy_file
from agentdiff.transaction import AgentRunTransaction

root = Path("/workspace")
result = AgentRunTransaction(
    root=root,
    policy=load_policy_file(root / "agentdiff.yaml"),
    task="Run custom agent",
).run(["python3", "run_agent.py"], timeout_seconds=900)

print(result.run_id, result.safety_outcome.value, result.blast_radius.score)
```

The local backend uses an explicit argument vector and does not use a shell. It is not a sandbox.

## Integrate before tool dispatch

For a framework that exposes typed tool calls, connect policy at the last common point before execution:

1. Map the framework's file and command tools to normalized paths or argument vectors.
2. Ask `PolicyEngine` for a deterministic decision.
3. Block `deny`, explicitly handle `review`, and record the decision provenance.
4. Dispatch only after that decision.
5. Wrap the overall run with `AgentRunTransaction` when local filesystem evidence and recovery are required.

Do not parse an arbitrary shell string and call that deterministic command authorization. Require a structured `argv` value or resolve to review/deny. The [MCP-style hook](mcp-policy.md) demonstrates this pattern without implementing transport.

## Legacy trajectory instrumentation

The original evaluator API remains available for frameworks that expose callbacks:

```python
from agentdiff import AgentDiffConfig, AgentDiffSession

config = AgentDiffConfig(
    root="/workspace",
    target_paths=["src/auth.py"],
    capture_env_vars=False,
)

with AgentDiffSession("Fix authentication", config) as session:
    agent.run(
        on_tool=lambda name, args, output, error, duration_ms: session.record(
            thought="Agent tool step",
            tool_name=name,
            tool_args=args,
            tool_result=output,
            observation="Tool completed" if error is None else "Tool failed",
            error=type(error).__name__ if error else None,
            duration_ms=duration_ms,
        )
    )

report = session.evaluate()
```

This records user-supplied trajectory data for evaluation. It does **not** intercept or authorize tools. Trajectory arguments and results can be persisted without runtime-policy redaction, so sanitize them before recording.

## Adapter verification checklist

1. Identify the actual command or dispatch seam; do not rely on an advisory callback if calls can bypass it.
2. Test allow, review, deny, malformed, and unknown-tool paths.
3. Keep file paths root-relative and require structured command arguments.
4. Confirm that rejected calls never reach the executor.
5. Use synthetic secret values to test redaction.
6. Test one intended mutation, one denied mutation, and one post-run rollback conflict.
7. Document which collectors and platforms the adapter cannot support.
8. Never describe observation as syscall blocking or local execution as isolation.

See [LangChain / LangGraph](langchain.md) for the optional legacy callback and [Runtime model](../concepts/runtime.md) for the transaction lifecycle.

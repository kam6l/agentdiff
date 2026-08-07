# Custom frameworks

You do not need an adapter to evaluate a custom agent. Wrap the run with `AgentDiffSession` and record events at the point where your framework executes tools.

```python
from agentdiff import AgentDiffConfig, AgentDiffSession

config = AgentDiffConfig(
    root="/workspace",
    target_paths=["src/auth.py"],
    capture_env_vars=False,
)

with AgentDiffSession("Fix authentication", config) as run:
    result = agent.run(
        on_tool=lambda name, args, output, error, duration_ms: run.record(
            thought="Agent tool step",
            tool_name=name,
            tool_args=args,
            tool_result=output,
            observation=str(output),
            error=str(error) if error else None,
            duration_ms=duration_ms,
        )
    )

report = run.evaluate()
```

## Instrument a tool executor

When the framework has no callback system, wrap its execution seam:

```python
from time import perf_counter


def execute_with_tracking(run, execute, name, arguments):
    started = perf_counter()
    try:
        result = execute(name, arguments)
    except Exception as error:
        run.record(
            "Tool failed",
            name,
            arguments,
            error=str(error),
            duration_ms=(perf_counter() - started) * 1000,
        )
        raise

    run.record(
        "Tool completed",
        name,
        arguments,
        tool_result=result,
        observation=str(result),
        duration_ms=(perf_counter() - started) * 1000,
    )
    return result
```

## Build an adapter class

For repeated integrations, subclass `BaseAgentDiffAdapter`. Implement `attach(agent)` so it registers your framework's callbacks and returns the configured agent. The base class provides `start()`, `record_step()`, and `evaluate()`.

```python
from agentdiff import BaseAgentDiffAdapter


class MyAdapter(BaseAgentDiffAdapter):
    def attach(self, agent):
        agent.on_tool(self.record_step)
        return agent
```

Adapters should be thin. Keep framework-specific event conversion in the adapter and keep state capture, metrics, and pass/fail logic in AgentDiff.

## Verification checklist

1. Capture the baseline before the framework starts.
2. Record successful and failed tool calls.
3. Preserve durations in milliseconds.
4. Evaluate only after child processes and servers have settled.
5. Test one intended and one unintended mutation.
6. Disable collectors the runtime cannot access.

See the [LangChain callback](langchain.md) for a concrete implementation.

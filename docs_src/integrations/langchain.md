# LangChain / LangGraph

AgentDiff includes an optional `langchain-core` callback. From a source checkout, install the extra with:

```bash
uv sync --locked --extra langchain --group dev
```

## Callback usage

```python
from agentdiff.integrations.langchain_callback import AgentDiffCallbackHandler

callback = AgentDiffCallbackHandler(
    task_description="Fix authentication",
    root="/workspace",
    target_paths=["src/auth.py"],
    cleanliness_threshold=0.8,
)
callback.start()

result = graph.invoke(
    {"input": "Fix the authentication bug"},
    config={"callbacks": [callback]},
)

report = callback.get_evaluation_result()
print(report.metrics.cleanliness_score)
```

For a LangChain runnable, pass the same handler through its callback configuration:

```python
result = chain.invoke(inputs, config={"callbacks": [callback]})
```

## Events recorded

| LangChain callback | AgentDiff behavior |
| --- | --- |
| `on_llm_start` | Keeps a bounded prompt excerpt as step context |
| `on_llm_end` | Reads provider token usage when available |
| `on_agent_action` | Uses the ReAct log for the next tool step |
| `on_tool_start` | Parses arguments and starts a timer |
| `on_tool_end` | Records a successful tool step and observation |
| `on_tool_error` | Records the failed tool step and error |
| `on_agent_finish` | Stores the final result on the trajectory |
| `on_chain_error` | Stores the final error |

Each completed tool call becomes one trajectory step. Token accounting depends on the model provider exposing `llm_output.token_usage`.

## Explicit context

```python
from agentdiff.integrations.langchain_callback import AgentDiffLangChainSession

with AgentDiffLangChainSession(
    task_description="Refactor service",
    root="/workspace",
    target_paths=["src/service.py"],
) as callback:
    chain.invoke(inputs, config={"callbacks": [callback]})

report = callback.get_evaluation_result()
```

## Operational notes

- Call `start()` immediately before execution when not using the context manager.
- Call `get_evaluation_result()` after the run and after temporary processes have exited.
- Use `capture_env_vars=False`, `capture_processes=False`, or `capture_ports=False` for restricted runners.
- Call `reset()` before reusing one callback for another run.
- This integration depends only on `langchain-core`; AgentDiff does not create or configure your agent.

For frameworks without LangChain callbacks, use the [framework-neutral integration](custom.md).

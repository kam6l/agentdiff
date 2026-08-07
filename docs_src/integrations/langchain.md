# LangChain / LangGraph Integration

AgentDiff provides a first-class callback handler for LangChain and LangGraph.

## Installation

```bash
pip install agentdiff[langchain]
# or
uv add agentdiff[langchain]
```

## Quick Start

```python
from agentdiff.integrations import AgentDiffSession, LangChainCallbackHandler
from langgraph.graph import StateGraph

# 1. Create session (starts pre-snapshot automatically)
with AgentDiffSession(
    paths=["/repo"],
    target_paths=["/repo/src/"]
) as session:
    
    # 2. Create callback handler
    callback = LangChainCallbackHandler(session)
    
    # 3. Run your LangGraph agent
    graph = create_my_agent_graph()
    result = graph.invoke(
        {"input": "Fix the authentication bug"},
        config={"callbacks": [callback]}
    )

# 4. Session exits → auto-runs evaluation
report = session.evaluate()
print(f"Cleanliness: {report.cleanliness_score:.1%}")
```

## With LangChain Chains

```python
from langchain.chains import LLMChain
from agentdiff.integrations import AgentDiffSession, LangChainCallbackHandler

with AgentDiffSession(paths=["/repo"], target_paths=["/repo/src/"]) as session:
    callback = LangChainCallbackHandler(session)
    
    chain = LLMChain(llm=llm, prompt=prompt)
    result = chain.invoke(
        {"input": "Refactor the user service"},
        callbacks=[callback]
    )

report = session.evaluate()
```

## What Gets Captured Automatically

| Event | Captured As |
|-------|-------------|
| `on_chain_start` | Trajectory step start (thought) |
| `on_chain_end` | Trajectory step end (observation) |
| `on_tool_start` | Tool call with arguments |
| `on_tool_end` | Tool result + duration |
| `on_tool_error` | Tool error |
| `on_llm_start` | LLM call (tokens tracked) |
| `on_llm_end` | LLM response (tokens tracked) |

## Advanced: Custom Step Boundaries

```python
from agentdiff.integrations import LangChainCallbackHandler

class CustomCallbackHandler(LangChainCallbackHandler):
    def on_chain_start(self, serialized, inputs, **kwargs):
        # Only create steps for specific chain types
        if serialized.get("name") == "AgentExecutor":
            super().on_chain_start(serialized, inputs, **kwargs)
    
    def on_tool_end(self, output, **kwargs):
        # Add custom metadata
        self._current_tool_call.metadata["custom_field"] = "value"
        super().on_tool_end(output, **kwargs)

with AgentDiffSession(...) as session:
    callback = CustomCallbackHandler(session)
    # ...
```

## Accessing the Report

```python
with AgentDiffSession(...) as session:
    callback = LangChainCallbackHandler(session)
    # ... run agent ...
    
    # Get report anytime (even before session exits)
    report = session.get_report()
    
    # Or wait for full evaluation
    report = session.evaluate()

# Export formats
report.to_json("report.json")
report.to_html("report.html")
report.to_junit("report.xml")
```

## Configuration

```yaml
# agentdiff.yaml
langchain:
  capture_llm_tokens: true
  capture_tool_args: true
  capture_tool_results: true
  step_boundary_chains:
    - "AgentExecutor"
    - "PlanAndExecute"
    - "CustomAgent"
```

## Related

- [Custom Framework Integration](custom.md) — Build your own adapter
- [CI/CD Tutorial](../tutorials/ci-cd.md) — Use in pipelines
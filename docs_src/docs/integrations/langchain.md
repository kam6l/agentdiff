---
title: LangChain and LangGraph callback
description: Experimental legacy trajectory evaluation callback.
---

# LangChain and LangGraph callback

**Status: Experimental compatibility API.** The callback records LangChain tool activity and evaluates legacy snapshot cleanliness. It does not create a transaction capsule, apply runtime mutation policy, compute the new blast-radius score, or provide rollback.

Install the optional dependency in a checkout:

```bash
uv sync --extra langchain
```

## Use it

```python
from agentdiff.integrations.langchain_callback import AgentDiffCallbackHandler

callback = AgentDiffCallbackHandler(
    task_description="Fix the parser",
    target_paths=["src/parser.py"],
    root="/workspace/project",
)
callback.start()

result = app.invoke(
    {"input": "Fix the parser"},
    config={"callbacks": [callback]},
)

evaluation = callback.get_evaluation_result()
print(evaluation.metrics.cleanliness_score, evaluation.passed)
```

Call `start()` immediately before the agent run. `get_evaluation_result()` captures the final snapshot and finalizes the recorded trajectory. `get_diff()`, `get_trajectory()`, and `reset()` expose the implemented compatibility lifecycle.

For the primary runtime product, wrap the whole agent command with `agentdiff run` or [`AgentRunTransaction`](../sdk-reference.md).

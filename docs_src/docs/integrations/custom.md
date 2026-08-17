---
title: Custom integration
description: Wrap any framework command with the primary transaction API.
---

# Custom integration

The reliable integration boundary is an explicit argv. It works with any framework that has a CLI and keeps AgentDiff independent from agent self-reporting.

## CLI boundary

```bash
agentdiff run --task "Fix authentication" -- your-agent --project .
```

For automation, add `--format json` and choose `--fail-on never|review|deny` explicitly.

## Python boundary

```python
from agentdiff import AgentRunTransaction, load_policy_file

transaction = AgentRunTransaction(
    root="/workspace/project",
    policy=load_policy_file("/workspace/project/agentdiff.yaml"),
    task="Fix authentication",
)
result = transaction.run(
    ["your-agent", "--project", "."],
    timeout_seconds=900,
)

print(result.to_dict())
```

This path produces the same capsule, policy decisions, score, and recovery evidence as the CLI.

## Experimental compatibility session

`AgentDiffSession` remains available for frameworks that want to record trajectory steps and calculate the original cleanliness metric:

```python
from agentdiff import AgentDiffConfig, AgentDiffSession

config = AgentDiffConfig(root="/workspace/project", target_paths=["src/auth.py"])
with AgentDiffSession("Fix authentication", config=config) as session:
    run_your_agent()
    session.record(
        thought="Update authentication",
        tool_name="write_file",
        tool_args={"path": "src/auth.py"},
        observation="updated",
    )

evaluation = session.evaluate()
```

The compatibility session is separate from the transaction/recovery core. There is no plugin entry-point discovery or built-in CrewAI/AutoGen adapter in `0.2.x`.

---
title: Anthropic Sandbox Runtime adapter
description: Experimental delegation through an installed srt executable.
---

# Anthropic Sandbox Runtime adapter

**Status: Experimental.** AgentDiff can wrap argv with a separately installed `srt` executable. AgentDiff records that external sandboxing was requested; effective enforcement depends on the installed runtime, operating system, version, and settings.

The adapter does not bundle `srt`, translate AgentDiff policy into sandbox policy, parse enforcement logs, or prove which controls were applied.

## CLI

Install and configure [`srt`](https://github.com/anthropics/sandbox-runtime) separately, then run:

```bash
agentdiff run \
  --runtime srt \
  --srt-executable srt \
  --srt-settings /absolute/path/to/settings.json \
  --task "Fix the parser" \
  -- python agent_task.py
```

The executed wrapper argv is:

```text
srt --settings /absolute/path/to/settings.json -- python agent_task.py
```

Use the normal `--timeout` option for the overall observed command. There is no `--sandbox-timeout` or `--sandbox-logs` flag.

## Python

```python
import sys

from agentdiff import AgentRunTransaction, load_policy_file
from agentdiff.runtime import SandboxRuntime

runtime = SandboxRuntime(
    root="/workspace/project",
    executable="srt",
    settings="/absolute/path/to/settings.json",
)
result = AgentRunTransaction(
    root="/workspace/project",
    policy=load_policy_file("/workspace/project/agentdiff.yaml"),
    task="Fix the parser",
    runtime=runtime,
).run([sys.executable, "agent_task.py"], timeout_seconds=300)

print(result.runtime.backend)      # anthropic-sandbox-runtime
print(result.runtime.enforcement)  # external_sandbox_requested
```

## Boundary

AgentDiff captures host-visible before/after state around the wrapper. It does not claim that host-visible observations equal all in-sandbox activity. Review the external runtime's own settings and guarantees independently.

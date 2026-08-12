---
title: MCP-style policy hook
description: Experimental transport-neutral pre-dispatch policy decisions.
---

# MCP-style policy hook

**Status: Experimental.** `MCPPolicyHook` is a small synchronous hook that a real transport adapter can call before dispatching recognized filesystem or command tools. It is not an MCP client, server, middleware package, or proxy.

## Use it

```python
from agentdiff import MCPPolicyHook, PolicyAction, ToolCallBlockedError, load_policy_file

hook = MCPPolicyHook(load_policy_file("agentdiff.yaml"))

decision = hook.evaluate(
    "filesystem.write_file",
    {"path": "src/app.py", "content": "not retained in the decision"},
)
if decision.action is PolicyAction.ALLOW:
    dispatch_tool()
```

Or fail closed before dispatch:

```python
try:
    hook.authorize("filesystem.write_file", {"path": ".env"})
except ToolCallBlockedError as error:
    print(error.decision.rule, error.decision.reason)
```

`authorize()` blocks `deny` and `review` by default. A caller with an explicit review workflow may pass `allow_review=True`.

## Recognized semantics

- Known read-only filesystem tools return `allow`.
- Known mutating filesystem tools evaluate `path`, `file_path`, `source`, `destination`, and `target` values with the same path policy.
- Known command tools accept only a non-empty string `argv` list. Shell command strings return `review`; AgentDiff does not parse or authorize shell syntax.
- Unknown or malformed tools return `review`.

The decision stores only normalized subjects and provenance; arbitrary content and credentials are not copied into it. See the executable [example](https://github.com/kam6l/agentdiff/blob/main/examples/mcp_policy_hook.py).

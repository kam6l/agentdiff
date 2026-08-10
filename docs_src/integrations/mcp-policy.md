# MCP-style policy hook

AgentDiff includes a transport-neutral hook for evaluating MCP-style tool calls before dispatch:

```python
from agentdiff.integrations import MCPPolicyHook, ToolCallBlockedError
from agentdiff.policy import load_policy_file

policy = load_policy_file("agentdiff.yaml")
hook = MCPPolicyHook(policy)

try:
    decision = hook.authorize(
        "filesystem.write_file",
        {"path": "src/app.py", "content": "..."},
    )
except ToolCallBlockedError as error:
    log(error.decision.to_dict())
    raise

send_to_mcp_server()
```

This is an **integration seam**, not an MCP client, proxy, server, or transport. Your dispatcher must call the hook before sending the tool request. AgentDiff cannot enforce policy on calls that bypass it.

## Recognized calls

The hook recognizes common suffixes for:

- mutating filesystem tools such as `write_file`, `edit_file`, `move_file`, `delete_file`, and `apply_patch`;
- read-only filesystem tools such as `read_file` and `list_directory`; and
- command tools such as `execute_command`, `run_command`, and `spawn_process`.

Names can be dotted (`filesystem.write_file`) or use common MCP-generated separators (`mcp__filesystem__write_file`). This is convention matching, not protocol discovery.

Mutating filesystem calls are evaluated with the same deterministic path policy used by runtime manifests. Command calls require an explicit string `argv` sequence and use process policy. Shell command strings are not parsed or authorized because shell parsing is ambiguous and platform-dependent.

## Unknown and malformed tools

Unknown tools, mutating tools without a usable path, unsafe paths, malformed argument payloads, and unparsed shell strings resolve to `review`.

`authorize()` blocks both `deny` and `review` by default. A caller can deliberately accept review decisions:

```python
decision = hook.authorize(name, arguments, allow_review=True)
```

This makes the fail-open choice explicit at the dispatch boundary.

## Privacy

The serialized decision contains the tool name, path/executable subjects, final action, rule provenance, and reason. It does not retain arbitrary argument values such as file content or tokens.

Paths themselves can still be sensitive. Apply the same artifact-handling precautions as run capsules.

## Extending the hook

The current recognizer is intentionally small. A production transport adapter should:

1. map server-specific tool schemas to normalized path/argv subjects;
2. treat ambiguous mutation semantics as review;
3. persist the redacted decision before dispatch;
4. ensure denied/review calls cannot bypass the hook; and
5. add executable tests for each server/tool schema it advertises.

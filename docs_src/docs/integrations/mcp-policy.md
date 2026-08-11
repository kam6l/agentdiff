# MCP Policy Hook

Block or review tool calls at the MCP level before they execute.

## Overview

The MCP Policy Hook integrates AgentDiff's policy engine directly into the [Model Context Protocol](https://modelcontextprotocol.io/) flow. When an agent calls a tool via MCP, the hook evaluates the call against your policy **before execution**.

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP FLOW                                  │
├─────────────────────────────────────────────────────────────────┤
│  Agent ──► MCP Client ──► MCP Server ──► Tool                  │
│                │          │                                     │
│                │          ▼                                     │
│                │    ┌─────────┐                                 │
│                │    │  HOOK   │  ◄── AgentDiff Policy Engine    │
│                │    └────┬────┘                                 │
│                │         │                                      │
│                │    ALLOW/DENY/REVIEW                            │
│                │         │                                      │
│                ▼         ▼                                      │
│             Execute   Block                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Installation

```bash
pip install "agentdiff[mcp]"
```

---

## Quickstart

### 1. Create Policy

```yaml
# mcp-policy.yaml
schema_version: 1
mcp:
  tools:
    write_file:
      allow:
        - "src/**"
        - "tests/**"
      deny:
        - ".env*"
        - "*.pem"
        - "*.key"
      review:
        - "config.yaml"
        - "pyproject.toml"
    run_command:
      deny:
        - "rm -rf *"
        - "sudo *"
        - "curl * | bash"
      review:
        - "npm install"
        - "pip install"
    read_file:
      allow:
        - "**"
    list_directory:
      allow:
        - "**"
```

### 2. Configure MCP Server

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "mcp-filesystem-server",
      "args": ["/workspace"],
      "env": {
        "AGENTDIFF_POLICY": "mcp-policy.yaml"
      }
    }
  }
}
```

### 3. Enable Hook (Python)

```python
from agentdiff.integrations import MCPolicyHook
from mcp.server import Server

# Create hook with policy
hook = MCPolicyHook.from_file("mcp-policy.yaml")

# Wrap your MCP server
server = Server("my-agent")

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    # Evaluate BEFORE execution
    decision = hook.evaluate_tool_call(name, arguments)
    
    if decision.action == "deny":
        raise PermissionError(f"Blocked by policy: {decision.reason}")
    
    if decision.action == "review":
        # Log for human review, allow to proceed
        logger.warning(f"REVIEW required: {decision.reason}")
    
    # Execute the tool
    return await server.call_tool(name, arguments)
```

---

## Policy Schema (MCP)

```yaml
schema_version: 1

mcp:
  # Default for tools not explicitly configured
  default: review  # allow | review | deny
  
  # Per-tool rules
  tools:
    <tool_name>:
      allow:
        - <glob pattern>
      deny:
        - <glob pattern>
      review:
        - <glob pattern>
      default: review  # override global default for this tool
```

### Argument Matching

Patterns match against **serialized arguments**:

```yaml
tools:
  write_file:
    # Match file paths
    deny:
      - "arguments.path:.env*"      # .env files
      - "arguments.path:*.pem"      # PEM files
    allow:
      - "arguments.path:src/**"     # Source files
  
  run_command:
    # Match command strings
    deny:
      - "arguments.command:rm -rf *"     # Destructive
      - "arguments.command:sudo *"       # Privilege escalation
      - "arguments.command:curl * | sh"  # Pipe to shell
    review:
      - "arguments.command:pip install *"  # Dependency changes
      - "arguments.command:npm install *"  # Dependency changes
```

---

## Decision Types

| Decision | Behavior |
|----------|----------|
| **ALLOW** | Tool executes immediately |
| **REVIEW** | Tool executes but flagged for human review (audit log) |
| **DENY** | Tool blocked, `PermissionError` raised |

---

## Hook API

```python
from agentdiff.integrations import MCPolicyHook
from agentdiff.policy import PolicyAction

hook = MCPolicyHook.from_file("mcp-policy.yaml")

# Evaluate a tool call
decision = hook.evaluate_tool_call(
    tool_name="write_file",
    arguments={"path": ".env", "content": "SECRET=123"}
)

# Decision object
print(decision.action)      # PolicyAction.DENY
print(decision.rule)        # "mcp.tools.write_file.deny[0]"
print(decision.pattern)     # "arguments.path:.env*"
print(decision.reason)      # "matched mcp.tools.write_file.deny[0] pattern 'arguments.path:.env*'"
print(decision.tool_name)   # "write_file"
print(decision.arguments)   # {"path": ".env", "content": "SECRET=123"}
```

### Batch Evaluation

```python
# Evaluate multiple calls at once (for planning)
decisions = hook.evaluate_batch([
    {"tool": "write_file", "arguments": {"path": "src/main.py", "content": "..."}},
    {"tool": "write_file", "arguments": {"path": ".env", "content": "..."}},
    {"tool": "run_command", "arguments": {"command": "npm install"}},
])

for d in decisions:
    print(f"{d.tool_name}: {d.action.value}")
```

---

## Integration Patterns

### With FastMCP

```python
from fastmcp import FastMCP
from agentdiff.integrations import MCPolicyHook

mcp = FastMCP("My Server")
hook = MCPolicyHook.from_file("mcp-policy.yaml")

@mcp.tool()
async def write_file(path: str, content: str) -> str:
    decision = hook.evaluate_tool_call("write_file", {"path": path, "content": content})
    
    if decision.action == PolicyAction.DENY:
        raise PermissionError(f"Policy DENY: {decision.reason}")
    
    # ... actual file write ...
    return "OK"
```

### With MCP Proxy

```python
# mcp-proxy config
{
  "proxies": [
    {
      "name": "filesystem-with-policy",
      "command": "mcp-filesystem-server",
      "args": ["/workspace"],
      "middleware": [
        "agentdiff.mcp.MCPolicyMiddleware"
      ],
      "env": {
        "AGENTDIFF_POLICY": "mcp-policy.yaml"
      }
    }
  ]
}
```

---

## Audit Logging

All decisions are logged for compliance:

```json
{
  "timestamp": "2026-01-15T10:30:45.123Z",
  "tool": "write_file",
  "arguments": {"path": ".env", "content": "***"},
  "decision": "DENY",
  "rule": "mcp.tools.write_file.deny[0]",
  "pattern": "arguments.path:.env*",
  "agent_id": "agent-abc123",
  "session_id": "sess-xyz789"
}
```

Enable structured logging:

```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            **getattr(record, "extra", {})
        })

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.getLogger("agentdiff.mcp").addHandler(handler)
logging.getLogger("agentdiff.mcp").setLevel(logging.INFO)
```

---

## Testing Policies

```bash
# Test a tool call against policy
agentdiff mcp test \
  --policy mcp-policy.yaml \
  --tool write_file \
  --args '{"path": ".env", "content": "SECRET=123"}'

# Output:
# DECISION: DENY
# RULE: mcp.tools.write_file.deny[0]
# PATTERN: arguments.path:.env*
# REASON: matched mcp.tools.write_file.deny[0] pattern 'arguments.path:.env*'
```

### Batch Test File

```yaml
# test-cases.yaml
- tool: write_file
  arguments:
    path: "src/main.py"
    content: "print('hello')"
  expect: ALLOW

- tool: write_file
  arguments:
    path: ".env"
    content: "SECRET=123"
  expect: DENY

- tool: run_command
  arguments:
    command: "rm -rf /"
  expect: DENY
```

```bash
agentdiff mcp test-batch --policy mcp-policy.yaml --cases test-cases.yaml
```

---

## Next Steps

- [Anthropic Sandbox Runtime](sandbox-runtime.md) — Kernel-level isolation
- [Custom Frameworks](custom.md) — Integrate with your agent framework
- [Mutation Policy](../concepts/policy.md) — Filesystem policy reference
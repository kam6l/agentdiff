# LangChain / LangGraph Integration

Use AgentDiff as a callback handler to observe and evaluate LangChain/LangGraph agent runs.

## Installation

```bash
pip install "agentdiff[langchain]"
```

---

## Quickstart

### LangGraph

```python
from langgraph.graph import StateGraph
from agentdiff.integrations import AgentDiffCallbackHandler

# Create callback handler
callback = AgentDiffCallbackHandler(
    policy_path="agentdiff-policy.yaml",
    task_description="Fix the parser",
)

# Build your graph
graph = StateGraph(AgentState)
# ... add nodes, edges ...

# Compile with callback
app = graph.compile()

# Run with callback
result = app.invoke(
    {"input": "Fix the parser bug"},
    config={"callbacks": [callback]}
)

# Access results
print(f"Run ID: {callback.run_id}")
print(f"Blast radius: {callback.blast_radius.score}/100")
```

### LangChain (Legacy)

```python
from langchain.agents import AgentExecutor
from agentdiff.integrations import AgentDiffCallbackHandler

callback = AgentDiffCallbackHandler(
    policy_path="agentdiff-policy.yaml",
    task_description="Refactor the service",
)

agent = AgentExecutor(agent=..., tools=..., callbacks=[callback])
result = agent.invoke({"input": "Refactor the user service"})
```

---

## Callback Handler API

```python
from agentdiff.integrations import AgentDiffCallbackHandler

callback = AgentDiffCallbackHandler(
    policy_path="agentdiff-policy.yaml",  # Required
    task_description="Fix the parser",    # Required
    root="/workspace",                    # Working directory (default: cwd)
    observe_processes=True,               # Track owned processes
    observe_ports=True,                   # Track network ports
    backup_enabled=True,                  # Create backups for recovery
)
```

### Properties (After Run)

```python
# Run identification
callback.run_id          # str
callback.task_description # str

# Results
callback.status          # "PASS" | "REVIEW" | "DENY"
callback.blast_radius    # BlastRadiusResult
callback.mutations       # list[MutationRecord]

# Recovery
callback.rollback(safe_only=True)
callback.restore_file("src/main.py")
```

---

## With LangGraph Checkpointers

```python
from langgraph.checkpoint.sqlite import SqliteSaver
from agentdiff.integrations import AgentDiffCallbackHandler

# Persistent checkpointer
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")

callback = AgentDiffCallbackHandler(
    policy_path="agentdiff-policy.yaml",
    task_description="Long-running task",
)

app = graph.compile(checkpointer=checkpointer)

# Run with thread_id for resumability
config = {
    "configurable": {"thread_id": "session-123"},
    "callbacks": [callback],
}

result = app.invoke({"input": "Fix the parser"}, config=config)
```

---

## Streaming with Callbacks

```python
from agentdiff.integrations import AgentDiffCallbackHandler

callback = AgentDiffCallbackHandler(
    policy_path="agentdiff-policy.yaml",
    task_description="Streaming fix",
)

# Stream events
async for event in app.astream(
    {"input": "Fix the parser"},
    config={"callbacks": [callback]},
    stream_mode="values",
):
    print(event)

# Final results available after stream completes
print(f"Blast radius: {callback.blast_radius.score}")
```

---

## Policy for LLM Tool Calls

Configure policy to match LangChain tool schemas:

```yaml
# agentdiff-policy.yaml
schema_version: 1

mcp:
  tools:
    write_file:
      allow:
        - "arguments.path:src/**"
        - "arguments.path:tests/**"
      deny:
        - "arguments.path:.env*"
        - "arguments.path:*.pem"
      review:
        - "arguments.path:pyproject.toml"
        - "arguments.path:config.yaml"
    
    run_command:
      deny:
        - "arguments.command:rm -rf *"
        - "arguments.command:sudo *"
      review:
        - "arguments.command:pip install *"
        - "arguments.command:npm install *"
    
    read_file:
      allow:
        - "arguments.path:**"
    
    list_directory:
      allow:
        - "arguments.path:**"
    
    # Custom tools
    my_custom_tool:
      allow:
        - "arguments.repo_path:src/**"
      deny:
        - "arguments.repo_path:.git/**"
```

---

## Accessing Evidence Programmatically

```python
# After agent run completes
capsule = callback.get_capsule()

# Filesystem mutations
for mutation in capsule.mutations:
    print(f"{mutation.change_type} {mutation.path} → {mutation.decision}")

# Process evidence
for proc in capsule.processes:
    print(f"PID {proc.pid} ({proc.create_time}) → {proc.cleanup_status}")

# Port observation
for port in capsule.ports.new:
    print(f"New port: {port.proto} {port.addr}:{port.port}")

# Blast radius components
for component in callback.blast_radius.components:
    print(f"{component.name}: {component.points} pts ({component.detail})")
```

---

## Custom Callback Logic

Extend the handler for custom behavior:

```python
from agentdiff.integrations import AgentDiffCallbackHandler
from agentdiff.policy import PolicyAction

class SlackAlertCallback(AgentDiffCallbackHandler):
    def on_deny_mutation(self, mutation):
        """Called when a DENY mutation is detected."""
        self.slack_webhook.post({
            "text": f"🚨 Agent DENY mutation: {mutation.path}",
            "blocks": [...]
        })
    
    def on_blast_radius_exceeded(self, threshold, actual):
        """Called when blast radius exceeds threshold."""
        self.pagerduty.alert(f"Blast radius {actual} > {threshold}")

callback = SlackAlertCallback(
    policy_path="agentdiff-policy.yaml",
    task_description="Production fix",
)

# Use with your agent...
```

---

## Next Steps

- [Anthropic Sandbox Runtime](sandbox-runtime.md) — Kernel isolation
- [MCP Policy Hook](mcp-policy.md) — Block at protocol level
- [Custom Frameworks](custom.md) — Build your own integration
- [Mutation Policy](../concepts/policy.md) — Policy reference
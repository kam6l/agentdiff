# Custom Framework Integration

Build your own AgentDiff integration for any agent framework.

## Integration Points

AgentDiff exposes three integration layers:

| Layer | Use Case | Complexity |
|-------|----------|------------|
| **Runtime API** | Wrap any `argv` sequence | Low |
| **Callback Handler** | Observe tool calls in real-time | Medium |
| **Policy Hook** | Block/review at protocol level | High |

---

## 1. Runtime API (Simplest)

Wrap any command without modifying your agent:

```python
from agentdiff import AgentDiffRuntime
from agentdiff.policy import Policy

policy = Policy.from_file("agentdiff-policy.yaml")
runtime = AgentDiffRuntime(policy=policy, root="/workspace")

# Your agent runs any command
result = runtime.run(
    argv=["python3", "my_agent.py", "--task", "Fix parser"],
    task_description="Fix the parser",
)

# Access evidence
print(f"Run ID: {result.run_id}")
print(f"Blast radius: {result.blast_radius.score}")

# Recover if needed
runtime.rollback(result.run_id, safe_only=True)
```

### CLI Wrapper

Even simpler — shell out to CLI:

```bash
# In your agent's code
import subprocess

result = subprocess.run([
    "agentdiff", "run",
    "--task", "Fix the parser",
    "--", "python3", "my_agent.py"
], capture_output=True, text=True)

# Parse run_id from output
run_id = parse_run_id(result.stdout)
```

---

## 2. Callback Handler (Real-Time)

Observe tool calls as they happen:

```python
from agentdiff.integrations import BaseCallbackHandler
from agentdiff.policy import PolicyAction

class MyFrameworkCallback(BaseCallbackHandler):
    def __init__(self, policy_path, task_description):
        super().__init__(policy_path, task_description)
    
    def on_tool_start(self, tool_name, arguments):
        """Called before tool executes."""
        decision = self.policy_engine.decide_tool_call(tool_name, arguments)
        
        if decision.action == PolicyAction.DENY:
            raise PermissionError(f"Blocked: {decision.reason}")
        
        if decision.action == PolicyAction.REVIEW:
            self.log_review(decision)
    
    def on_tool_end(self, tool_name, arguments, result):
        """Called after tool executes."""
        # Record mutation for blast radius
        self.record_mutation(tool_name, arguments, result)
    
    def on_agent_finish(self, final_result):
        """Called when agent completes."""
        self.finalize_run()

# Usage
callback = MyFrameworkCallback("agentdiff-policy.yaml", "Fix parser")
your_agent.run(callbacks=[callback])
```

### BaseCallbackHandler Methods to Override

| Method | When Called | Purpose |
|--------|-------------|---------|
| `on_agent_start(task)` | Agent begins | Initialize run capsule |
| `on_tool_start(name, args)` | Before tool call | Policy check, pre-capture |
| `on_tool_end(name, args, result)` | After tool call | Record mutation |
| `on_tool_error(name, args, error)` | Tool fails | Record failed mutation |
| `on_agent_finish(result)` | Agent done | Finalize, compute blast radius |

---

## 3. Policy Hook (Protocol Level)

Block at the protocol level (MCP, custom RPC):

```python
from agentdiff.integrations import MCPolicyHook
from agentdiff.policy import PolicyAction

class MyProtocolHook:
    def __init__(self, policy_path):
        self.hook = MCPolicyHook.from_file(policy_path)
    
    def intercept_call(self, method, params):
        """Call this before executing any mutating operation."""
        decision = self.hook.evaluate_tool_call(method, params)
        
        if decision.action == PolicyAction.DENY:
            return {"error": "BLOCKED", "reason": decision.reason}
        
        if decision.action == PolicyAction.REVIEW:
            self.audit_log(decision)
        
        return {"allowed": True, "decision": decision.to_dict()}

# Usage in your protocol server
hook = MyProtocolHook("agentdiff-policy.yaml")

async def handle_request(request):
    if request.method in MUTATING_METHODS:
        check = hook.intercept_call(request.method, request.params)
        if "error" in check:
            return error_response(check["error"], check["reason"])
    
    return await execute_request(request)
```

---

## Complete Example: CrewAI Integration

```python
# agentdiff_crewai.py
from crewai import Agent, Task, Crew
from agentdiff.integrations import BaseCallbackHandler
from agentdiff.policy import PolicyAction

class CrewAICallback(BaseCallbackHandler):
    def __init__(self, policy_path, task_description):
        super().__init__(policy_path, task_description)
        self.current_task = None
    
    def on_task_start(self, task: Task):
        self.current_task = task.description
        self.on_agent_start(task.description)
    
    def on_tool_start(self, tool_name, arguments):
        # Map CrewAI tool names to policy
        policy_tool = self._map_tool(tool_name)
        decision = self.policy_engine.decide_tool_call(policy_tool, arguments)
        
        if decision.action == PolicyAction.DENY:
            raise PermissionError(f"CrewAI blocked: {decision.reason}")
    
    def on_tool_end(self, tool_name, arguments, result):
        self.record_mutation(self._map_tool(tool_name), arguments, result)
    
    def on_task_end(self, task: Task, output: str):
        self.on_agent_finish(output)
    
    def _map_tool(self, crewai_tool):
        mapping = {
            "file_write": "write_file",
            "file_read": "read_file",
            "shell": "run_command",
            "directory_list": "list_directory",
        }
        return mapping.get(crewai_tool, crewai_tool)

# Usage
callback = CrewAICallback("agentdiff-policy.yaml", "Fix parser")

agent = Agent(role="Developer", tools=[...], callbacks=[callback])
task = Task(description="Fix the parser", agent=agent)
crew = Crew(agents=[agent], tasks=[task])
result = crew.kickoff()

# Access AgentDiff results
print(f"Blast radius: {callback.blast_radius.score}")
callback.rollback(safe_only=True)
```

---

## Complete Example: AutoGen Integration

```python
# agentdiff_autogen.py
from autogen import AssistantAgent, UserProxyAgent
from agentdiff.integrations import BaseCallbackHandler
from agentdiff.policy import PolicyAction

class AutoGenCallback(BaseCallbackHandler):
    def __init__(self, policy_path, task_description):
        super().__init__(policy_path, task_description)
    
    def on_function_call(self, name, args):
        decision = self.policy_engine.decide_tool_call(name, args)
        if decision.action == PolicyAction.DENY:
            return {"error": "BLOCKED", "reason": decision.reason}
        return None  # Allow
    
    def on_function_result(self, name, args, result):
        self.record_mutation(name, args, result)

# Usage
callback = AutoGenCallback("agentdiff-policy.yaml", "Code review")

assistant = AssistantAgent("assistant", function_callback=callback)
user_proxy = UserProxyAgent("user")
user_proxy.initiate_chat(assistant, message="Review this PR")
```

---

## Required Policy Patterns for Common Tools

Ensure your policy covers these tool schemas:

```yaml
mcp:
  tools:
    # File operations
    write_file:
      arguments:
        path: string
        content: string
    read_file:
      arguments:
        path: string
    list_directory:
      arguments:
        path: string
    
    # Shell
    run_command:
      arguments:
        command: string
        args?: string[]
        env?: object
    
    # Git
    git_commit:
      arguments:
        message: string
        files?: string[]
    git_diff:
      arguments:
        path?: string
    
    # Package managers
    pip_install:
      arguments:
        packages: string[]
        requirements_file?: string
    npm_install:
      arguments:
        packages?: string[]
        dev?: boolean
```

---

## Testing Your Integration

```python
# test_integration.py
import pytest
from my_integration import MyFrameworkCallback

def test_deny_mutation_blocked():
    callback = MyFrameworkCallback("test-policy.yaml", "Test")
    
    with pytest.raises(PermissionError):
        callback.on_tool_start("write_file", {"path": ".env", "content": "SECRET=123"})

def test_allow_mutation_passes():
    callback = MyFrameworkCallback("test-policy.yaml", "Test")
    
    # Should not raise
    callback.on_tool_start("write_file", {"path": "src/main.py", "content": "print('hi')"})
    callback.on_tool_end("write_file", {"path": "src/main.py"}, "OK")
    
    # Blast radius should be 0
    callback.on_agent_finish("Done")
    assert callback.blast_radius.score == 0

def test_review_mutation_flagged():
    callback = MyFrameworkCallback("test-policy.yaml", "Test")
    
    callback.on_tool_start("write_file", {"path": "pyproject.toml", "content": "..."})
    callback.on_tool_end("write_file", {"path": "pyproject.toml"}, "OK")
    callback.on_agent_finish("Done")
    
    assert callback.blast_radius.level == "MODERATE"
```

---

## Publishing Your Integration

1. Create `agentdiff-<framework>` package
2. Add entry point:
```python
# setup.py
entry_points={
    "agentdiff.integrations": [
        "myframework = my_integration:MyFrameworkCallback",
    ]
}
```
3. Users enable with: `agentdiff --integration myframework`

---

## Next Steps

- [Anthropic Sandbox Runtime](sandbox-runtime.md) — Kernel isolation
- [MCP Policy Hook](mcp-policy.md) — Protocol-level blocking
- [LangChain / LangGraph](langchain.md) — Reference implementation
- [Mutation Policy](../concepts/policy.md) — Policy reference
# Custom Framework Integration

Build an adapter for any agent framework in ~50 lines.

## Base Adapter

```python
from agentdiff.integrations import BaseFrameworkAdapter
from agentdiff import AgentFramework

class MyFrameworkAdapter(BaseFrameworkAdapter):
    """Adapter for MyCustomAgent framework."""
    
    framework_name = "myframework"
    
    def on_agent_start(self, task: str):
        """Called when agent begins a task."""
        self.tracker = self.session.create_tracker(task_description=task)
    
    def on_step_start(self, thought: str):
        """Called at start of each reasoning step."""
        self.tracker.start_step(thought)
    
    def on_tool_call(
        self,
        name: str,
        arguments: dict,
        result: any,
        error: str | None = None,
        duration_ms: int = 0
    ):
        """Called for each tool invocation."""
        self.tracker.record_tool_call(name, arguments, result, error, duration_ms)
    
    def on_step_end(self, observation: str):
        """Called at end of each reasoning step."""
        self.tracker.end_step(observation)
    
    def on_agent_end(self, final_result: str, final_error: str | None = None):
        """Called when agent completes."""
        self.trajectory = self.tracker.finish(final_result, final_error)

# Register globally
AgentFramework.register_adapter("myframework", MyFrameworkAdapter)
```

## Usage

```python
from agentdiff.integrations import AgentDiffSession

with AgentDiffSession(paths=["/repo"], target_paths=["/repo/src/"]) as session:
    # Your framework uses the adapter internally
    agent = MyCustomAgent(adapter=session.get_adapter("myframework"))
    result = agent.run("Fix the bug")
    
    # Session auto-evaluates on exit
    report = session.evaluate()
```

## Required Methods

| Method | When Called | Must Call |
|--------|-------------|-----------|
| `on_agent_start(task)` | Task begins | `session.create_tracker()` |
| `on_step_start(thought)` | Each reasoning step | `tracker.start_step()` |
| `on_tool_call(name, args, result, error, duration)` | Each tool use | `tracker.record_tool_call()` |
| `on_step_end(observation)` | Step completes | `tracker.end_step()` |
| `on_agent_end(result, error)` | Task completes | `tracker.finish()` |

## Example: CrewAI Adapter

```python
from agentdiff.integrations import BaseFrameworkAdapter
from agentdiff import AgentFramework

class CrewAIAdapter(BaseFrameworkAdapter):
    framework_name = "crewai"
    
    def __init__(self, session):
        super().__init__(session)
        self._current_step = None
    
    def on_agent_start(self, task):
        self.tracker = self.session.create_tracker(task_description=task)
    
    def on_task_start(self, task_description, agent_role):
        self.tracker.start_step(f"[{agent_role}] {task_description}")
    
    def on_tool_call(self, name, args, result, error, duration_ms):
        self.tracker.record_tool_call(name, args, result, error, duration_ms)
    
    def on_task_end(self, output):
        self.tracker.end_step(str(output))
    
    def on_agent_end(self, result, error):
        self.trajectory = self.tracker.finish(result, error)

AgentFramework.register_adapter("crewai", CrewAIAdapter)
```

## Hook Into Your Framework

Find your framework's callback/hook system:

| Framework | Hook Point |
|-----------|------------|
| CrewAI | `task_callback`, `step_callback` |
| AutoGen | `register_hook("tool_call", ...)` |
| OpenHands | `event_stream.subscribe(...)` |
| LangGraph | `config={"callbacks": [...]}` |
| Custom | Wrap your tool executor |

## Minimal Wrapper Pattern

If no hooks exist, wrap the tool executor:

```python
def tracked_tool_call(original_fn, adapter):
    def wrapper(name, args):
        start = time.time()
        try:
            result = original_fn(name, args)
            adapter.on_tool_call(name, args, result, None, int((time.time()-start)*1000))
            return result
        except Exception as e:
            adapter.on_tool_call(name, args, None, str(e), int((time.time()-start)*1000))
            raise
    return wrapper

# Apply
agent.tool_executor = tracked_tool_call(agent.tool_executor, adapter)
```

## Related

- [LangChain Integration](langchain.md) — Reference implementation
- [Python API](../api.md) — Core classes
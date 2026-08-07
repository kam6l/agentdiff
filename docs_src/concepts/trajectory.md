# Trajectory Tracking

AgentDiff records a **step-by-step trajectory** of agent execution, enabling precise fault attribution and efficiency analysis.

## Trajectory Structure

```json
{
  "run_id": "abc123",
  "task_description": "Fix the add() function",
  "framework": "langgraph",
  "started_at": "2026-01-15T10:30:00Z",
  "ended_at": "2026-01-15T10:30:45Z",
  "steps": [
    {
      "step_id": 0,
      "thought": "Reading calculator.py to understand the bug",
      "tool_calls": [
        {
          "name": "read_file",
          "arguments": {"path": "calculator.py"},
          "result": "def add(a, b): return a - b",
          "error": null,
          "duration_ms": 45
        }
      ],
      "observation": "Found bug: subtract instead of add",
      "started_at": "2026-01-15T10:30:00Z",
      "ended_at": "2026-01-15T10:30:01Z"
    }
  ],
  "final_result": "Tests pass",
  "final_error": null
}
```

## Key Metrics Derived

| Metetric | Description |
|----------|-------------|
| **Total Steps** | Number of high-level agent steps |
| **Total Tool Calls** | Sum of all tool invocations |
| **Unique Tools Used** | Diversity of tool usage |
| **Loop Count** | Detected redundant cycles |
| **Redundant Calls** | Repeated identical tool calls |
| **Efficiency Score** | `unique_tools / total_tool_calls` |
| **Error Recovery Steps** | Steps after a failed tool call |
| **Success Rate** | `successful_calls / total_calls` |

## Loop Detection

AgentDiff detects when an agent gets stuck in a cycle:

```python
# Automatically detected
Loop detected: Steps 3-7 repeat same read_file → write_file pattern
Loop Count: 1
Redundant Calls: 4
```

## Step-Level Fault Attribution

When combined with environment diffing, each step can be attributed:

```
Step 2 (write_file config.yaml): +3 unintended mutations
Step 4 (run_command npm install): +12 process spawns
Step 5 (write_file debug.log): +1 unexpected file creation
```

## Recording from Your Agent

```python
from agentdiff import TrajectoryTracker

tracker = TrajectoryTracker(task_description="Fix auth bug")

# For each agent step:
tracker.start_step("Analyzing auth module")
tracker.record_tool_call("read_file", {"path": "auth.py"}, result=content, duration_ms=30)
tracker.record_tool_call("grep", {"pattern": "password"}, result=matches, duration_ms=15)
tracker.end_step("Found hardcoded secret")

# ... more steps ...

trajectory = tracker.finish(final_result="Secret rotated, tests pass")
trajectory.save("trajectory.json")
```

## Related

- [Cleanliness Score](cleanliness.md) — How trajectory feeds evaluation
- [Side Effects](side-effects.md) — Mutations attributed to steps
# Trajectory tracking

A trajectory records the execution path that produced a state change: thoughts or step labels, tool calls, observations, timing, token usage, and final status.

## Record steps

```python
from agentdiff import AgentFramework, TrajectoryTracker

tracker = TrajectoryTracker(
    task_description="Fix the evaluator",
    framework=AgentFramework.CUSTOM,
)

tracker.start_step("Inspect the failing module")
tracker.record_tool_call(
    name="read_file",
    arguments={"path": "src/evaluator.py"},
    result="...",
    duration_ms=38,
)
tracker.end_step("Found the hard-coded threshold")

trajectory = tracker.finish(final_result="Tests pass")
trajectory.save("trajectory.json")
```

`TrajectoryRecord.load("trajectory.json")` reconstructs a saved record.

## Time a tool safely

`track_tool()` records duration and exceptions. Call the yielded setter to retain the result:

```python
tracker.start_step("Query repository")
with tracker.track_tool("search", {"query": "threshold"}) as set_result:
    matches = search("threshold")
    set_result(matches)
tracker.end_step("Found evaluator references")
```

## Derived metrics

AgentDiff computes:

- total steps and tool calls
- unique tools used
- failed tool calls and success rate
- input and output token totals
- elapsed run time and average step time
- repeated tool-pattern loops
- redundant-call count
- efficiency score

Efficiency starts at `1.0`, subtracts the detected redundancy ratio, and applies half of the failed-call rate as an additional penalty. It is diagnostic—not a claim about model intelligence or wall-clock speed.

## Loop detection

`TrajectoryRecord.detect_loops()` scans repeated tool-name windows. It detects repeated execution patterns such as:

```text
read_file → write_file → read_file → write_file → read_file → write_file
```

Because the detector considers tool names rather than semantic intent, inspect the returned patterns before treating every loop as a defect.

## Saved schema

The JSON record includes `run_id`, `task_description`, `framework`, timestamps, metadata, steps, final result, and final error. Each step includes its tool calls, observation, optional token counts, and duration.

AgentDiff does not require hidden chain-of-thought. Use concise operational step labels when private reasoning should not be stored.

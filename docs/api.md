# Python API Reference

## Core Classes

### `AgentDiffSession`
Context manager for full evaluation workflow.

```python
from agentdiff import AgentDiffSession

with AgentDiffSession(
    paths=["/repo"],                    # Paths to snapshot
    target_paths=["/repo/src/main.py"], # Intended mutation targets
    exclude_patterns=["*.log", "__pycache__"],
    cleanliness_threshold=0.8
) as session:
    # Run your agent here
    result = agent.run("Fix the bug")
    
    # Automatic evaluation on exit
    report = session.evaluate()

print(report.cleanliness_score)
print(report.side_effects)
```

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `paths` | `list[str]` | `["."]` | Paths to include in snapshots |
| `target_paths` | `list[str]` | `[]` | Paths agent *should* modify |
| `exclude_patterns` | `list[str]` | `[]` | Glob patterns to ignore |
| `cleanliness_threshold` | `float` | `0.8` | Threshold for pass/fail |

---

### `DiffEngine`
Filesystem and environment diffing.

```python
from agentdiff import DiffEngine

engine = DiffEngine(watch_paths=["/repo"], exclude_patterns=["*.log"])

# Capture snapshot
snapshot = engine.snapshot()

# ... agent runs ...

# Capture second snapshot
snapshot2 = engine.snapshot()

# Compute diff
diff = engine.diff(snapshot, snapshot2)

print(diff.summary)
# {'file_created': 2, 'file_modified': 1, 'file_deleted': 0, ...}

print(diff.added_files)
print(diff.modified_files)
print(diff.deleted_files)
```

---

### `TrajectoryTracker`
Step-by-step trajectory recording.

```python
from agentdiff import TrajectoryTracker, AgentFramework

tracker = TrajectoryTracker(
    task_description="Fix login bug",
    framework=AgentFramework.LANGGRAPH
)

# Per agent step:
tracker.start_step("Reading auth module")
tracker.record_tool_call(
    name="read_file",
    arguments={"path": "auth.py"},
    result=file_content,
    duration_ms=45
)
tracker.end_step("Found hardcoded secret")

# ... more steps ...

trajectory = tracker.finish(
    final_result="Secret rotated, tests pass"
)

trajectory.save("trajectory.json")

# Load later
loaded = TrajectoryTracker.load("trajectory.json")
```

---

### `AgentDiffEvaluator`
Compute cleanliness and side effects.

```python
from agentdiff import AgentDiffEvaluator, TrajectoryTracker, DiffEngine

# Load trajectory and diff
trajectory = TrajectoryTracker.load("trajectory.json").get_trajectory()
diff = engine.diff(pre_snapshot, post_snapshot)

# Evaluate
evaluator = AgentDiffEvaluator(target_paths=["/repo/src/main.py"])
report = evaluator.evaluate(trajectory, diff)

print(f"Cleanliness: {report.cleanliness_score:.2%}")
print(f"Grade: {report.grade}")
print(f"Side Effects: {len(report.side_effects)}")

for effect in report.side_effects:
    print(f"  {effect.severity}: {effect.category} — {effect.description}")

# Export
report.to_json("report.json")
report.to_html("report.html")  # Requires optional dependency
report.to_junit("report.xml")
```

---

## Data Models

### `EvaluationReport`
| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `str` | Unique run identifier |
| `cleanliness_score` | `float` | 0.0–1.0 |
| `grade` | `str` | A+ through F |
| `total_mutations` | `int` | All mutations |
| `target_mutations` | `int` | Mutations in target_paths |
| `unintended_mutations` | `int` | Mutations outside target |
| `side_effects` | `list[SideEffect]` | Classified effects |
| `trajectory_metrics` | `TrajectoryMetrics` | Step/loop/efficiency stats |

### `SideEffect`
| Field | Type | Description |
|-------|------|-------------|
| `severity` | `Severity` | CRITICAL / WARNING / INFO |
| `category` | `str` | e.g., "unexpected_file_modification" |
| `description` | `str` | Human-readable |
| `path` | `str \| None` | Affected path |
| `step_index` | `int \| None` | Attributed trajectory step |

### `TrajectoryMetrics`
| Field | Type | Description |
|-------|------|-------------|
| `total_steps` | `int` | |
| `total_tool_calls` | `int` | |
| `unique_tools` | `int` | |
| `loop_count` | `int` | |
| `redundant_calls` | `int` | |
| `efficiency_score` | `float` | |
| `error_recovery_steps` | `int` | |
| `success_rate` | `float` | |

---

## Enums

### `AgentFramework`
```python
class AgentFramework(Enum):
    CUSTOM = "custom"
    LANGCHAIN = "langchain"
    LANGGRAPH = "langgraph"
    CREWAI = "crewai"
    AUTOGEN = "autogen"
    OPENHANDS = "openhands"
```

### `Severity`
```python
class Severity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
```

---

## Integrations

### LangChain/LangGraph Callback

```python
from agentdiff.integrations import LangChainCallbackHandler, AgentDiffSession

with AgentDiffSession(paths=["/repo"], target_paths=["/repo/src/"]) as session:
    callback = LangChainCallbackHandler(session)
    
    # For LangGraph
    graph.invoke({"input": "task"}, config={"callbacks": [callback]})
    
    # For LangChain
    chain.invoke({"input": "task"}, callbacks=[callback])

report = session.evaluate()
```

### Custom Framework Adapter

```python
from agentdiff.integrations import BaseFrameworkAdapter

class MyFrameworkAdapter(BaseFrameworkAdapter):
    def on_tool_call(self, name, args, result, error, duration_ms):
        self.tracker.record_tool_call(name, args, result, error, duration_ms)
    
    def on_step_start(self, thought):
        self.tracker.start_step(thought)
    
    def on_step_end(self, observation):
        self.tracker.end_step(observation)

# Register
AgentFramework.register_adapter("myframework", MyFrameworkAdapter)
```

---

## Utility Functions

```python
from agentdiff import load_trajectory, load_snapshot, load_diff, load_report

trajectory = load_trajectory("trajectory.json")
snapshot = load_snapshot("snapshot.json")
diff = load_diff("diff.json")
report = load_report("report.json")
```
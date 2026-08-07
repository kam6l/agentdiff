# Quickstart

## Installation

```bash
pip install agentdiff
```

Or with uv:
```bash
uv add agentdiff
```

## Initialize Configuration

```bash
agentdiff init
```

Creates `agentdiff.yaml` in your project root:
```yaml
watch_paths:
  - .
target_paths: []
exclude_patterns:
  - "*.pyc"
  - "__pycache__"
  - ".git"
  - "*.log"
cleanliness_threshold: 0.8
```

## Run the Demo

```bash
agentdiff demo
```

Outputs a full evaluation report with cleanliness score and side effects.

## Basic CLI Workflow

### 1. Capture baseline snapshot (before agent runs)
```bash
agentdiff snapshot --output before.json
```

### 2. Run your agent
```bash
# Any agent framework - LangGraph, CrewAI, custom, etc.
python run_my_agent.py
```

### 3. Capture post snapshot
```bash
agentdiff snapshot --output after.json
```

### 4. Evaluate
```bash
agentdiff eval --trajectory trajectory.json --pre before.json --post after.json
```

### 5. View results
```
Cleanliness Score: 0.847
Total Mutations: 12
Target Mutations: 10
Unintended Mutations: 2
Side Effects: 2 WARNING, 0 CRITICAL
```

## Save Trajectory from Your Agent

```python
from agentdiff import TrajectoryTracker

tracker = TrajectoryTracker(task_description="Fix login bug")

# During agent execution
tracker.start_step("Reading auth module")
tracker.record_tool_call("read_file", {"path": "auth.py"}, result="...", duration_ms=45)
tracker.end_step("Found the bug")

tracker.start_step("Fixing the bug")
tracker.record_tool_call("write_file", {"path": "auth.py", "content": "..."}, result="OK", duration_ms=120)
tracker.end_step("Fix applied")

# Save for evaluation
trajectory = tracker.finish(final_result="Tests pass")
trajectory.save("trajectory.json")
```

## Next Steps

- [CLI Reference](cli.md) — All commands and options
- [Python API](api.md) — Programmatic usage
- [Integrations](integrations/langchain.md) — LangChain/LangGraph callback
- [CI/CD Tutorial](tutorials/ci-cd.md) — Gate agent quality in pipelines
# Python API

AgentDiff can be used as a framework-neutral session or as three explicit components: snapshot engine, trajectory tracker, and evaluator.

## Framework-neutral session

```python
from agentdiff import AgentDiffConfig, AgentDiffSession

config = AgentDiffConfig(
    root=".",
    target_paths=["src/evaluator.py"],
    cleanliness_threshold=0.8,
)

with AgentDiffSession("Fix the evaluator", config) as run:
    your_agent()
    run.record(
        thought="Applied the focused patch",
        tool_name="edit_file",
        tool_args={"path": "src/evaluator.py"},
        observation="File updated",
    )

result = run.evaluate()
print(result.metrics.cleanliness_score)
print(result.passed)
```

Relative targets are resolved against `config.root`. Call `evaluate()` after the work finishes; leaving the context does not hide exceptions or auto-publish a report.

## Explicit components

```python
from pathlib import Path

from agentdiff import AgentDiffEvaluator, DiffEngine, TrajectoryTracker

root = Path(".").resolve()
engine = DiffEngine(watch_paths=[str(root)])
before_fs, before_env = engine.snapshot()

tracker = TrajectoryTracker(task_description="Update one file")
tracker.start_step("Edit target")
tracker.record_tool_call("write_file", {"path": "target.txt"}, result="ok")
tracker.end_step("Done")
Path("target.txt").write_text("updated\n")
trajectory = tracker.finish()

after_fs, after_env = engine.snapshot()
evaluator = AgentDiffEvaluator(
    target_paths=[str(root)],
    cleanliness_threshold=0.8,
)
evaluator.set_target_mutations([str(root / "target.txt")])
result = evaluator.evaluate_from_snapshots(
    trajectory,
    (before_fs, before_env),
    (after_fs, after_env),
)
```

`EvaluationResult.to_json()` returns a JSON string. `EvaluationResult.print_summary()` renders a Rich terminal report.

## API reference

### Diff engine

::: agentdiff.diff_engine.DiffEngine
    options:
      show_root_heading: true
      members:
        - snapshot
        - diff

### Trajectory tracker

::: agentdiff.trajectory.TrajectoryTracker
    options:
      show_root_heading: true
      members:
        - start_step
        - record_tool_call
        - record_llm_usage
        - track_tool
        - end_step
        - finish
        - save

### Evaluator

::: agentdiff.evaluator.AgentDiffEvaluator
    options:
      show_root_heading: true
      members:
        - set_target_mutations
        - evaluate
        - evaluate_from_snapshots

### Result models

::: agentdiff.evaluator.EvaluationResult
    options:
      show_root_heading: true
      members:
        - to_dict
        - to_json
        - print_summary

::: agentdiff.evaluator.CleanlinessMetrics
    options:
      show_root_heading: true

::: agentdiff.evaluator.SideEffect
    options:
      show_root_heading: true

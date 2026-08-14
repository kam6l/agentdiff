"""Evaluator configuration regression tests."""

from pathlib import Path

from agentdiff.diff_engine import DiffEngine
from agentdiff.evaluator import AgentDiffEvaluator
from agentdiff.trajectory import TrajectoryTracker


def evaluate_half_clean_run(root: Path, threshold: float):
    root.mkdir()
    target = root / "target.txt"
    target.write_text("before\n")

    engine = DiffEngine(
        watch_paths=[str(root)],
        capture_env_vars=False,
        capture_processes=False,
        capture_ports=False,
    )
    before = engine.snapshot()

    target.write_text("after\n")
    (root / "debug.log").write_text("unexpected\n")
    after = engine.snapshot()

    tracker = TrajectoryTracker(task_description="Modify target.txt")
    tracker.start_step("Edit the requested file")
    tracker.record_tool_call("write_file", {"path": str(target)}, result="ok")
    tracker.end_step("Target updated")
    trajectory = tracker.finish()

    evaluator = AgentDiffEvaluator(
        target_paths=[str(root)],
        cleanliness_threshold=threshold,
    )
    evaluator.set_target_mutations([str(target)])
    return evaluator.evaluate_from_snapshots(trajectory, before, after)


def test_evaluator_respects_configurable_cleanliness_threshold(tmp_path: Path) -> None:
    strict = evaluate_half_clean_run(tmp_path / "strict", threshold=0.75)
    permissive = evaluate_half_clean_run(tmp_path / "permissive", threshold=0.5)

    assert strict.metrics.cleanliness_score == 0.5
    assert strict.passed is False
    assert permissive.metrics.cleanliness_score == 0.5
    assert permissive.passed is True

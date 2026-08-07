"""
Demonstration test for AgentDiff core functionality.

This test simulates an agent run that modifies files and environment,
then evaluates the trajectory for cleanliness and side effects.
"""

import os
import tempfile
from pathlib import Path

import pytest

from agentdiff import (
    AgentDiffEvaluator,
    AgentFramework,
    DiffEngine,
    SideEffectSeverity,
    TrajectoryRecord,
    TrajectoryTracker,
)


class TestDiffEngine:
    """Tests for the filesystem/environment diff engine."""

    def test_filesystem_snapshot_capture(self):
        """Test capturing filesystem snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("hello world")
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").write_text("nested")

            engine = DiffEngine(watch_paths=[tmpdir])
            fs_snap, _env_snap = engine.snapshot()

            assert str(test_file) in fs_snap.file_hashes
            assert str(subdir / "nested.txt") in fs_snap.file_hashes
            assert str(subdir) in fs_snap.directories

    def test_filesystem_diff_detects_changes(self):
        """Test diff detects file creation, modification, deletion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = DiffEngine(watch_paths=[tmpdir])

            # Create a file first, then snapshot
            new_file = Path(tmpdir) / "created.txt"
            new_file.write_text("new content")

            mod_file = Path(tmpdir) / "modify.txt"
            mod_file.write_text("original")

            del_file = Path(tmpdir) / "delete.txt"
            del_file.write_text("to delete")

            # Initial snapshot (after creating files)
            pre_fs, pre_env = engine.snapshot()

            # Modify existing
            mod_file.write_text("modified")

            # Delete a file
            del_file.unlink()

            post_fs, post_env = engine.snapshot()

            diff = engine.diff(pre_fs, post_fs, pre_env, post_env)

            # Check created - should NOT include created.txt since it existed in pre
            # But we can verify created.txt is in pre_fs
            assert str(new_file) in pre_fs.file_hashes

            # Check modified
            modified = [d for d in diff.filesystem_diffs if d.diff_type.value == "file_modified"]
            assert any("modify.txt" in d.path for d in modified)

            # Check deleted
            deleted = [d for d in diff.filesystem_diffs if d.diff_type.value == "file_deleted"]
            assert any("delete.txt" in d.path for d in deleted)

    def test_environment_diff(self):
        """Test environment variable diffs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = DiffEngine(watch_paths=[tmpdir])
            pre_fs, pre_env = engine.snapshot()

            # Modify environment - add new var and modify existing
            os.environ["AGENT_TEST_VAR"] = "test_value"
            # Set a var that will be "existing" - first snapshot captures current state
            # so we need to set it before pre_snapshot for it to show as modified
            # Actually, let's test adding a new var
            os.environ["NEW_TEST_VAR"] = "new_value"

            post_fs, post_env = engine.snapshot()

            diff = engine.diff(pre_fs, post_fs, pre_env, post_env)

            env_added = [d for d in diff.environment_diffs if d.diff_type.value == "env_var_added"]
            # Should detect both new vars
            assert any("AGENT_TEST_VAR" in d.path for d in env_added)
            assert any("NEW_TEST_VAR" in d.path for d in env_added)

            # Cleanup
            del os.environ["AGENT_TEST_VAR"]
            del os.environ["NEW_TEST_VAR"]


class TestTrajectoryTracker:
    """Tests for trajectory tracking."""

    def test_basic_trajectory_recording(self):
        """Test recording a simple trajectory."""
        tracker = TrajectoryTracker(
            task_description="Test task",
            framework=AgentFramework.CUSTOM,
        )

        tracker.start_step(thought="I need to read a file")
        tracker.record_tool_call(
            "read_file", {"path": "/tmp/test.txt"}, result="content", duration_ms=100
        )
        tracker.end_step(observation="File read successfully")

        tracker.start_step(thought="Now I'll write a file")
        tracker.record_tool_call(
            "write_file", {"path": "/tmp/out.txt", "content": "hello"}, result="ok", duration_ms=50
        )
        tracker.end_step(observation="File written")

        record = tracker.finish(final_result="success")

        assert record.total_steps == 2
        assert record.total_tool_calls == 2
        assert record.final_result == "success"
        assert record.steps[0].tool_calls[0].name == "read_file"
        assert record.steps[1].tool_calls[0].name == "write_file"

    def test_track_tool_context_records_result(self):
        """The tool context's setter stores the result on the trajectory."""
        tracker = TrajectoryTracker(task_description="Context manager test")
        tracker.start_step(thought="Call a tool")

        with tracker.track_tool("lookup", {"query": "agentdiff"}) as set_result:
            set_result({"found": True})

        tracker.end_step(observation="Lookup complete")
        record = tracker.finish()

        assert record.steps[0].tool_calls[0].result == {"found": True}

    def test_trajectory_save_load(self):
        """Test saving and loading trajectory records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = TrajectoryTracker(task_description="Save/load test")
            tracker.start_step()
            tracker.record_tool_call("test_tool", {"arg": "value"}, result="done")
            tracker.end_step()
            record = tracker.finish()

            save_path = Path(tmpdir) / "trajectory.json"
            record.save(save_path)

            loaded = TrajectoryRecord.load(save_path)
            assert loaded.run_id == record.run_id
            assert loaded.task_description == record.task_description
            assert loaded.total_tool_calls == 1

    def test_loop_detection(self):
        """Test detection of repeated tool call patterns."""
        tracker = TrajectoryTracker(task_description="Loop test")
        # Simulate a loop: read -> write -> read -> write -> read -> write
        for i in range(6):
            tracker.start_step()
            tracker.record_tool_call(
                "read_file", {"path": f"/tmp/file{i % 2}.txt"}, result="content"
            )
            tracker.record_tool_call("write_file", {"path": f"/tmp/out{i % 2}.txt"}, result="ok")
            tracker.end_step()
        record = tracker.finish()

        loops = record.detect_loops(min_repeat=2)
        assert len(loops) > 0
        # Should detect the read/write pattern
        pattern_names = [loop["pattern"] for loop in loops]
        assert any("read_file" in p and "write_file" in p for p in pattern_names)


class TestEvaluator:
    """Tests for evaluation and metrics."""

    def test_cleanliness_metrics_computation(self):
        """Test cleanliness metrics are computed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup: create target file
            target_file = Path(tmpdir) / "target.txt"
            target_file.write_text("original")

            engine = DiffEngine(watch_paths=[tmpdir])
            pre_fs, pre_env = engine.snapshot()

            # Simulate agent: modifies target (good) and creates temp file (bad)
            target_file.write_text("modified")
            (Path(tmpdir) / "temp_junk.txt").write_text("junk")

            post_fs, post_env = engine.snapshot()

            # Create trajectory
            tracker = TrajectoryTracker(task_description="Modify target")
            tracker.start_step()
            tracker.record_tool_call("edit_file", {"path": str(target_file)}, result="ok")
            tracker.record_tool_call(
                "write_file", {"path": str(Path(tmpdir) / "temp_junk.txt")}, result="ok"
            )
            tracker.end_step()
            trajectory = tracker.finish()

            # Evaluate
            evaluator = AgentDiffEvaluator(target_paths=[tmpdir])
            evaluator.set_target_mutations([str(target_file)])
            result = evaluator.evaluate_from_snapshots(
                trajectory, (pre_fs, pre_env), (post_fs, post_env)
            )

            # Check metrics
            assert result.metrics.total_mutations >= 2  # target + junk
            assert result.metrics.target_mutations >= 1  # target file
            assert result.metrics.unintended_mutations >= 1  # junk file
            assert result.metrics.cleanliness_score < 1.0  # Not perfect

    def test_side_effect_detection(self):
        """Test detection of critical side effects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            important_file = Path(tmpdir) / "important.txt"
            important_file.write_text("do not delete")

            engine = DiffEngine(watch_paths=[tmpdir])
            pre_fs, pre_env = engine.snapshot()

            # Agent deletes important file (critical side effect)
            important_file.unlink()

            post_fs, post_env = engine.snapshot()

            tracker = TrajectoryTracker(task_description="Dangerous task")
            tracker.start_step()
            tracker.record_tool_call("delete_file", {"path": str(important_file)}, result="deleted")
            tracker.end_step()
            trajectory = tracker.finish()

            evaluator = AgentDiffEvaluator(target_paths=[tmpdir])
            evaluator.set_target_mutations([])  # No expected mutations
            result = evaluator.evaluate_from_snapshots(
                trajectory, (pre_fs, pre_env), (post_fs, post_env)
            )

            # Should detect critical side effect
            critical_effects = [
                se for se in result.side_effects if se.severity == SideEffectSeverity.CRITICAL
            ]
            assert len(critical_effects) > 0
            assert not result.passed  # Should fail due to critical effect

    def test_evaluation_pass_criteria(self):
        """Test evaluation passes for clean runs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = Path(tmpdir) / "target.txt"
            target_file.write_text("original")

            engine = DiffEngine(watch_paths=[tmpdir])
            pre_fs, pre_env = engine.snapshot()

            # Clean run: only modifies target
            target_file.write_text("modified cleanly")

            post_fs, post_env = engine.snapshot()

            tracker = TrajectoryTracker(task_description="Clean task")
            tracker.start_step()
            tracker.record_tool_call("edit_file", {"path": str(target_file)}, result="ok")
            tracker.end_step()
            trajectory = tracker.finish()

            evaluator = AgentDiffEvaluator(target_paths=[tmpdir])
            evaluator.set_target_mutations([str(target_file)])
            result = evaluator.evaluate_from_snapshots(
                trajectory, (pre_fs, pre_env), (post_fs, post_env)
            )

            assert result.metrics.cleanliness_score == 1.0
            assert result.passed


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline_simulation(self):
        """Test complete agent evaluation pipeline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup project structure
            project = Path(tmpdir) / "project"
            project.mkdir()
            (project / "main.py").write_text("def foo():\n    return 1\n")
            (project / "test.py").write_text("def test_foo():\n    assert foo() == 1\n")

            engine = DiffEngine(watch_paths=[str(project)])
            pre_fs, pre_env = engine.snapshot()

            # Simulate agent fixing a bug but introducing a side effect
            (project / "main.py").write_text("def foo():\n    return 2\n")  # Target change
            (project / "debug.log").write_text("DEBUG: entered foo\n")  # Side effect
            (project / "config.json").write_text('{"debug": true}\n')  # Side effect

            post_fs, post_env = engine.snapshot()

            # Record trajectory
            tracker = TrajectoryTracker(
                task_description="Fix foo() to return 2",
                framework=AgentFramework.CUSTOM,
            )
            tracker.start_step(thought="Reading main.py to understand the bug")
            tracker.record_tool_call(
                "read_file", {"path": str(project / "main.py")}, result="def foo():\n    return 1\n"
            )
            tracker.end_step()

            tracker.start_step(thought="Fixing the return value")
            tracker.record_tool_call(
                "write_file",
                {"path": str(project / "main.py"), "content": "def foo():\n    return 2\n"},
                result="ok",
            )
            tracker.end_step()

            tracker.start_step(thought="Adding debug logging")
            tracker.record_tool_call(
                "write_file",
                {"path": str(project / "debug.log"), "content": "DEBUG: entered foo\n"},
                result="ok",
            )
            tracker.record_tool_call(
                "write_file",
                {"path": str(project / "config.json"), "content": '{"debug": true}\n'},
                result="ok",
            )
            tracker.end_step()

            trajectory = tracker.finish(final_result="Bug fixed, but added debug artifacts")

            # Evaluate
            evaluator = AgentDiffEvaluator(target_paths=[str(project)])
            evaluator.set_target_mutations([str(project / "main.py")])

            result = evaluator.evaluate_from_snapshots(
                trajectory, (pre_fs, pre_env), (post_fs, post_env)
            )

            # Verify results
            assert result.metrics.target_mutations == 1  # main.py
            assert result.metrics.unintended_mutations == 2  # debug.log, config.json
            assert result.metrics.cleanliness_score == pytest.approx(1 / 3, rel=0.1)
            assert len(result.side_effects) == 2
            assert not result.passed  # Failed due to side effects

            # Print summary for manual inspection
            result.print_summary()


if __name__ == "__main__":
    # Run tests manually
    pytest.main([__file__, "-v", "--tb=short"])

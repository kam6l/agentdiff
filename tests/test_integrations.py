"""Framework integration regression tests."""

from pathlib import Path
from uuid import uuid4

import pytest

from agentdiff import AgentDiffConfig, AgentDiffSession


def test_session_records_and_evaluates_a_framework_agnostic_run(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("before\n")
    config = AgentDiffConfig(
        root=str(tmp_path),
        target_paths=["target.txt"],
        cleanliness_threshold=0.8,
        capture_env_vars=False,
        capture_processes=False,
        capture_ports=False,
    )

    with AgentDiffSession(task_description="Update target", config=config) as session:
        target.write_text("after\n")
        (tmp_path / "unexpected.log").write_text("debug\n")
        session.record(
            thought="Update the requested file",
            tool_name="write_file",
            tool_args={"path": str(target)},
            observation="Target updated",
        )

    result = session.evaluate()

    assert result.metrics.total_steps == 1
    assert result.metrics.cleanliness_score == pytest.approx(0.5)
    assert result.passed is False


def test_langchain_callback_records_tool_step_and_evaluates_state(tmp_path: Path) -> None:
    callback_module = pytest.importorskip("agentdiff.integrations.langchain_callback")
    callback_class = callback_module.AgentDiffCallbackHandler

    target = tmp_path / "target.txt"
    target.write_text("before\n")
    callback = callback_class(
        task_description="Update target",
        target_paths=["target.txt"],
        root=str(tmp_path),
        capture_env_vars=False,
        capture_processes=False,
        capture_ports=False,
    )
    callback.start()

    target.write_text("after\n")
    (tmp_path / "unexpected.txt").write_text("debug\n")
    run_id = uuid4()
    callback.on_tool_start(
        {"name": "write_file"},
        f'{{"path": "{target}"}}',
        run_id=run_id,
    )
    callback.on_tool_end("ok", run_id=run_id)

    result = callback.get_evaluation_result()

    assert result.metrics.total_steps == 1
    assert result.metrics.cleanliness_score == pytest.approx(0.5)
    assert result.passed is False

"""CLI regression tests."""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff import TrajectoryTracker
from agentdiff.demo import run_demo


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the installed AgentDiff module in an isolated working directory."""
    return subprocess.run(
        [sys.executable, "-m", "agentdiff.cli", *args],
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )


def test_cli_help_only_lists_implemented_commands(tmp_path: Path) -> None:
    result = run_cli("--help", cwd=tmp_path)

    assert result.returncode == 0
    assert "snapshot" in result.stdout
    assert "diff" in result.stdout
    assert "eval" in result.stdout
    assert "replay" not in result.stdout
    assert "init" not in result.stdout


def test_demo_json_output_is_machine_readable(capsys) -> None:
    run_demo(show_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is False
    assert payload["metrics"]["cleanliness_score"] < 1.0


def test_demo_json_ignores_live_process_churn(capsys, monkeypatch) -> None:
    process_snapshots = iter(
        [
            [SimpleNamespace(info={"pid": 1})],
            [SimpleNamespace(info={"pid": 1}), SimpleNamespace(info={"pid": 2})],
        ]
    )
    monkeypatch.setattr(psutil, "process_iter", lambda _attrs: iter(next(process_snapshots)))
    monkeypatch.setattr(psutil, "net_connections", lambda **_kwargs: [])

    run_demo(show_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"]["total_mutations"] == 3


def test_cli_snapshot_files_round_trip_into_diff(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "target.txt"
    target.write_text("before\n")

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    snapshot_flags = ("--no-env", "--no-proc", "--no-ports")

    first = run_cli(
        "snapshot",
        "--root",
        str(workspace),
        *snapshot_flags,
        "-o",
        str(before),
        cwd=tmp_path,
    )
    assert first.returncode == 0, first.stderr

    target.write_text("after\n")
    second = run_cli(
        "snapshot",
        "--root",
        str(workspace),
        *snapshot_flags,
        "-o",
        str(after),
        cwd=tmp_path,
    )
    assert second.returncode == 0, second.stderr

    result = run_cli(
        "diff",
        str(before),
        str(after),
        "--root",
        str(workspace),
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "Files: +0 ~1 -0" in result.stdout

    json_result = run_cli(
        "diff",
        str(before),
        str(after),
        "--root",
        str(workspace),
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert json_result.returncode == 0, json_result.stderr
    payload = json.loads(json_result.stdout)
    assert payload["summary"]["file_modified"] == 1


def test_cli_ignores_its_own_snapshot_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    artifacts = workspace / ".agentdiff"
    artifacts.mkdir(parents=True)
    target = workspace / "target.txt"
    target.write_text("before\n")

    before = artifacts / "before.json"
    after = artifacts / "after.json"
    flags = ("--no-env", "--no-proc", "--no-ports")

    first = run_cli(
        "snapshot",
        "--root",
        str(workspace),
        *flags,
        "-o",
        str(before),
        cwd=tmp_path,
    )
    assert first.returncode == 0, first.stderr

    target.write_text("after\n")
    second = run_cli(
        "snapshot",
        "--root",
        str(workspace),
        *flags,
        "-o",
        str(after),
        cwd=tmp_path,
    )
    assert second.returncode == 0, second.stderr

    result = run_cli(
        "diff",
        str(before),
        str(after),
        "--root",
        str(workspace),
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"] == {"file_modified": 1}


def test_cli_snapshot_disable_flags_skip_system_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "snapshot.json"

    result = run_cli(
        "snapshot",
        "--root",
        str(workspace),
        "--no-env",
        "--no-proc",
        "--no-ports",
        "-o",
        str(output),
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    snapshot = json.loads(output.read_text())
    assert snapshot["environment"]["env_vars"] == {}
    assert snapshot["environment"]["process_pids"] == []
    assert snapshot["environment"]["open_ports"] == []


def test_cli_eval_returns_json_and_applies_threshold(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "target.txt"
    target.write_text("before\n")

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    trajectory_path = tmp_path / "trajectory.json"
    snapshot_flags = ("--no-env", "--no-proc", "--no-ports")

    first = run_cli(
        "snapshot",
        "--root",
        str(workspace),
        *snapshot_flags,
        "-o",
        str(before),
        cwd=tmp_path,
    )
    assert first.returncode == 0, first.stderr

    target.write_text("after\n")
    (workspace / "debug.log").write_text("unexpected\n")

    second = run_cli(
        "snapshot",
        "--root",
        str(workspace),
        *snapshot_flags,
        "-o",
        str(after),
        cwd=tmp_path,
    )
    assert second.returncode == 0, second.stderr

    tracker = TrajectoryTracker(task_description="Modify target.txt")
    tracker.start_step("Edit the requested file")
    tracker.record_tool_call("write_file", {"path": str(target)}, result="ok")
    tracker.end_step("Target updated")
    tracker.finish().save(trajectory_path)

    result = run_cli(
        "eval",
        str(trajectory_path),
        "--pre",
        str(before),
        "--post",
        str(after),
        "--root",
        str(workspace),
        "--target",
        str(target),
        "--threshold",
        "0.8",
        "--format",
        "json",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["metrics"]["cleanliness_score"] == 0.5
    assert payload["passed"] is False

    gated = run_cli(
        "eval",
        str(trajectory_path),
        "--pre",
        str(before),
        "--post",
        str(after),
        "--root",
        str(workspace),
        "--target",
        str(target),
        "--threshold",
        "0.8",
        "--format",
        "json",
        "--fail-on-failure",
        cwd=tmp_path,
    )
    assert gated.returncode == 1
    assert json.loads(gated.stdout)["passed"] is False

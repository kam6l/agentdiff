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
    assert "run" in result.stdout
    assert "inspect" in result.stdout
    assert "rollback" in result.stdout
    assert "cleanup" in result.stdout
    assert "doctor" in result.stdout
    assert "policy" in result.stdout
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


def test_cli_policy_init_validate_and_explain(tmp_path: Path) -> None:
    policy_path = tmp_path / "agentdiff.yaml"

    initialized = run_cli(
        "policy",
        "init",
        "--output",
        str(policy_path),
        cwd=tmp_path,
    )
    assert initialized.returncode == 0, initialized.stderr
    assert policy_path.exists()

    validated = run_cli(
        "policy",
        "validate",
        "--policy",
        str(policy_path),
        cwd=tmp_path,
    )
    assert validated.returncode == 0, validated.stderr
    assert "valid schema version 1" in validated.stdout

    explained = run_cli(
        "policy",
        "explain",
        ".env",
        "--policy",
        str(policy_path),
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert explained.returncode == 0, explained.stderr
    decision = json.loads(explained.stdout)
    assert decision["action"] == "deny"
    assert decision["rule"].startswith("filesystem.deny")


def test_cli_run_inspect_list_and_safe_rollback(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "filesystem": {
                    "allow_write": ["intended.txt"],
                    "deny": [".env"],
                    "default": "review",
                },
                "process": {"allow": ["python*"], "default": "deny"},
                "network": {"mode": "off"},
            }
        ),
        encoding="utf-8",
    )
    script = (
        "from pathlib import Path; "
        "Path('intended.txt').write_text('keep', encoding='utf-8'); "
        "Path('.env').write_text('remove', encoding='utf-8')"
    )

    executed = run_cli(
        "run",
        "--root",
        str(workspace),
        "--policy",
        str(policy_path),
        "--task",
        "CLI transaction",
        "--format",
        "json",
        "--",
        sys.executable,
        "-c",
        script,
        cwd=tmp_path,
    )
    assert executed.returncode == 3, executed.stderr
    payload = json.loads(executed.stdout)
    run_id = payload["run_id"]
    assert payload["status"] == "denied"
    assert payload["blast_radius"]["score"] == 65

    inspected = run_cli(
        "inspect",
        run_id,
        "--root",
        str(workspace),
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["result"]["run_id"] == run_id

    verified = run_cli(
        "verify",
        run_id,
        "--root",
        str(workspace),
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["ok"] is True

    listed = run_cli("runs", "--root", str(workspace), "--format", "json", cwd=tmp_path)
    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout)[0]["run_id"] == run_id

    rolled_back = run_cli(
        "rollback",
        run_id,
        "--root",
        str(workspace),
        "--safe-only",
        "--format",
        "json",
        cwd=tmp_path,
    )
    assert rolled_back.returncode == 0, rolled_back.stderr
    assert json.loads(rolled_back.stdout)["conflicts"] == []
    assert (workspace / "intended.txt").read_text(encoding="utf-8") == "keep"
    assert not (workspace / ".env").exists()


def test_cli_run_can_select_anthropic_sandbox_runtime(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "filesystem": {"allow_write": ["result.txt"], "default": "review"},
                "process": {"allow": ["python*"], "default": "deny"},
                "network": {"mode": "off"},
            }
        ),
        encoding="utf-8",
    )
    wrapper = tmp_path / "fake-srt"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:1] == ['--settings']:\n"
        "    args = args[2:]\n"
        "os.execv(args[0], args)\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    settings = tmp_path / "srt-settings.json"
    settings.write_text("{}\n", encoding="utf-8")

    executed = run_cli(
        "run",
        "--root",
        str(workspace),
        "--policy",
        str(policy_path),
        "--runtime",
        "srt",
        "--srt-executable",
        str(wrapper),
        "--srt-settings",
        str(settings),
        "--format",
        "json",
        "--",
        sys.executable,
        "-c",
        "from pathlib import Path; Path('result.txt').write_text('ok')",
        cwd=tmp_path,
    )

    assert executed.returncode == 0, executed.stderr
    runtime = json.loads(executed.stdout)["runtime"]
    assert runtime["backend"] == "anthropic-sandbox-runtime"
    assert runtime["enforcement"] == "external_sandbox_requested"


def test_cli_run_returns_nonzero_when_command_launch_fails(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy_path = tmp_path / "policy.json"
    command = "agentdiff-command-that-does-not-exist"
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "filesystem": {"default": "review"},
                "process": {"allow": [command], "default": "deny"},
                "network": {"mode": "off"},
            }
        ),
        encoding="utf-8",
    )

    executed = run_cli(
        "run",
        "--root",
        str(workspace),
        "--policy",
        str(policy_path),
        "--format",
        "json",
        "--fail-on",
        "never",
        "--",
        command,
        cwd=tmp_path,
    )

    assert executed.returncode == 1
    payload = json.loads(executed.stdout)
    assert payload["status"] == "error"
    assert payload["execution_error"]["type"] == "FileNotFoundError"


def test_cli_doctor_reports_port_observation_without_network_control(tmp_path: Path) -> None:
    result = run_cli("doctor", "--format", "json", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["local_runtime"] is True
    assert report["listening_port_observation"] == "partial"
    assert report["listening_port_observation_scope"] == "machine_wide"
    assert report["network_observation"] is False
    assert report["network_enforcement"] is False
    assert report["sandboxed"] is False

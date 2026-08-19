"""CLI regression tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

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
    assert "snapshot" not in result.stdout
    assert "eval" not in result.stdout
    assert "{run,inspect,runs,verify,rollback,cleanup,doctor,policy,cortex," in result.stdout
    assert "run" in result.stdout
    assert "inspect" in result.stdout
    assert "rollback" in result.stdout
    assert "cleanup" in result.stdout
    assert "doctor" in result.stdout
    assert "policy" in result.stdout
    assert "cortex" in result.stdout
    assert "bootstrap" in result.stdout
    assert "prove" in result.stdout
    assert "promote" in result.stdout
    assert "repair" in result.stdout
    assert "wrap" in result.stdout
    assert "serve" in result.stdout
    assert "heal" not in result.stdout
    assert "replay" not in result.stdout
    assert "init" in result.stdout


def test_package_module_runs_the_cli(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "agentdiff", "--help"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "Observe, govern, score, and recover" in result.stdout


def test_cortex_is_one_explicit_experimental_namespace(tmp_path: Path) -> None:
    result = run_cli("cortex", "--help", cwd=tmp_path)

    assert result.returncode == 0
    assert "{skill,context,memory,agent,advise}" in result.stdout
    assert "autonomous" not in result.stdout.lower()
    assert "heal" not in result.stdout.lower()


def test_run_summary_leads_with_outcome_counts_and_recovery(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "filesystem": {
                    "allow_write": ["src/**"],
                    "deny": [".env"],
                    "default": "review",
                },
                "process": {"allow": ["python*"], "default": "deny"},
                "network": {"mode": "off"},
                "rollback": {"enabled": True},
            }
        ),
        encoding="utf-8",
    )
    script = (
        "from pathlib import Path; "
        "Path('src').mkdir(); "
        "Path('src/result.py').write_text('ok'); "
        "Path('notes.txt').write_text('review'); "
        "Path('.env').write_text('protected')"
    )

    result = run_cli(
        "run",
        "--root",
        str(workspace),
        "--policy",
        str(policy_path),
        "--",
        sys.executable,
        "-c",
        script,
        cwd=tmp_path,
    )

    assert result.returncode == 3
    assert result.stdout.startswith("Task completed\n\n")
    assert "Expected changes:   1" in result.stdout
    assert "Unexpected changes: 1" in result.stdout
    assert "Protected changes:  1" in result.stdout
    assert "Blast Radius: CRITICAL" in result.stdout
    assert "Recovery available: YES" in result.stdout
    assert "Policy outcome: DENY" in result.stdout


def test_demo_json_output_is_machine_readable(capsys) -> None:
    run_demo(show_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "denied"
    assert payload["safety_outcome"] == "deny"
    assert payload["runtime"]["returncode"] == 0
    assert {change["path"] for change in payload["changes"]} == {
        "calculator.py",
        "config.json",
        "debug.log",
    }


def test_demo_json_uses_primary_transaction_schema(capsys) -> None:
    run_demo(show_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["command_decision"]["action"] == "allow"
    assert payload["blast_radius"]["score"] > 0


@pytest.mark.parametrize("command", ["snapshot", "diff", "eval", "heal"])
def test_legacy_and_overstated_commands_are_not_public_cli_verbs(
    tmp_path: Path, command: str
) -> None:
    result = run_cli(command, cwd=tmp_path)

    assert result.returncode == 2
    assert "invalid choice" in result.stderr


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


@pytest.mark.skipif(os.name == "nt", reason="test shim relies on POSIX shebang execution")
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

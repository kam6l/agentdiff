from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING

import psutil
import pytest

from agentdiff.doctor import CapabilityStatus, collect_doctor_report, doctor_report
from agentdiff.runtime import LocalRuntime, OwnedProcess, RuntimeBackend, SandboxRuntime

if TYPE_CHECKING:
    from pathlib import Path


def test_local_runtime_preserves_argv_and_uses_root_as_cwd(tmp_path: Path) -> None:
    output = tmp_path / "argv.json"
    injection_marker = tmp_path / "shell-was-used"
    metacharacter = f"value with spaces; touch {injection_marker}"
    script = (
        "import json, pathlib, sys; "
        "pathlib.Path('argv.json').write_text("
        "json.dumps({'argv': sys.argv[1:], 'cwd': str(pathlib.Path.cwd())}), "
        "encoding='utf-8')"
    )
    runtime: RuntimeBackend = LocalRuntime(root=tmp_path)

    result = runtime.run([sys.executable, "-c", script, metacharacter], timeout_seconds=5)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload == {"argv": [metacharacter], "cwd": str(tmp_path.resolve())}
    assert not injection_marker.exists()
    assert result.argv == (sys.executable, "-c", script, metacharacter)
    assert result.cwd == str(tmp_path.resolve())
    assert result.returncode == 0
    assert result.timed_out is False


def test_sandbox_runtime_wraps_argv_without_shell_parsing(tmp_path: Path) -> None:
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
    output = tmp_path / "sandbox-argv.json"
    argument = "space and ; metacharacter"
    command = (
        sys.executable,
        "-c",
        "import json,pathlib,sys; pathlib.Path('sandbox-argv.json').write_text("
        "json.dumps(sys.argv[1:]), encoding='utf-8')",
        argument,
    )

    result = SandboxRuntime(
        root=tmp_path,
        executable=wrapper,
        settings=settings,
    ).run(command, timeout_seconds=5)

    assert json.loads(output.read_text(encoding="utf-8")) == [argument]
    assert result.argv == command
    assert result.backend == "anthropic-sandbox-runtime"
    assert result.enforcement == "external_sandbox_requested"
    assert result.wrapper_argv == (
        str(wrapper.resolve()),
        "--settings",
        str(settings.resolve()),
        *command,
    )


def test_sandbox_runtime_rejects_non_string_argv(tmp_path: Path) -> None:
    wrapper = tmp_path / "fake-srt"
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wrapper.chmod(0o700)

    runtime = SandboxRuntime(root=tmp_path, executable=wrapper)

    with pytest.raises(TypeError, match="every argv item must be a string"):
        runtime.run([sys.executable, 1])  # type: ignore[list-item]


def test_local_runtime_enforces_timeout_and_cleans_the_owned_child(tmp_path: Path) -> None:
    runtime = LocalRuntime(root=tmp_path, poll_interval_seconds=0.01)
    started = time.monotonic()

    result = runtime.run(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout_seconds=0.15,
    )

    assert time.monotonic() - started < 5
    assert result.timed_out is True
    assert result.returncode == 124
    assert result.duration_seconds < 5
    assert len(result.owned_processes) >= 1
    child = result.owned_processes[0]
    assert child.pid > 0
    assert child.create_time > 0
    assert result.cleanup is not None
    assert result.cleanup.targeted >= 1
    assert not psutil.pid_exists(child.pid)


def test_local_runtime_cleans_direct_child_when_observation_is_interrupted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = LocalRuntime(root=tmp_path)
    launched: dict[str, subprocess.Popen[str]] = {}
    real_popen = subprocess.Popen

    def tracked_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        launched["process"] = process
        return process

    original_observe = runtime._observe_process_tree

    def interrupt_after_observation(root_pid, owned):
        original_observe(root_pid, owned)
        raise KeyboardInterrupt

    monkeypatch.setattr("agentdiff.runtime.local.subprocess.Popen", tracked_popen)
    monkeypatch.setattr(runtime, "_observe_process_tree", interrupt_after_observation)

    with pytest.raises(KeyboardInterrupt):
        runtime.run([sys.executable, "-c", "import time; time.sleep(30)"])

    process = launched["process"]
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)
        pytest.fail("interrupted runtime left its direct child running")


def test_local_runtime_tracks_and_cleans_descendants(tmp_path: Path) -> None:
    script = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        "pathlib.Path('descendant.pid').write_text(str(child.pid), encoding='utf-8'); "
        "time.sleep(30)"
    )
    runtime = LocalRuntime(root=tmp_path, poll_interval_seconds=0.01)

    result = runtime.run([sys.executable, "-c", script], timeout_seconds=0.3)

    descendant_pid = int((tmp_path / "descendant.pid").read_text(encoding="utf-8"))
    descendants = [item for item in result.owned_processes if item.relation == "descendant"]
    assert any(item.pid == descendant_pid and item.create_time > 0 for item in descendants)
    assert result.cleanup is not None
    assert result.cleanup.targeted >= 2
    assert not psutil.pid_exists(descendant_pid)


def test_local_runtime_cleans_owned_residue_after_successful_parent_exit(tmp_path: Path) -> None:
    script = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        "pathlib.Path('residue.pid').write_text(str(child.pid), encoding='utf-8'); "
        "time.sleep(0.2)"
    )
    runtime = LocalRuntime(root=tmp_path, poll_interval_seconds=0.01)

    result = runtime.run([sys.executable, "-c", script], timeout_seconds=5)
    residue_pid = int((tmp_path / "residue.pid").read_text(encoding="utf-8"))

    try:
        assert result.returncode == 0
        assert result.cleanup is not None
        assert any(item.pid == residue_pid for item in result.owned_processes)
        assert not psutil.pid_exists(residue_pid)
    finally:
        if psutil.pid_exists(residue_pid):
            psutil.Process(residue_pid).kill()


@pytest.mark.skipif(os.name != "posix", reason="requires a POSIX process session")
def test_local_runtime_finds_reparented_child_in_its_execution_session(tmp_path: Path) -> None:
    script = (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        "pathlib.Path('reparented.pid').write_text(str(child.pid), encoding='utf-8')"
    )
    runtime = LocalRuntime(root=tmp_path, poll_interval_seconds=0.2)

    result = runtime.run([sys.executable, "-c", script], timeout_seconds=5)
    child_pid = int((tmp_path / "reparented.pid").read_text(encoding="utf-8"))

    try:
        assert any(item.pid == child_pid for item in result.owned_processes)
        assert not psutil.pid_exists(child_pid)
    finally:
        if psutil.pid_exists(child_pid):
            psutil.Process(child_pid).kill()


def test_cleanup_refuses_even_near_matching_reused_pid(tmp_path: Path, monkeypatch) -> None:
    recorded = OwnedProcess(
        pid=4242,
        create_time=100.0,
        parent_pid=1,
        relation="descendant",
    )

    class ReusedProcess:
        pid = recorded.pid
        terminate_called = False
        kill_called = False

        def create_time(self) -> float:
            return recorded.create_time + 0.0000001

        def terminate(self) -> None:
            self.terminate_called = True

        def kill(self) -> None:
            self.kill_called = True

    reused = ReusedProcess()
    monkeypatch.setattr(psutil, "Process", lambda _pid: reused)
    monkeypatch.setattr(psutil, "wait_procs", lambda processes, timeout: (processes, []))

    report = LocalRuntime(root=tmp_path).cleanup([recorded])

    assert report.targeted == 0
    assert report.outcomes[0].action == "pid_reused"
    assert reused.terminate_called is False
    assert reused.kill_called is False


def test_cleanup_reports_a_process_that_survives_forceful_cleanup(
    tmp_path: Path, monkeypatch
) -> None:
    recorded = OwnedProcess(
        pid=4343,
        create_time=200.0,
        parent_pid=1,
        relation="descendant",
    )

    class SurvivingProcess:
        pid = recorded.pid
        terminate_called = False
        kill_called = False

        def create_time(self) -> float:
            return recorded.create_time

        def terminate(self) -> None:
            self.terminate_called = True

        def kill(self) -> None:
            self.kill_called = True

    survivor = SurvivingProcess()
    monkeypatch.setattr(psutil, "Process", lambda _pid: survivor)
    monkeypatch.setattr(psutil, "wait_procs", lambda processes, timeout: ([], processes))

    report = LocalRuntime(root=tmp_path).cleanup([recorded], grace_period_seconds=0)

    assert report.targeted == 1
    assert report.outcomes[0].action == "still_running"
    assert survivor.terminate_called is True
    assert survivor.kill_called is True


def test_runtime_result_is_json_serializable(tmp_path: Path) -> None:
    result = LocalRuntime(root=tmp_path).run(
        [sys.executable, "-c", "pass"],
        timeout_seconds=5,
    )

    payload = result.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert payload["schema_version"] == 1
    assert payload["argv"] == [sys.executable, "-c", "pass"]
    assert payload["owned_processes"][0]["pid"] > 0
    assert payload["owned_processes"][0]["create_time"] > 0


def test_port_diff_is_labeled_machine_wide_observation(tmp_path: Path, monkeypatch) -> None:
    existing = SimpleNamespace(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        laddr=("127.0.0.1", 41001),
        status=psutil.CONN_LISTEN,
        pid=10,
    )
    opened = SimpleNamespace(
        family=socket.AF_INET6,
        type=socket.SOCK_STREAM,
        laddr=("::1", 41002),
        status=psutil.CONN_LISTEN,
        pid=11,
    )
    snapshots = iter([[existing], [existing, opened]])
    monkeypatch.setattr(psutil, "net_connections", lambda *, kind: next(snapshots))

    result = LocalRuntime(root=tmp_path).run([sys.executable, "-c", "pass"])

    observation = result.port_observation
    assert observation.scope == "machine_wide"
    assert observation.level == "observation"
    assert observation.ownership_attributed is False
    assert observation.enforced is False
    assert [(item.host, item.port, item.pid) for item in observation.opened] == [("::1", 41002, 11)]
    assert observation.closed == ()


def test_port_observation_permission_failure_is_evidence_not_a_crash(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        psutil,
        "net_connections",
        lambda *, kind: (_ for _ in ()).throw(psutil.AccessDenied()),
    )

    result = LocalRuntime(root=tmp_path).run([sys.executable, "-c", "pass"])

    assert result.returncode == 0
    assert result.port_observation.opened == ()
    assert result.port_observation.closed == ()
    assert result.port_observation.error is not None


def test_incomplete_port_snapshots_do_not_infer_a_machine_wide_delta(
    tmp_path: Path, monkeypatch
) -> None:
    endpoint = SimpleNamespace(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        laddr=("127.0.0.1", 41003),
        status=psutil.CONN_LISTEN,
        pid=12,
    )
    snapshots = iter([psutil.AccessDenied(), [endpoint]])

    def net_connections(*, kind):
        snapshot = next(snapshots)
        if isinstance(snapshot, BaseException):
            raise snapshot
        return snapshot

    monkeypatch.setattr(psutil, "net_connections", net_connections)

    result = LocalRuntime(root=tmp_path).run([sys.executable, "-c", "pass"])

    assert result.port_observation.opened == ()
    assert result.port_observation.closed == ()
    assert "before snapshot" in (result.port_observation.error or "")


def test_doctor_reports_an_honest_capability_matrix() -> None:
    report = collect_doctor_report()
    capabilities = {item.name: item for item in report.capabilities}

    assert capabilities["filesystem_observation"].status is CapabilityStatus.YES
    assert capabilities["filesystem_rollback"].status is CapabilityStatus.YES
    assert capabilities["process_ownership"].status is CapabilityStatus.YES
    assert capabilities["process_cleanup"].status is CapabilityStatus.YES
    assert capabilities["listening_port_observation"].status is CapabilityStatus.PARTIAL
    assert capabilities["network_observation"].status is CapabilityStatus.NO
    assert capabilities["network_enforcement"].status is CapabilityStatus.NO
    assert capabilities["sandbox"].status is CapabilityStatus.NO
    assert capabilities["docker_backend"].status is CapabilityStatus.NO
    assert isinstance(capabilities["docker_backend"].detected, bool)
    assert capabilities["mcp_interception"].status is CapabilityStatus.NO

    payload = report.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert payload["network_observation"] is False
    assert payload["network_enforcement"] is False
    assert payload["filesystem_enforcement"] is False
    assert payload["filesystem_policy_evaluation"] == "post_run"
    assert payload["sandboxed"] is False
    assert doctor_report()["capabilities"] == payload["capabilities"]


def test_doctor_reports_detected_sandbox_runtime_adapter(monkeypatch) -> None:
    monkeypatch.setattr(
        "agentdiff.doctor.shutil.which",
        lambda name: "/usr/bin/srt" if name == "srt" else None,
    )

    report = doctor_report()

    capability = report["capabilities"]["anthropic_sandbox_runtime"]
    assert capability["status"] == "partial"
    assert capability["detected"] is True
    assert report["sandbox_runtime_cli_detected"] is True
    assert report["enforcement_backends"] == ["anthropic-sandbox-runtime"]

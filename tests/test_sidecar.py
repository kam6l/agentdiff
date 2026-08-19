"""Tests for the zero-touch sidecar, wrap adapter, and notifications (system 1)."""

from __future__ import annotations

import json
import sys
import threading
import time
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff.sidecar import Notifier, SidecarClient, WrapRunner
from agentdiff.sidecar.notify import Notification
from agentdiff.sidecar.server import SidecarServer, _SidecarHTTPServer

from .fake_proof import fake_env_factory


@pytest.fixture()
def sidecar(tmp_path: Path):
    """Start an in-process sidecar and return a client plus state dir."""
    import os

    server = SidecarServer(tmp_path, port=0)
    httpd = _SidecarHTTPServer(("127.0.0.1", 0), server)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    actual_port = int(httpd.server_address[1])
    (server.state_dir / "port").write_text(str(actual_port), encoding="utf-8")
    (server.state_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
    client = SidecarClient(tmp_path)
    yield client, server, httpd
    httpd.shutdown()
    httpd.server_close()


def test_sidecar_status_and_bootstrap(sidecar) -> None:  # type: ignore[no-untyped-def]
    client, server, _ = sidecar
    status = client.status()
    assert status["ok"] is True
    assert status["root"] == str(server.root)
    assert status["sessions"] == 0

    # A repo with no policy yet: bootstrap compiles one.
    (server.root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (server.root / "src").mkdir()
    (server.root / "src" / "__init__.py").write_text("")
    response = client.bootstrap(force=True)
    assert response["ok"] is True
    assert (server.root / "agentdiff.yaml").is_file()


def test_sidecar_run_transaction(sidecar) -> None:  # type: ignore[no-untyped-def]
    client, server, _ = sidecar
    (server.root / "value.txt").write_text("base", encoding="utf-8")
    response = client.run(
        argv=[
            sys.executable,
            "-c",
            "from pathlib import Path; Path('value.txt').write_text('agent')",
        ],
        task="sidecar run",
    )
    assert response["ok"] is True
    run_id = response["run_id"]
    assert run_id
    assert response["result"]["status"] == "passed"
    # The capsule is sealed and verifiable.
    from agentdiff.transaction import RunStore

    report = RunStore.open(server.root, run_id).verify_integrity()
    assert report.ok


def test_sidecar_session_events_evaluate_tool_calls(sidecar) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = sidecar
    begun = client.session_begin(task="check tool call policy", agent="codex")
    session_id = begun["session_id"]
    decision = client.session_event(
        session_id=session_id,
        event_type="tool_call",
        data={"tool_name": "write_file", "arguments": {"path": ".env"}},
    )
    assert decision["decision"] is not None
    assert decision["decision"]["action"] in {"deny", "review", "allow"}
    ended = client.session_end(session_id=session_id)
    assert ended["session"]["task"] == "check tool call policy"
    assert len(ended["session"]["events"]) == 1


def test_sidecar_notify(sidecar) -> None:  # type: ignore[no-untyped-def]
    client, server, _ = sidecar
    response = client.notify(kind="human", title="scope review", message="dependency added")
    assert response["ok"] is True
    log = (server.root / ".agentdiff" / "notifications.jsonl").read_text(encoding="utf-8")
    assert "scope review" in log
    assert "dependency added" in log


def test_notifier_appends_and_echoes(tmp_path: Path) -> None:
    notifier = Notifier(tmp_path, echo=False)
    path = notifier.notify(Notification(kind="auto", title="hello", message="world"))
    assert path.is_file()
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert entries[0]["title"] == "hello"
    notifier.notify(Notification(kind="retry", title="second"))
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert len(entries) == 2


def _wrapped_repo(root: Path) -> None:
    (root / "value.txt").write_text("base", encoding="utf-8")
    (root / "agentdiff.yaml").write_text(
        """
version: 2
filesystem:
  allow_write: ["**"]
  default: allow
process:
  allow: ["python*"]
  default: deny
network:
  mode: "off"
proof:
  image: "python:3.12-slim"
  network: false
  setup: []
  build: [["python", "-m", "compileall", "-q", "."]]
  tests:
    - ["python", "-c", "from pathlib import Path; assert Path('value.txt').read_text() == 'fixed'"]
""",
        encoding="utf-8",
    )


def test_wrap_zero_touch_proven_and_promoted(tmp_path: Path) -> None:
    _wrapped_repo(tmp_path)
    runner = WrapRunner(
        tmp_path,
        enable_proof=True,
        enable_repair=True,
        enable_promote=True,
        notify=False,
        environment_factory=fake_env_factory(),
    )
    summary = runner.wrap(
        [sys.executable, "-c", "from pathlib import Path; Path('value.txt').write_text('fixed')"],
        task="zero-touch wrap",
    )
    assert summary.status == "PROVEN", summary.to_dict()
    assert summary.routing == "AUTO"
    assert summary.promotion_status == "PROMOTED"
    assert (tmp_path / "value.txt").read_text(encoding="utf-8") == "fixed"


def test_wrap_repair_loop_fixes_with_custom_builder(tmp_path: Path) -> None:
    _wrapped_repo(tmp_path)
    runner, calls = _counting_runner()

    from agentdiff.policy import load_policy_file
    from agentdiff.repair import RepairLoop
    from agentdiff.repair.packet import FailurePacket  # noqa: TC001
    from agentdiff.transaction import AgentRunTransaction
    from agentdiff.workspace import WarmWorkspaceFactory, compute_identity

    factory = WarmWorkspaceFactory(tmp_path)
    policy = load_policy_file(tmp_path / "agentdiff.yaml")
    identity = compute_identity(tmp_path, policy=policy)
    workspace = factory.create_workspace(identity)

    def fixing_repair(packet: FailurePacket) -> list[str]:
        del packet
        return [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('value.txt').write_text('fixed')",
        ]

    def attempt_workspace():
        return factory.create_workspace(identity).path

    def base_preparer(destination):
        from agentdiff.sidecar.adapters import _copy_writable

        _copy_writable(workspace.base.path, destination)

    try:
        transaction = AgentRunTransaction(
            root=workspace.path,
            policy=policy,
            task="first attempt",
        ).run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('value.txt').write_text('broken')",
            ]
        )

        loop = RepairLoop(
            workspace.path,
            transaction.run_id,
            policy=policy,
            max_attempts=3,
            environment_factory=fake_env_factory(runner),
            base_preparer=base_preparer,
            repair_command_builder=fixing_repair,
            attempt_workspace_factory=attempt_workspace,
        )
        outcome = loop.run()
        assert outcome.status == "REPAIRED", outcome.to_dict()
        assert len(calls) >= 2
    finally:
        workspace.close()


def test_wrap_without_proof_returns_not_proven(tmp_path: Path) -> None:
    _wrapped_repo(tmp_path)
    wrap = WrapRunner(
        tmp_path,
        enable_proof=False,
        enable_promote=False,
        notify=False,
    )
    summary = wrap.wrap(
        [sys.executable, "-c", "from pathlib import Path; Path('value.txt').write_text('fixed')"],
        task="no proof",
    )
    assert summary.status == "NOT_PROVEN"
    assert (tmp_path / "value.txt").read_text(encoding="utf-8") == "base"


def test_sidecar_daemon_start_and_stop(tmp_path: Path) -> None:
    """Ensure a detached daemon can be spawned and stopped."""
    from agentdiff.sidecar import ensure_sidecar

    client = ensure_sidecar(tmp_path)
    status = client.status()
    assert status["ok"] is True
    client.request("POST", "/v1/stop")
    deadline = time.monotonic() + 10.0
    port_file = tmp_path / ".agentdiff" / "sidecar" / "port"
    while time.monotonic() < deadline and port_file.exists():
        time.sleep(0.1)
    assert not port_file.exists()


def _counting_runner():
    calls: list[int] = []

    def runner(phase: str, command: tuple[str, ...]):
        del phase, command
        calls.append(1)
        # First proof fails, later proofs pass: the repair loop is exercised.
        return (1, (0, 1)) if len(calls) <= 1 else (0, (1, 1))

    return runner, calls

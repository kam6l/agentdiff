"""Tests for the proof-driven automatic repair loop (system 3)."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff.policy import load_policy
from agentdiff.repair import RepairLoop, default_repair_command_builder
from agentdiff.repair.packet import FailurePacket
from agentdiff.transaction import AgentRunTransaction

from .fake_proof import counting_runner, fake_env_factory


def _policy() -> object:
    return load_policy(
        {
            "version": 2,
            "filesystem": {"allow_write": ["**"], "default": "allow"},
            "process": {"allow": ["python*"], "default": "deny"},
            "network": {"mode": "off"},
            "proof": {
                "image": "python:3.12-slim",
                "network": False,
                "setup": [],
                "build": [["python", "-m", "compileall", "-q", "."]],
                "tests": [
                    [
                        "python",
                        "-c",
                        "from pathlib import Path; assert Path('value.txt').read_text() == 'fixed'",
                    ]
                ],
            },
        }
    )


def _run_failing_attempt(root: Path) -> str:
    """Run an agent command that writes the wrong value, producing a failing patch."""
    policy = _policy()
    result = AgentRunTransaction(
        root=root,
        policy=policy,
        task="attempt that needs repair",
    ).run(
        [sys.executable, "-c", "from pathlib import Path; Path('value.txt').write_text('broken')"]
    )
    return result.run_id


def test_repair_loop_retries_until_proof_passes(tmp_path: Path) -> None:
    (tmp_path / "value.txt").write_text("base", encoding="utf-8")
    run_id = _run_failing_attempt(tmp_path)

    runner, _ = counting_runner(fail_first=1)
    policy = _policy()

    def repair_command_builder(packet: FailurePacket) -> list[str]:
        del packet
        return [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('value.txt').write_text('fixed')",
        ]

    loop = RepairLoop(
        tmp_path,
        run_id,
        policy=policy,
        max_attempts=3,
        environment_factory=fake_env_factory(runner),
        repair_command_builder=repair_command_builder,
    )
    outcome = loop.run()
    assert outcome.status == "REPAIRED"
    assert outcome.repaired_run_id is not None
    assert len(outcome.attempts) == 2
    assert outcome.attempts[0].verdict == "NOT_PROVEN"
    assert outcome.attempts[1].verdict == "PROVEN"
    assert (tmp_path / "value.txt").read_text(encoding="utf-8") == "fixed"
    # The failure packet was persisted for evidence.
    assert len(list((tmp_path / ".agentdiff" / "repair" / run_id).glob("*.json"))) >= 1


def test_repair_loop_stops_after_max_attempts(tmp_path: Path) -> None:
    (tmp_path / "value.txt").write_text("base", encoding="utf-8")
    run_id = _run_failing_attempt(tmp_path)
    runner, _ = counting_runner(fail_first=99)

    def repair_command_builder(packet: FailurePacket) -> list[str]:
        del packet
        return [sys.executable, "-c", "pass"]

    loop = RepairLoop(
        tmp_path,
        run_id,
        policy=_policy(),
        max_attempts=2,
        environment_factory=fake_env_factory(runner),
        repair_command_builder=repair_command_builder,
    )
    outcome = loop.run()
    assert outcome.status == "FAILED"
    assert len(outcome.attempts) == 2


def test_repair_loop_stops_when_scope_changes(tmp_path: Path) -> None:
    (tmp_path / "value.txt").write_text("base", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("lock-v1\n", encoding="utf-8")
    run_id = _run_failing_attempt(tmp_path)
    runner, _ = counting_runner(fail_first=99)

    def scope_changing_repair(packet: FailurePacket) -> list[str]:
        del packet
        # The repair writes a dependency lockfile: a trust-boundary change.
        return [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('uv.lock').write_text('new-dependency')",
        ]

    loop = RepairLoop(
        tmp_path,
        run_id,
        policy=_policy(),
        max_attempts=3,
        environment_factory=fake_env_factory(runner),
        repair_command_builder=scope_changing_repair,
    )
    outcome = loop.run()
    assert outcome.status == "NEEDS_HUMAN"
    assert "trust boundary" in outcome.human_reason


def test_repair_loop_without_builder_writes_packet(tmp_path: Path) -> None:
    (tmp_path / "value.txt").write_text("base", encoding="utf-8")
    run_id = _run_failing_attempt(tmp_path)
    runner, _ = counting_runner(fail_first=99)
    loop = RepairLoop(
        tmp_path,
        run_id,
        policy=_policy(),
        max_attempts=3,
        environment_factory=fake_env_factory(runner),
        repair_command_builder=None,
    )
    outcome = loop.run()
    assert outcome.status == "NEEDS_AGENT"
    assert outcome.attempts[0].packet_path is not None
    packet_path = tmp_path / outcome.attempts[0].packet_path  # type: ignore[operator]
    assert packet_path.is_file()


def test_repair_loop_respects_max_runtime(tmp_path: Path) -> None:
    (tmp_path / "value.txt").write_text("base", encoding="utf-8")
    run_id = _run_failing_attempt(tmp_path)
    runner, _ = counting_runner(fail_first=99)

    def slow_repair(packet: FailurePacket) -> list[str]:
        del packet
        return [sys.executable, "-c", "import time; time.sleep(0.2)"]

    loop = RepairLoop(
        tmp_path,
        run_id,
        policy=_policy(),
        max_attempts=5,
        max_runtime_seconds=0.05,
        environment_factory=fake_env_factory(runner),
        repair_command_builder=slow_repair,
    )
    outcome = loop.run()
    assert outcome.status == "BLOCKED"


def test_default_repair_command_builder_replaces_prompt(tmp_path: Path) -> None:
    (tmp_path / "value.txt").write_text("base", encoding="utf-8")
    run_id = _run_failing_attempt(tmp_path)
    builder = default_repair_command_builder(["codex", "exec", "do the task"])
    packet = FailurePacket(
        run_id=run_id,
        attempt=1,
        failed_phases=(),
        failed_tests=(),
        changed_files=(),
        policy={"version": 2, "filesystem": {}},
        allowed_scope=("**",),
        risk={},
        reasons=("tests failed",),
    )
    argv = builder(packet)
    assert argv[0] == "codex"
    assert argv[1] == "exec"
    assert "failure packet" in argv[2].lower()
    # The original prompt was replaced, not appended.
    assert argv[2] != "do the task"

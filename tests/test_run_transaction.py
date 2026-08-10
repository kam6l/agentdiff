from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from agentdiff.policy import Policy, PolicyAction, load_policy
from agentdiff.runtime import OwnedProcess, PortObservation, RuntimeResult
from agentdiff.transaction import AgentRunTransaction, RollbackEngine, RunStore


def _policy(*, allow: list[str], deny: list[str]) -> Policy:
    return load_policy(
        {
            "version": 1,
            "filesystem": {
                "allow_write": allow,
                "deny": deny,
                "default": "review",
            },
            "process": {
                "allow": [Path(sys.executable).name],
                "default": "deny",
            },
            "network": {"mode": "off"},
            "limits": {"files_changed": 20, "files_deleted": 5},
        }
    )


def test_missing_cleanup_report_is_scored_as_residual_process_risk(tmp_path: Path) -> None:
    class RuntimeWithoutCleanup:
        def run(self, argv, **_kwargs):
            return RuntimeResult(
                argv=tuple(argv),
                cwd=str(tmp_path),
                returncode=0,
                timed_out=False,
                duration_seconds=0.01,
                owned_processes=(
                    OwnedProcess(
                        pid=999_999_999,
                        create_time=1.0,
                        parent_pid=1,
                        relation="descendant",
                    ),
                ),
                cleanup=None,
                port_observation=PortObservation(),
            )

        def cleanup(self, processes, *, grace_period_seconds=1.0):
            raise AssertionError("transaction must use the runtime result's cleanup evidence")

    policy = load_policy(
        {
            "version": 1,
            "filesystem": {"default": "allow"},
            "process": {"allow": ["agent"], "default": "deny"},
            "network": {"mode": "off"},
        }
    )

    result = AgentRunTransaction(
        root=tmp_path,
        policy=policy,
        runtime=RuntimeWithoutCleanup(),
    ).run(["agent"])

    assert result.blast_radius.counts["orphan_processes"] == 1


def test_transaction_records_policy_enriched_changes_and_durable_artifacts(
    tmp_path: Path,
) -> None:
    script = (
        "from pathlib import Path; "
        "Path('allowed.txt').write_text('ok', encoding='utf-8'); "
        "Path('.env').write_text('unsafe', encoding='utf-8')"
    )
    transaction = AgentRunTransaction(
        root=tmp_path,
        policy=_policy(allow=["allowed.txt"], deny=[".env"]),
        task="write one allowed and one protected file",
    )

    result = transaction.run(
        [sys.executable, "-c", script, "--api-key", "transaction-secret"],
        timeout_seconds=5,
    )

    by_path = {item.path: item for item in result.changes}
    assert result.status == "denied"
    assert result.safety_outcome is PolicyAction.DENY
    assert result.runtime is not None
    assert result.runtime.returncode == 0
    assert by_path["allowed.txt"].decision.action is PolicyAction.ALLOW
    assert by_path[".env"].decision.action is PolicyAction.DENY
    assert result.blast_radius.score == 65
    assert result.blast_radius.level.value == "high"

    run_dir = tmp_path / ".agentdiff" / "runs" / result.run_id
    expected = {
        "after.json",
        "before.json",
        "events.jsonl",
        "metadata.json",
        "policy.json",
        "result.json",
        "runtime.json",
    }
    assert expected <= {path.name for path in run_dir.iterdir()}
    for artifact in run_dir.iterdir():
        if artifact.suffix in {".json", ".jsonl"}:
            assert "transaction-secret" not in artifact.read_text(encoding="utf-8")

    payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["changes"][0]["path"] == ".env"


def test_denied_root_command_is_blocked_before_execution(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    script = f"from pathlib import Path; Path({str(marker)!r}).touch()"
    policy = load_policy(
        {
            "version": 1,
            "process": {"deny": [Path(sys.executable).name], "default": "allow"},
        }
    )

    result = AgentRunTransaction(root=tmp_path, policy=policy).run([sys.executable, "-c", script])

    assert result.status == "blocked"
    assert result.safety_outcome is PolicyAction.DENY
    assert result.runtime is None
    assert result.command_decision.rule == "process.deny[0]"
    assert not marker.exists()
    assert result.changes == []


def test_safe_only_rollback_preserves_allowed_work_and_human_edits(tmp_path: Path) -> None:
    intended = tmp_path / "intended.txt"
    intended.write_text("before", encoding="utf-8")
    script = (
        "from pathlib import Path; "
        "Path('intended.txt').write_text('agent work', encoding='utf-8'); "
        "Path('.env').write_text('collateral', encoding='utf-8')"
    )
    result = AgentRunTransaction(
        root=tmp_path,
        policy=_policy(allow=["intended.txt"], deny=[".env"]),
    ).run([sys.executable, "-c", script], timeout_seconds=5)
    intended.write_text("human follow-up", encoding="utf-8")

    report = RollbackEngine.open(tmp_path, result.run_id).rollback(safe_only=True)

    assert report.conflicts == []
    assert not (tmp_path / ".env").exists()
    assert intended.read_text(encoding="utf-8") == "human follow-up"
    assert [action.path for action in report.actions] == [".env"]


def test_transaction_limit_violations_are_review_evidence(tmp_path: Path) -> None:
    policy = load_policy(
        {
            "version": 1,
            "filesystem": {"allow_write": ["**"], "default": "allow"},
            "process": {"allow": [Path(sys.executable).name], "default": "deny"},
            "limits": {"files_changed": 0},
            "network": {"mode": "off"},
        }
    )
    script = "from pathlib import Path; Path('one.txt').write_text('one', encoding='utf-8')"

    result = AgentRunTransaction(root=tmp_path, policy=policy).run(
        [sys.executable, "-c", script], timeout_seconds=5
    )

    assert result.status == "review"
    assert result.safety_outcome is PolicyAction.REVIEW
    assert result.limit_violations[0].name == "files_changed"
    assert result.blast_radius.counts["budget_violations"] == 1


def test_disabled_rollback_does_not_capture_backups(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("before\n", encoding="utf-8")
    policy = load_policy(
        {
            "version": 1,
            "filesystem": {"allow_write": ["target.txt"], "default": "review"},
            "process": {"allow": [Path(sys.executable).name], "default": "deny"},
            "network": {"mode": "off"},
            "rollback": {"enabled": False, "max_backup_file_mb": 10},
        }
    )

    result = AgentRunTransaction(root=tmp_path, policy=policy).run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('target.txt').write_text('after\\n')",
        ]
    )

    assert result.changes[0].reversible is False
    assert result.changes[0].recovery_reason == "rollback disabled by policy"
    assert not any((tmp_path / ".agentdiff" / "runs" / result.run_id / "backup").iterdir())
    with pytest.raises(PermissionError, match="disabled by policy"):
        RollbackEngine.open(tmp_path, result.run_id).rollback(all_changes=True)


def test_hostile_child_cannot_rewrite_before_evidence_and_backup(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("before", encoding="utf-8")
    policy = _policy(allow=["target.txt"], deny=[])
    script = (
        "import hashlib, json; "
        "from pathlib import Path; "
        "Path('target.txt').write_text('after', encoding='utf-8'); "
        "run = next((Path('.agentdiff') / 'runs').iterdir()); "
        "backup = run / 'backup' / 'target.txt'; "
        "backup.write_text('attacker-controlled', encoding='utf-8'); "
        "before = run / 'before.json'; "
        "payload = json.loads(before.read_text(encoding='utf-8')); "
        "payload['files']['target.txt']['sha256'] = "
        "hashlib.sha256(b'attacker-controlled').hexdigest(); "
        "before.write_text(json.dumps(payload), encoding='utf-8')"
    )

    result = AgentRunTransaction(root=tmp_path, policy=policy).run([sys.executable, "-c", script])
    report = RollbackEngine.open(tmp_path, result.run_id).rollback(all_changes=True)

    assert result.changes[0].reversible is False
    assert "backup integrity" in result.changes[0].recovery_reason
    assert report.actions == []
    assert report.conflicts
    assert target.read_text(encoding="utf-8") == "after"


def test_hostile_child_cannot_forge_trusted_capsule_metadata_or_events(tmp_path: Path) -> None:
    policy = _policy(allow=["target.txt"], deny=[])
    script = (
        "from pathlib import Path; "
        "Path('target.txt').write_text('after', encoding='utf-8'); "
        "run = next((Path('.agentdiff') / 'runs').iterdir()); "
        "(run / 'metadata.json').write_text('{}', encoding='utf-8'); "
        "(run / 'policy.json').write_text('{}', encoding='utf-8'); "
        "(run / 'events.jsonl').write_text('{\"event\": \"forged\"}\\n', encoding='utf-8')"
    )

    result = AgentRunTransaction(root=tmp_path, policy=policy, task="trusted task").run(
        [sys.executable, "-c", script]
    )
    store = RunStore.open(tmp_path, result.run_id)
    events = [
        json.loads(line) for line in (store.run_dir / "events.jsonl").read_text().splitlines()
    ]

    assert store.read_json("metadata.json")["task"] == "trusted task"
    assert store.read_json("policy.json")["version"] == 1
    assert "forged" not in {event.get("type") or event.get("event") for event in events}
    assert store.verify_integrity().ok

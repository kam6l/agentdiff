from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentdiff.policy import load_policy
from agentdiff.transaction import AgentRunTransaction, RunInspector
from agentdiff.transaction.inspection import list_runs
from agentdiff.transaction.store import InvalidRunIdError, RunStore


def _run_once(root: Path, task: str = "inspection test") -> str:
    policy = load_policy(
        {
            "version": 1,
            "filesystem": {"allow_write": ["output.txt"], "default": "review"},
            "process": {"allow": [Path(sys.executable).name], "default": "deny"},
            "network": {"mode": "off"},
        }
    )
    script = "from pathlib import Path; Path('output.txt').write_text('ok', encoding='utf-8')"
    return (
        AgentRunTransaction(root=root, policy=policy, task=task)
        .run([sys.executable, "-c", script])
        .run_id
    )


def test_inspector_loads_unified_run_and_summary(tmp_path: Path) -> None:
    run_id = _run_once(tmp_path)

    inspector = RunInspector(tmp_path, run_id)
    inspection = inspector.inspect()
    summary = inspector.summary()

    assert inspection["metadata"]["run_id"] == run_id
    assert inspection["result"]["changes"][0]["path"] == "output.txt"
    assert inspection["policy"]["version"] == 1
    assert inspection["integrity"]["ok"] is True
    assert summary.run_id == run_id
    assert summary.status == "passed"
    assert summary.safety_outcome == "allow"
    assert summary.blast_radius == 0
    assert summary.returncode == 0
    assert summary.integrity_ok is True


def test_list_runs_returns_newest_first(tmp_path: Path) -> None:
    first = _run_once(tmp_path, "first")
    second = _run_once(tmp_path, "second")

    summaries = list_runs(tmp_path)

    assert {item.run_id for item in summaries} == {first, second}
    assert summaries[0].created_at >= summaries[1].created_at
    assert {item.task for item in summaries} == {"first", "second"}


def test_inspector_rejects_invalid_run_ids(tmp_path: Path) -> None:
    with pytest.raises(InvalidRunIdError):
        RunInspector(tmp_path, "../escape")


def test_cleanup_uses_stored_pid_identity_and_persists_report(tmp_path: Path) -> None:
    store = RunStore.create(tmp_path, task="cleanup", command=["agent"])
    store.write_json(
        "runtime.json",
        {
            "schema_version": 1,
            "owned_processes": [
                {
                    "pid": 999_999_999,
                    "create_time": 1.0,
                    "parent_pid": 1,
                    "relation": "descendant",
                }
            ],
        },
    )
    empty_manifest = {
        "schema_version": 1,
        "root": str(tmp_path),
        "captured_at": "test",
        "files": {},
    }
    store.write_json("policy.json", {"version": 1})
    store.write_json("before.json", empty_manifest)
    store.write_json("after.json", empty_manifest)
    store.write_json("result.json", {"schema_version": 1, "changes": []})
    store.finalize_integrity()

    report = RunInspector(tmp_path, store.run_id).cleanup()

    assert report.targeted == 0
    assert report.outcomes[0].action == "already_exited"
    assert (store.run_dir / "cleanup-result.json").exists()


def test_cleanup_refuses_an_unsealed_capsule(tmp_path: Path) -> None:
    store = RunStore.create(tmp_path, task="cleanup", command=["agent"])
    store.write_json("runtime.json", {"schema_version": 1, "owned_processes": []})

    with pytest.raises(PermissionError, match="sealed capsule integrity is required"):
        RunInspector(tmp_path, store.run_id).cleanup()

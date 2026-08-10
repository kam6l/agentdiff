from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from agentdiff.state.filesystem import FilesystemScanner, diff_manifests
from agentdiff.transaction.rollback import RollbackEngine
from agentdiff.transaction.store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


def _record_run(
    root: Path,
    mutate: object,
    decisions: dict[str, str],
    *,
    seal: bool = True,
) -> RunStore:
    store = RunStore.create(root, task="test rollback", command=["agent"])
    before = FilesystemScanner(root, backup_dir=store.backup_dir).capture(backup=True)
    assert callable(mutate)
    mutate()
    after = FilesystemScanner(root).capture()
    changes = diff_manifests(before, after)
    store.write_json("before.json", before.to_dict())
    store.write_json("after.json", after.to_dict())
    store.write_json(
        "result.json",
        {
            "schema_version": 1,
            "changes": [
                {
                    **change.to_dict(),
                    "decision": decisions.get(change.path, "review"),
                }
                for change in changes
            ],
        },
    )
    store.write_json("policy.json", {"version": 1, "rollback": {"enabled": True}})
    store.write_json("runtime.json", {"schema_version": 1, "owned_processes": []})
    if seal:
        store.finalize_integrity()
    return store


def test_full_rollback_restores_modified_deleted_and_created_files(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "modified.txt").write_text("before", encoding="utf-8")
    (root / "deleted.txt").write_bytes(b"deleted-content")

    def mutate() -> None:
        (root / "modified.txt").write_text("after", encoding="utf-8")
        (root / "deleted.txt").unlink()
        (root / "created.bin").write_bytes(b"created-content")

    store = _record_run(root, mutate, {})
    report = RollbackEngine(root, store.run_id).rollback(all_changes=True)

    assert report.conflicts == []
    assert (root / "modified.txt").read_text(encoding="utf-8") == "before"
    assert (root / "deleted.txt").read_bytes() == b"deleted-content"
    assert not (root / "created.bin").exists()
    assert {item.action for item in report.actions} == {"restored", "removed"}


def test_safe_only_keeps_allowed_files_and_rolls_back_review_or_deny(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()

    def mutate() -> None:
        (root / "src.py").write_text("keep", encoding="utf-8")
        (root / ".env").write_text("remove", encoding="utf-8")
        (root / "debug.log").write_text("remove", encoding="utf-8")

    store = _record_run(
        root,
        mutate,
        {"src.py": "allow", ".env": "deny", "debug.log": "review"},
    )
    report = RollbackEngine(root, store.run_id).rollback(safe_only=True)

    assert report.conflicts == []
    assert (root / "src.py").read_text(encoding="utf-8") == "keep"
    assert not (root / ".env").exists()
    assert not (root / "debug.log").exists()


def test_rollback_refuses_to_overwrite_human_edit_after_run(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "auth.py"
    target.write_text("A", encoding="utf-8")

    def mutate() -> None:
        target.write_text("B", encoding="utf-8")

    store = _record_run(root, mutate, {"auth.py": "deny"})
    target.write_text("C", encoding="utf-8")
    report = RollbackEngine(root, store.run_id).rollback(safe_only=True)

    assert target.read_text(encoding="utf-8") == "C"
    assert len(report.conflicts) == 1
    assert report.conflicts[0].reason == "current state differs from recorded after-state"


def test_rollback_refuses_to_delete_changed_created_file(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "new.txt"

    def mutate() -> None:
        target.write_text("agent", encoding="utf-8")

    store = _record_run(root, mutate, {"new.txt": "deny"})
    target.write_text("human", encoding="utf-8")
    report = RollbackEngine(root, store.run_id).rollback(safe_only=True)

    assert target.read_text(encoding="utf-8") == "human"
    assert len(report.conflicts) == 1


def test_rollback_refuses_path_traversal_in_tampered_result(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("safe", encoding="utf-8")
    store = RunStore.create(root, task="tampered", command=["agent"])
    empty = FilesystemScanner(root).capture()
    store.write_json("before.json", empty.to_dict())
    store.write_json("after.json", empty.to_dict())
    store.write_json(
        "result.json",
        {
            "schema_version": 1,
            "changes": [{"path": "../outside.txt", "change_type": "created", "decision": "deny"}],
        },
    )
    store.write_json("policy.json", {"version": 1, "rollback": {"enabled": True}})
    store.write_json("runtime.json", {"schema_version": 1, "owned_processes": []})
    store.finalize_integrity()

    report = RollbackEngine(root, store.run_id).rollback(safe_only=True)

    assert outside.read_text(encoding="utf-8") == "safe"
    assert len(report.conflicts) == 1
    assert report.conflicts[0].reason == "unsafe path"


def test_rollback_refuses_symlink_and_hardlink_surprises(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "target.txt"
    target.write_text("before", encoding="utf-8")

    def mutate() -> None:
        target.write_text("after", encoding="utf-8")

    store = _record_run(root, mutate, {"target.txt": "deny"})
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")

    report = RollbackEngine(root, store.run_id).rollback(safe_only=True)
    assert outside.read_text(encoding="utf-8") == "outside"
    assert len(report.conflicts) == 1

    if hasattr(os, "link"):
        target.unlink()
        target.write_text("after", encoding="utf-8")
        alias = root / "alias.txt"
        try:
            os.link(target, alias)
        except OSError:
            return
        report = RollbackEngine(root, store.run_id).rollback(safe_only=True)
        assert len(report.conflicts) == 1


def test_rollback_refuses_a_tampered_sealed_capsule(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "created.txt"

    def mutate() -> None:
        target.write_text("agent", encoding="utf-8")

    store = _record_run(root, mutate, {"created.txt": "deny"})
    (store.run_dir / "result.json").write_text(
        '{"schema_version":1,"changes":[]}\n',
        encoding="utf-8",
    )

    report = RollbackEngine(root, store.run_id).rollback(safe_only=True)

    assert target.read_text(encoding="utf-8") == "agent"
    assert report.actions == []
    assert report.conflicts[0].path == "<capsule>"
    assert report.conflicts[0].reason == "capsule integrity verification failed"


def test_rollback_refuses_an_unsealed_capsule(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "created.txt"

    def mutate() -> None:
        target.write_text("agent", encoding="utf-8")

    store = _record_run(root, mutate, {"created.txt": "deny"}, seal=False)

    report = RollbackEngine(root, store.run_id).rollback(safe_only=True)

    assert target.read_text(encoding="utf-8") == "agent"
    assert report.actions == []
    assert report.conflicts[0].path == "<capsule>"
    assert report.conflicts[0].reason == "sealed capsule integrity is required"

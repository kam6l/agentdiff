from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from agentdiff.state.filesystem import (
    FilesystemScanner,
    diff_manifests,
)
from agentdiff.transaction.store import InvalidRunIdError, RunStore

if TYPE_CHECKING:
    from pathlib import Path


def test_scanner_captures_regular_files_without_following_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "project"
    outside = tmp_path / "outside.txt"
    root.mkdir()
    outside.write_text("outside secret", encoding="utf-8")
    (root / "inside.txt").write_text("inside", encoding="utf-8")
    try:
        (root / "escape").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")

    manifest = FilesystemScanner(root).capture()

    assert manifest.files["inside.txt"].sha256 is not None
    assert manifest.files["escape"].kind == "symlink"
    assert manifest.files["escape"].sha256 != manifest.files["inside.txt"].sha256
    assert "outside secret" not in str(manifest.to_dict())


def test_scanner_applies_defaults_and_agentdiffignore(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("private", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "pkg.js").write_text("ignored", encoding="utf-8")
    (root / "generated").mkdir()
    (root / "generated" / "result.txt").write_text("ignored", encoding="utf-8")
    (root / ".agentdiffignore").write_text("generated/**\n", encoding="utf-8")
    (root / "src.py").write_text("tracked", encoding="utf-8")

    manifest = FilesystemScanner(root).capture()

    assert "src.py" in manifest.files
    assert ".agentdiffignore" in manifest.files
    assert not any(path.startswith(".git/") for path in manifest.files)
    assert not any(path.startswith("node_modules/") for path in manifest.files)
    assert not any(path.startswith("generated/") for path in manifest.files)


def test_before_capture_creates_private_backups(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "nested").mkdir()
    (root / "nested" / "data.bin").write_bytes(b"\x00\x01payload")
    store = RunStore.create(root, task="test", command=["python", "agent.py"])

    manifest = FilesystemScanner(root, backup_dir=store.backup_dir).capture(backup=True)
    record = manifest.files["nested/data.bin"]

    assert record.backup_path == "nested/data.bin"
    backup = store.backup_dir / record.backup_path
    assert backup.read_bytes() == b"\x00\x01payload"
    if os.name != "nt":
        assert backup.stat().st_mode & 0o777 == 0o600
        assert store.run_dir.stat().st_mode & 0o777 == 0o700


@pytest.mark.skipif(os.name == "nt", reason="backslash is a separator on Windows")
def test_nonportable_filename_does_not_abort_backup_capture(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    unusual = root / "bad\\name.txt"
    unusual.write_text("content", encoding="utf-8")
    store = RunStore.create(root, task="test", command=["agent"])

    manifest = FilesystemScanner(root, backup_dir=store.backup_dir).capture(backup=True)

    assert manifest.files["bad\\name.txt"].sha256 is not None
    assert manifest.files["bad\\name.txt"].backup_path is None
    assert manifest.files["bad\\name.txt"].backup_error == "nonportable path"


def test_oversized_or_hardlinked_files_are_not_marked_recoverable(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "large.bin").write_bytes(b"x" * 2048)
    store = RunStore.create(root, task="test", command=["agent"])

    manifest = FilesystemScanner(
        root,
        backup_dir=store.backup_dir,
        backup_max_file_mb=0.0001,
    ).capture(backup=True)

    assert manifest.files["large.bin"].backup_path is None
    assert manifest.files["large.bin"].backup_error == "file exceeds backup limit"

    if hasattr(os, "link"):
        (root / "original.txt").write_text("linked", encoding="utf-8")
        try:
            os.link(root / "original.txt", root / "alias.txt")
        except OSError:
            return
        linked = FilesystemScanner(root, backup_dir=store.backup_dir).capture(backup=True)
        assert linked.files["original.txt"].link_count > 1
        assert linked.files["original.txt"].backup_path is None
        assert linked.files["original.txt"].backup_error == "hardlinked file"


def test_diff_manifests_reports_content_mode_create_and_delete(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    changed = root / "changed.txt"
    deleted = root / "deleted.txt"
    changed.write_text("before", encoding="utf-8")
    deleted.write_text("gone", encoding="utf-8")
    before = FilesystemScanner(root).capture()

    changed.write_text("after", encoding="utf-8")
    deleted.unlink()
    (root / "created.txt").write_text("new", encoding="utf-8")
    after = FilesystemScanner(root).capture()

    changes = {change.path: change for change in diff_manifests(before, after)}

    assert changes["changed.txt"].change_type == "modified"
    assert changes["changed.txt"].content_changed is True
    assert changes["deleted.txt"].change_type == "deleted"
    assert changes["created.txt"].change_type == "created"


def test_diff_reports_metadata_change_when_content_was_not_hashed(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    target = root / "large.bin"
    target.write_bytes(b"aa")
    before = FilesystemScanner(root, hash_max_file_mb=0).capture()

    target.write_bytes(b"bb")
    stat_result = target.stat()
    os.utime(target, ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 1))
    after = FilesystemScanner(root, hash_max_file_mb=0).capture()

    assert before.files["large.bin"].sha256 is None
    assert "large.bin" in before.unsupported
    changes = {change.path: change for change in diff_manifests(before, after)}
    assert changes["large.bin"].change_type == "modified"
    assert changes["large.bin"].content_changed is True


def test_protected_pattern_overrides_user_ignore_rule(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".agentdiffignore").write_text("secrets/**\n", encoding="utf-8")
    (root / "secrets").mkdir()
    (root / "secrets" / "token.txt").write_text("before", encoding="utf-8")

    manifest = FilesystemScanner(root, protected_patterns=["secrets/**"]).capture()

    assert "secrets/token.txt" in manifest.files


def test_protected_pattern_overrides_default_dependency_ignore(tmp_path: Path) -> None:
    root = tmp_path / "project"
    target = root / "node_modules" / "package" / "index.js"
    target.parent.mkdir(parents=True)
    target.write_text("before", encoding="utf-8")

    manifest = FilesystemScanner(
        root,
        protected_patterns=["node_modules/**"],
    ).capture()

    assert "node_modules/package/index.js" in manifest.files


def test_run_store_writes_versioned_artifacts_and_rejects_bad_ids(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = RunStore.create(root, task="Fix auth", command=["codex", "--flag", "a b"])

    store.write_json("result.json", {"status": "ok"})
    store.append_event("test_event", {"safe": True})

    metadata = store.read_json("metadata.json")
    assert metadata["schema_version"] == 1
    assert metadata["task"] == "Fix auth"
    assert metadata["command"] == ["codex", "--flag", "a b"]
    assert store.read_json("result.json") == {"status": "ok"}
    assert "test_event" in (store.run_dir / "events.jsonl").read_text(encoding="utf-8")

    for bad in ("../escape", "/absolute", "bad/slash", "", "."):
        with pytest.raises(InvalidRunIdError):
            RunStore.open(root, bad)


def test_run_store_redacts_command_and_event_secrets(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = RunStore.create(
        root,
        task="redaction",
        command=["agent", "--api-key", "command-secret"],
    )

    store.append_event("tool_event", {"token": "event-secret", "safe": "visible"})
    metadata = (store.run_dir / "metadata.json").read_text(encoding="utf-8")
    events = (store.run_dir / "events.jsonl").read_text(encoding="utf-8")

    assert "command-secret" not in metadata
    assert "event-secret" not in events
    assert "<redacted>" in metadata
    assert "<redacted>" in events
    assert "visible" in events


def test_run_store_integrity_seals_core_artifacts_and_detects_tampering(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = RunStore.create(root, task="integrity", command=["agent"])
    empty_manifest = {
        "schema_version": 1,
        "root": str(root.resolve()),
        "captured_at": "test",
        "files": {},
    }
    store.write_json("policy.json", {"version": 1})
    store.write_json("before.json", empty_manifest)
    store.write_json("after.json", empty_manifest)
    store.write_json("runtime.json", {"schema_version": 1, "owned_processes": []})
    store.write_json("result.json", {"schema_version": 1, "status": "passed"})

    manifest = store.finalize_integrity()
    verified = store.verify_integrity()

    assert "metadata.json" in manifest["files"]
    assert "events.jsonl" in manifest["files"]
    assert "result.json" in manifest["files"]
    assert verified.present is True
    assert verified.ok is True
    assert verified.issues == ()

    store.append_event("rollback_started", {"path": "safe.txt"})
    assert (store.run_dir / "recovery-events.jsonl").is_file()
    assert store.verify_integrity().ok is True

    (store.run_dir / "result.json").write_text('{"status":"tampered"}\n', encoding="utf-8")
    tampered = store.verify_integrity()
    assert tampered.ok is False
    assert any(issue.path == "result.json" for issue in tampered.issues)


def test_run_store_refuses_to_seal_an_incomplete_capsule(tmp_path: Path) -> None:
    store = RunStore.create(tmp_path, task="incomplete", command=["agent"])
    store.write_json("result.json", {"schema_version": 1, "status": "passed"})

    with pytest.raises(RuntimeError, match="missing required sealed artifacts"):
        store.finalize_integrity()

    assert not (store.run_dir / "integrity.json").exists()


def test_run_store_refuses_to_seal_when_a_referenced_backup_is_missing(tmp_path: Path) -> None:
    store = RunStore.create(tmp_path, task="missing backup", command=["agent"])
    manifest = {
        "schema_version": 1,
        "root": str(tmp_path.resolve()),
        "captured_at": "test",
        "files": {"secret.txt": {"backup_path": "secret.txt"}},
    }
    store.write_json("policy.json", {"version": 1})
    store.write_json("before.json", manifest)
    store.write_json("after.json", {**manifest, "files": {}})
    store.write_json("runtime.json", {"schema_version": 1, "owned_processes": []})
    store.write_json("result.json", {"schema_version": 1, "changes": []})

    with pytest.raises(RuntimeError, match=r"backup/secret\.txt"):
        store.finalize_integrity()


def test_run_store_rejects_replaced_run_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    store = RunStore.create(tmp_path, task="identity", command=["true"])
    moved = store.run_dir.with_name(f"{store.run_id}-moved")
    store.run_dir.rename(moved)
    store.run_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(InvalidRunIdError, match="run directory identity changed"):
        store.write_json("result.json", {"status": "forged"})

    assert not (outside / "result.json").exists()


def test_run_store_open_rejects_a_symlinked_agentdiff_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = RunStore.create(root, task="ancestor", command=["true"])
    external = tmp_path / "external-agentdiff"
    (root / ".agentdiff").rename(external)
    try:
        (root / ".agentdiff").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    with pytest.raises((FileNotFoundError, InvalidRunIdError), match=r"run|unsafe"):
    with pytest.raises((FileNotFoundError, InvalidRunIdError), match="run|unsafe"):
        RunStore.open(root, store.run_id)

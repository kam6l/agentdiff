"""Adversarial promotion recovery and fail-closed tests.

These tests simulate every crash point in the promotion write-ahead
state machine by constructing the exact on-disk journal/host state a crash
would leave behind, then asserting that recovery is deterministic,
convergent, and fails closed on ambiguity or corruption.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from agentdiff.promotion import (
    EntryState,
    JournalEntry,
    JournalLoadOutcome,
    JournalState,
    PromotionJournal,
    PromotionLockError,
    PromotionRecovery,
    PromotionRecoveryError,
    WorkspaceLease,
)
from agentdiff.promotion.lock import PromotionLockError as _LockError  # noqa: F401


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_journal(
    root: Path,
    *,
    state: JournalState,
    entries: list[JournalEntry],
    run_id: str = "run-crash",
    schema_version: int = 3,
) -> PromotionJournal:
    journal = PromotionJournal(
        root=root,
        run_id=run_id,
        patch_digest="patch-digest",
        state=state,
        entries=entries,
    )
    journal.schema_version = schema_version
    journal.persist()
    return journal


def base_entry(
    path: str,
    change_type: str,
    *,
    base_content: str | None = None,
    result_content: str | None = None,
    base_mode: int | None = 0o644,
    result_mode: int | None = 0o644,
    state: EntryState = EntryState.APPLIED,
    with_backup: bool = True,
    run_id: str = "run-crash",
) -> JournalEntry:
    backup_rel = (
        f".agentdiff/backups/{run_id}/{path}"
        if with_backup and change_type in {"modified", "deleted"}
        else None
    )
    return JournalEntry(
        path=path,
        change_type=change_type,
        base_sha256=sha256(base_content) if base_content is not None else None,
        result_sha256=sha256(result_content) if result_content is not None else None,
        base_mode=base_mode,
        result_mode=result_mode,
        base_size=len(base_content.encode()) if base_content is not None else None,
        result_size=len(result_content.encode()) if result_content is not None else None,
        state=state,
        staged_relpath=None,
        backup_relpath=backup_rel,
    )


def write_backup(root: Path, relpath: str, content: str, run_id: str = "run-crash") -> Path:
    target = root / ".agentdiff" / "backups" / run_id / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Corrupt / malformed journal must fail closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "{ not json",
        "[]",
        '{"schema_version": 3}',
        '{"schema_version": 3, "run_id": 1, "patch_digest": "x", "state": "APPLYING", "entries": []}',
        '{"schema_version": 3, "run_id": "r", "patch_digest": "x", "state": "BOGUS", "entries": []}',
        '{"schema_version": 3, "run_id": "r", "patch_digest": "x", "state": "APPLYING", "entries": [{"path": "a.txt"}]}',
        '{"schema_version": 99, "run_id": "r", "patch_digest": "x", "state": "APPLYING", "entries": []}',
        '{"schema_version": 3, "run_id": "r", "patch_digest": "x", "state": "APPLYING", "entries": [{"path": "a.txt", "change_type": "explode", "state": "PREPARED"}]}',
    ],
)
def test_corrupt_journal_fails_closed(tmp_path: Path, payload: str) -> None:
    (tmp_path / ".agentdiff").mkdir()
    (tmp_path / ".agentdiff" / "promotion-journal.json").write_text(payload, encoding="utf-8")

    loaded = PromotionJournal.load(tmp_path)
    assert loaded.outcome is JournalLoadOutcome.CORRUPT_JOURNAL

    with pytest.raises(PromotionRecoveryError, match="recovery state cannot be established"):
        PromotionRecovery(tmp_path).check_and_recover()


def test_no_journal_returns_none(tmp_path: Path) -> None:
    assert PromotionRecovery(tmp_path).check_and_recover() is None


def test_journal_symlink_fails_closed(tmp_path: Path) -> None:
    (tmp_path / ".agentdiff").mkdir()
    (tmp_path / "target.json").write_text("{}", encoding="utf-8")
    os.symlink(tmp_path / "target.json", tmp_path / ".agentdiff" / "promotion-journal.json")

    loaded = PromotionJournal.load(tmp_path)
    assert loaded.outcome is JournalLoadOutcome.CORRUPT_JOURNAL
    with pytest.raises(PromotionRecoveryError):
        PromotionRecovery(tmp_path).check_and_recover()


# ---------------------------------------------------------------------------
# Path traversal and symlink attacks in journal content
# ---------------------------------------------------------------------------


def test_journal_path_traversal_fails_closed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("do not touch", encoding="utf-8")
    entry = base_entry(
        "../outside.txt", "created", result_content="x", state=EntryState.APPLY_INTENT
    )
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])
    with pytest.raises(PromotionRecoveryError, match="unsafe|path"):
        PromotionRecovery(tmp_path).check_and_recover()
    assert outside.read_text(encoding="utf-8") == "do not touch"


def test_journal_targets_agentdiff_internal_state_fails_closed(tmp_path: Path) -> None:
    entry = base_entry(".agentdiff/promotion-journal.json", "created", result_content="x")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])
    with pytest.raises(PromotionRecoveryError, match="internal state"):
        PromotionRecovery(tmp_path).check_and_recover()


def test_journal_backup_escapes_approved_dir_fails_closed(tmp_path: Path) -> None:
    entry = JournalEntry(
        path="target.txt",
        change_type="modified",
        base_sha256=sha256("base"),
        result_sha256=sha256("result"),
        base_mode=0o644,
        result_mode=0o644,
        state=EntryState.APPLIED,
        backup_relpath=".agentdiff/backups/other-run/target.txt",
    )
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])
    with pytest.raises(PromotionRecoveryError, match="approved backup directory"):
        PromotionRecovery(tmp_path).check_and_recover()


def test_journal_backup_parent_symlink_fails_closed(tmp_path: Path) -> None:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "target.txt").write_text("base", encoding="utf-8")
    os.symlink(outside_dir, tmp_path / "evil")
    entry = JournalEntry(
        path="target.txt",
        change_type="modified",
        base_sha256=sha256("base"),
        result_sha256=sha256("result"),
        base_mode=0o644,
        result_mode=0o644,
        state=EntryState.APPLIED,
        backup_relpath=".agentdiff/backups/run-crash/evil/target.txt",
    )
    (tmp_path / ".agentdiff" / "backups" / "run-crash" / "evil").mkdir(parents=True)
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])
    with pytest.raises(PromotionRecoveryError):
        PromotionRecovery(tmp_path).check_and_recover()


def test_host_parent_symlink_fails_closed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "target.txt").write_text("result", encoding="utf-8")
    os.symlink(outside, tmp_path / "link")
    entry = base_entry(
        "link/target.txt", "modified", base_content="base", result_content="result"
    )
    write_backup(tmp_path, "link/target.txt", "base")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])
    with pytest.raises(PromotionRecoveryError, match="parent|directory"):
        PromotionRecovery(tmp_path).check_and_recover()


# ---------------------------------------------------------------------------
# Backup integrity validation
# ---------------------------------------------------------------------------


def test_backup_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    host = tmp_path / "target.txt"
    host.write_text("result", encoding="utf-8")
    entry = base_entry(
        "target.txt", "modified", base_content="base", result_content="result"
    )
    write_backup(tmp_path, "target.txt", "TAMPERED BACKUP CONTENT")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    with pytest.raises(PromotionRecoveryError, match="digest mismatch"):
        PromotionRecovery(tmp_path).check_and_recover()
    assert host.read_text(encoding="utf-8") == "result"


def test_backup_symlink_fails_closed(tmp_path: Path) -> None:
    host = tmp_path / "target.txt"
    host.write_text("result", encoding="utf-8")
    entry = base_entry(
        "target.txt", "modified", base_content="base", result_content="result"
    )
    backup_dir = tmp_path / ".agentdiff" / "backups" / "run-crash"
    backup_dir.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("base", encoding="utf-8")
    os.symlink(outside, backup_dir / "target.txt")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    with pytest.raises(PromotionRecoveryError):
        PromotionRecovery(tmp_path).check_and_recover()
    assert host.read_text(encoding="utf-8") == "result"


def test_backup_hardlink_fails_closed(tmp_path: Path) -> None:
    host = tmp_path / "target.txt"
    host.write_text("result", encoding="utf-8")
    entry = base_entry(
        "target.txt", "modified", base_content="base", result_content="result"
    )
    backup = write_backup(tmp_path, "target.txt", "base")
    os.link(backup, tmp_path / "extra-link")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    with pytest.raises(PromotionRecoveryError, match="link count"):
        PromotionRecovery(tmp_path).check_and_recover()


# ---------------------------------------------------------------------------
# Crash-point matrix
# ---------------------------------------------------------------------------


def test_crash_before_any_apply_cleans_up(tmp_path: Path) -> None:
    entry = base_entry(
        "target.txt",
        "modified",
        base_content="base",
        result_content="result",
        state=EntryState.PREPARED,
    )
    write_backup(tmp_path, "target.txt", "base")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])
    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report is not None
    assert report.status == "RECOVERED"
    assert report.restored == []
    assert (tmp_path / "target.txt").exists() is False  # never created


def test_crash_after_first_file_recovers_all(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first-result", encoding="utf-8")
    second.write_text("second-result", encoding="utf-8")
    entries = [
        base_entry("first.txt", "modified", base_content="first-base", result_content="first-result"),
        base_entry("second.txt", "modified", base_content="second-base", result_content="second-result"),
        base_entry("third.txt", "created", result_content="third-result"),
    ]
    write_backup(tmp_path, "first.txt", "first-base")
    write_backup(tmp_path, "second.txt", "second-base")
    # Crash state: first applied, second intent, third prepared.
    entries[0].state = EntryState.APPLIED
    entries[1].state = EntryState.APPLY_INTENT
    entries[2].state = EntryState.PREPARED
    make_journal(tmp_path, state=JournalState.APPLYING, entries=entries)

    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report is not None
    assert report.status == "RECOVERED"
    assert first.read_text(encoding="utf-8") == "first-base"
    assert second.read_text(encoding="utf-8") == "second-base"
    assert not (tmp_path / "third.txt").exists()
    assert "first.txt" in report.restored
    assert "second.txt" in report.restored
    # The PREPARED created entry was never applied, so nothing to clean.
    assert "third.txt" not in report.cleaned


def test_crash_after_mutation_before_journal_update_is_recovered(tmp_path: Path) -> None:
    """APPLY_INTENT with host == result: recovery must detect the mutation."""
    host = tmp_path / "target.txt"
    host.write_text("result", encoding="utf-8")
    entry = base_entry(
        "target.txt", "modified", base_content="base", result_content="result", state=EntryState.APPLY_INTENT
    )
    write_backup(tmp_path, "target.txt", "base")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report.status == "RECOVERED"
    assert host.read_text(encoding="utf-8") == "base"


def test_crash_after_mutation_before_journal_update_noop(tmp_path: Path) -> None:
    """APPLY_INTENT with host == base: recovery must NOT restore anything."""
    host = tmp_path / "target.txt"
    host.write_text("base", encoding="utf-8")
    entry = base_entry(
        "target.txt", "modified", base_content="base", result_content="result", state=EntryState.APPLY_INTENT
    )
    write_backup(tmp_path, "target.txt", "base")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report.status == "RECOVERED"
    assert report.restored == []
    assert host.read_text(encoding="utf-8") == "base"


def test_ambiguous_state_fails_closed(tmp_path: Path) -> None:
    """Host matches neither base nor result: recovery must refuse to overwrite."""
    host = tmp_path / "target.txt"
    host.write_text("UNRELATED HOST EDIT", encoding="utf-8")
    entry = base_entry(
        "target.txt", "modified", base_content="base", result_content="result", state=EntryState.APPLY_INTENT
    )
    write_backup(tmp_path, "target.txt", "base")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    with pytest.raises(PromotionRecoveryError, match="ambiguous"):
        PromotionRecovery(tmp_path).check_and_recover()
    assert host.read_text(encoding="utf-8") == "UNRELATED HOST EDIT"


def test_modified_file_recovery_preserves_mode(tmp_path: Path) -> None:
    host = tmp_path / "script.sh"
    host.write_text("result", encoding="utf-8")
    host.chmod(0o755)
    entry = base_entry(
        "script.sh",
        "modified",
        base_content="base",
        result_content="result",
        base_mode=0o755,
        result_mode=0o644,
        state=EntryState.APPLIED,
    )
    backup = write_backup(tmp_path, "script.sh", "base")
    backup.chmod(0o755)
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report.status == "RECOVERED"
    assert host.read_text(encoding="utf-8") == "base"
    if os.name != "nt":
        assert stat.S_IMODE(host.stat().st_mode) == 0o755


def test_deleted_file_recovery_restores_backup(tmp_path: Path) -> None:
    entry = base_entry(
        "gone.txt", "deleted", base_content="base", result_content=None, state=EntryState.APPLIED
    )
    write_backup(tmp_path, "gone.txt", "base")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report.status == "RECOVERED"
    assert (tmp_path / "gone.txt").read_text(encoding="utf-8") == "base"


def test_created_file_recovery_removes_result(tmp_path: Path) -> None:
    created = tmp_path / "created.txt"
    created.write_text("result", encoding="utf-8")
    entry = base_entry("created.txt", "created", result_content="result", state=EntryState.APPLIED)
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report.status == "RECOVERED"
    assert not created.exists()


def test_created_file_recovery_cleans_promote_temps(tmp_path: Path) -> None:
    created = tmp_path / "created.txt"
    created.write_text("result", encoding="utf-8")
    leftover = tmp_path / ".agentdiff-promote-abc123.tmp"
    leftover.write_text("result", encoding="utf-8")
    entry = base_entry("created.txt", "created", result_content="result", state=EntryState.APPLY_INTENT)
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report.status == "RECOVERED"
    assert not created.exists()
    assert not leftover.exists()


def test_recover_intent_retry_after_crash_between_replace_and_chmod(tmp_path: Path) -> None:
    """A crash between os.replace and chmod leaves content==base with a temp
    mode; retry must converge instead of declaring ambiguity."""
    host = tmp_path / "target.txt"
    host.write_text("base", encoding="utf-8")
    if os.name != "nt":
        host.chmod(0o600)  # temp-file mode from mkstemp, chmod never ran
    entry = base_entry(
        "target.txt",
        "modified",
        base_content="base",
        result_content="result",
        base_mode=0o755,
        result_mode=0o644,
        state=EntryState.RECOVER_INTENT,
    )
    write_backup(tmp_path, "target.txt", "base")
    make_journal(tmp_path, state=JournalState.APPLYING, entries=[entry])

    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report.status == "RECOVERED"
    assert host.read_text(encoding="utf-8") == "base"
    if os.name != "nt":
        assert stat.S_IMODE(host.stat().st_mode) == 0o755


def test_stale_committed_journal_is_cleaned(tmp_path: Path) -> None:
    entry = base_entry(
        "target.txt", "modified", base_content="base", result_content="result"
    )
    journal = make_journal(tmp_path, state=JournalState.COMMITTED, entries=[entry])
    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report is not None
    assert report.status == "NOTHING_TO_DO"
    assert not journal.path.exists()


def test_committed_journal_with_unconfirmed_entry_fails_closed(tmp_path: Path) -> None:
    entry = base_entry(
        "target.txt", "modified", base_content="base", result_content="result", state=EntryState.APPLY_INTENT
    )
    make_journal(tmp_path, state=JournalState.COMMITTED, entries=[entry])
    with pytest.raises(PromotionRecoveryError, match="inconsistent"):
        PromotionRecovery(tmp_path).check_and_recover()


def test_unrecoverable_journal_state_fails_closed(tmp_path: Path) -> None:
    entry = base_entry("target.txt", "modified", base_content="base", result_content="result")
    make_journal(tmp_path, state=JournalState.RECOVERY_FAILED, entries=[entry])
    with pytest.raises(PromotionRecoveryError, match="unrecoverable"):
        PromotionRecovery(tmp_path).check_and_recover()


def test_unapplied_staged_journal_is_cleaned(tmp_path: Path) -> None:
    entry = base_entry(
        "target.txt",
        "modified",
        base_content="base",
        result_content="result",
        state=EntryState.PREPARED,
    )
    journal = make_journal(tmp_path, state=JournalState.STAGED, entries=[entry])
    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report is not None
    assert report.status == "CLEANED_UNAPPLIED"
    assert not journal.path.exists()


def test_staged_journal_with_progressed_entry_fails_closed(tmp_path: Path) -> None:
    entry = base_entry(
        "target.txt", "modified", base_content="base", result_content="result", state=EntryState.APPLIED
    )
    make_journal(tmp_path, state=JournalState.STAGED, entries=[entry])
    with pytest.raises(PromotionRecoveryError, match="inconsistent"):
        PromotionRecovery(tmp_path).check_and_recover()


def test_legacy_schema2_journal_is_recoverable(tmp_path: Path) -> None:
    """Schema-2 journals (applied: bool) remain recoverable under old semantics."""
    host = tmp_path / "target.txt"
    host.write_text("result", encoding="utf-8")
    write_backup(tmp_path, "target.txt", "base")
    payload = {
        "schema_version": 2,
        "run_id": "run-crash",
        "patch_digest": "d",
        "state": "APPLYING",
        "created_at": "",
        "updated_at": "",
        "entries": [
            {
                "path": "target.txt",
                "change_type": "modified",
                "base_sha256": sha256("base"),
                "result_sha256": sha256("result"),
                "base_mode": 0o644,
                "result_mode": 0o644,
                "applied": True,
                "backup_relpath": ".agentdiff/backups/run-crash/target.txt",
            }
        ],
    }
    (tmp_path / ".agentdiff").mkdir(exist_ok=True)
    (tmp_path / ".agentdiff" / "promotion-journal.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    report = PromotionRecovery(tmp_path).check_and_recover()
    assert report.status == "RECOVERED"
    assert host.read_text(encoding="utf-8") == "base"


# ---------------------------------------------------------------------------
# Workspace lease: inode race and cross-process exclusion
# ---------------------------------------------------------------------------


def test_lock_file_is_never_unlinked(tmp_path: Path) -> None:
    lease = WorkspaceLease(tmp_path, run_id="run-1")
    with lease.hold():
        assert lease.lock_file.is_file()
    assert lease.lock_file.is_file(), "lock file must persist after release"
    # A second lease on the same persistent file must still work.
    with lease.hold():
        pass


def test_lease_excludes_second_holder(tmp_path: Path) -> None:
    with WorkspaceLease(tmp_path, run_id="run-1").hold():
        with pytest.raises(PromotionLockError, match="another process is promoting"):
            with WorkspaceLease(tmp_path, run_id="run-2").hold():
                pass


def test_lease_cross_process_exclusion(tmp_path: Path) -> None:
    """Two OS processes must not both hold the promotion lease."""
    script = (
        "import sys, time\n"
        "from agentdiff.promotion import WorkspaceLease, PromotionLockError\n"
        "root, marker = sys.argv[1], sys.argv[2]\n"
        "try:\n"
        "    with WorkspaceLease(root, 'run-x').hold(timeout_seconds=2.0):\n"
        "        open(marker, 'w').write('acquired')\n"
        "        time.sleep(3.0)\n"
        "except PromotionLockError:\n"
        "    open(marker, 'w').write('denied')\n"
    )
    marker = tmp_path / "marker"
    first = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path), str(marker)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = 10.0
        while not marker.exists() and deadline > 0:
            import time

            time.sleep(0.1)
            deadline -= 0.1
        assert marker.exists()
        # While the first process holds the lock, a second process must be denied.
        second = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path), str(tmp_path / "marker2")],
            capture_output=True,
            timeout=10,
            text=True,
        )
        assert second.returncode == 0
        assert (tmp_path / "marker2").read_text(encoding="utf-8") == "denied"
    finally:
        first.terminate()
        first.wait(timeout=5)

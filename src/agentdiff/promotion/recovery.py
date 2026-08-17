"""Crash-recovery engine for interrupted promotion transactions.

The promotion journal is untrusted persisted input. Every path it names is
validated before use: normalized relative paths that stay below the project
root (and below the approved backup directory for backups), with no symlink
parents and no special files. Backups are re-verified against the expected
SHA-256 / size / mode before any host file is overwritten, and restore copies
are written and fsynced from a validated descriptor so a concurrent swap of
the backup cannot be promoted into the host tree.

Recovery follows the write-ahead entry state machine:

- ``PREPARED``        → nothing was applied.
- ``APPLY_INTENT``    → the mutation may have happened; disambiguate by
                        comparing current host state to the expected base
                        and result, then restore (or confirm no-op).
- ``APPLIED``         → the mutation happened; restore.
- ``RECOVER_INTENT``  → a previous recovery was interrupted; re-run or
                        confirm the restore.
- ``RECOVERED``       → done.
- ``AMBIGUOUS``       → terminal fail-closed state; nothing is overwritten.

If the journal cannot be parsed or host state cannot be disambiguated, a
``PromotionRecoveryError`` is raised and promotion is blocked.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentdiff.pathing import normalize_relative_path
from agentdiff.state import FilesystemScanner

from .journal import (
    EntryState,
    JournalEntry,
    JournalLoadOutcome,
    JournalState,
    PromotionJournal,
)

_CHUNK_SIZE = 1024 * 1024
_PROMOTE_TEMP_PREFIX = ".agentdiff-promote-"


class PromotionRecoveryError(RuntimeError):
    """Raised when recovery cannot establish or restore a safe state."""


@dataclass
class RecoveryReport:
    """Result of one deterministic recovery pass."""

    run_id: str
    status: str
    restored: list[str] = field(default_factory=list)
    cleaned: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "restored": list(self.restored),
            "cleaned": list(self.cleaned),
            "errors": list(self.errors),
            "ambiguous": list(self.ambiguous),
        }


class PromotionRecovery:
    """Detect and rollback partially applied promotions using the write-ahead journal."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.scanner = FilesystemScanner(self.root)

    def check_and_recover(self) -> RecoveryReport | None:
        """Check for an interrupted journal and restore host state if needed.

        Raises :class:`PromotionRecoveryError` when the journal is corrupt,
        host state is ambiguous, or a restore cannot be completed safely.
        Returns ``None`` when no journal exists, and a report otherwise.
        """
        loaded = PromotionJournal.load(self.root)
        if loaded.outcome is JournalLoadOutcome.NO_JOURNAL:
            return None
        if loaded.outcome is JournalLoadOutcome.CORRUPT_JOURNAL:
            raise PromotionRecoveryError(
                f"promotion journal exists but recovery state cannot be established: {loaded.error}"
            )
        journal = loaded.journal
        assert journal is not None

        if journal.state in {JournalState.COMMITTED, JournalState.ROLLED_BACK}:
            self._validate_terminal_consistency(journal)
            journal.clean()
            return RecoveryReport(
                run_id=journal.run_id,
                status="NOTHING_TO_DO",
            )

        if journal.state in {JournalState.PLAN_RECORDED, JournalState.STAGED}:
            if any(entry.state is not EntryState.PREPARED for entry in journal.entries):
                raise PromotionRecoveryError(
                    "promotion journal is internally inconsistent: "
                    "unapplied transaction contains progressed entries"
                )
            journal.clean()
            return RecoveryReport(
                run_id=journal.run_id,
                status="CLEANED_UNAPPLIED",
            )

        if journal.state not in {JournalState.APPLYING, JournalState.RECOVERY_REQUIRED}:
            raise PromotionRecoveryError(
                f"promotion journal is in an unrecoverable state: {journal.state.value}"
            )

        report = RecoveryReport(run_id=journal.run_id, status="IN_PROGRESS")
        try:
            self._recover_entries(journal, report)
        except PromotionRecoveryError:
            journal.state = JournalState.RECOVERY_FAILED
            journal.persist()
            raise
        if report.ambiguous:
            journal.state = JournalState.RECOVERY_FAILED
            journal.persist()
            raise PromotionRecoveryError(
                "promotion recovery is ambiguous for: "
                + ", ".join(report.ambiguous)
                + "; refusing to overwrite host state"
            )
        if report.errors:
            journal.state = JournalState.RECOVERY_FAILED
            journal.persist()
            raise PromotionRecoveryError(
                "promotion recovery failed for: " + ", ".join(report.errors)
            )
        journal.state = JournalState.ROLLED_BACK
        journal.persist()
        report.status = "RECOVERED"
        return report

    # ------------------------------------------------------------------
    # Entry state machine
    # ------------------------------------------------------------------

    def _recover_entries(self, journal: PromotionJournal, report: RecoveryReport) -> None:
        for entry in journal.entries:
            self._validate_entry_paths(journal, entry)
            if entry.state is EntryState.PREPARED or entry.state is EntryState.RECOVERED:
                continue
            if entry.state is EntryState.AMBIGUOUS:
                report.ambiguous.append(entry.path)
                continue
            current = self._capture_host(entry.path)
            if entry.change_type == "created":
                self._recover_created(entry, current, report)
            elif entry.change_type in {"modified", "deleted"}:
                self._recover_present_or_deleted(entry, current, report)
            else:  # pragma: no cover - guarded by journal validation
                raise PromotionRecoveryError(
                    f"unsupported journal change type: {entry.change_type}"
                )

    def _recover_created(self, entry: JournalEntry, current: Any, report: RecoveryReport) -> None:
        """A created file is rolled back by unlinking the promoted result.

        Content match is sufficient to decide removal: a crash between the
        ``os.link`` and the follow-up ``chmod`` can leave result content with
        a temporary mode, and the file must be removed either way.
        """
        expected_result = self._content_matches(current, entry.result_sha256)
        if entry.state is EntryState.APPLY_INTENT:
            if current is None:
                # Host is absent -> the mutation never happened.
                entry.state = EntryState.PREPARED
                return
            if expected_result:
                entry.state = EntryState.RECOVER_INTENT
            else:
                report.ambiguous.append(entry.path)
                entry.state = EntryState.AMBIGUOUS
                return
        if entry.state in {EntryState.APPLIED, EntryState.RECOVER_INTENT}:
            if current is None:
                entry.state = EntryState.RECOVERED
                return
            if not expected_result:
                report.ambiguous.append(entry.path)
                entry.state = EntryState.AMBIGUOUS
                return
            self._remove_created_file(entry)
            self._cleanup_promote_temps(entry)
            entry.state = EntryState.RECOVERED
            report.cleaned.append(entry.path)

    def _recover_present_or_deleted(
        self, entry: JournalEntry, current: Any, report: RecoveryReport
    ) -> None:
        """A modified or deleted file is rolled back by restoring the base copy.

        Content-only base matches are treated as a partially completed
        restore (``os.replace`` done, ``chmod`` pending): the restore is
        repeated, which is idempotent, instead of declaring ambiguity.
        """
        expected_base_content = self._content_matches(current, entry.base_sha256)
        expected_base = self._file_matches(current, entry.base_sha256, entry.base_mode)
        expected_result = self._content_matches(current, entry.result_sha256)
        host_absent = current is None
        result_absent = host_absent if entry.change_type == "deleted" else False

        if entry.state is EntryState.APPLY_INTENT:
            if expected_base:
                entry.state = EntryState.PREPARED
                return
            if result_absent or expected_result or expected_base_content:
                # Mutation occurred (or a restore is partially complete):
                # restore the verified base copy.
                entry.state = EntryState.RECOVER_INTENT
            else:
                report.ambiguous.append(entry.path)
                entry.state = EntryState.AMBIGUOUS
                return
        if entry.state in {EntryState.APPLIED, EntryState.RECOVER_INTENT}:
            if expected_base:
                # Restore already complete; re-apply the mode in case a crash
                # interrupted the chmod between replace and verification.
                if not self._file_matches(current, entry.base_sha256, entry.base_mode):
                    self._apply_base_mode(entry)
                    rechecked = self._capture_host(entry.path)
                    if not self._file_matches(rechecked, entry.base_sha256, entry.base_mode):
                        raise PromotionRecoveryError(
                            f"restored mode does not match expected base state: {entry.path}"
                        )
                entry.state = EntryState.RECOVERED
                return
            if entry.change_type == "deleted" and not host_absent and not expected_result:
                report.ambiguous.append(entry.path)
                entry.state = EntryState.AMBIGUOUS
                return
            if entry.change_type == "modified" and host_absent:
                report.ambiguous.append(entry.path)
                entry.state = EntryState.AMBIGUOUS
                return
            self._restore_from_backup(entry)
            entry.state = EntryState.RECOVERED
            report.restored.append(entry.path)

    # ------------------------------------------------------------------
    # Host capture and identity helpers
    # ------------------------------------------------------------------

    def _capture_host(self, relative: str) -> Any:
        try:
            return self.scanner.capture_one(relative)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _file_matches(record: Any, sha256: str | None, mode: int | None) -> bool:
        if record is None or record.kind != "file" or record.link_count != 1:
            return False
        if record.sha256 is None or sha256 is None:
            return False
        return record.sha256 == sha256 and (mode is None or record.mode == mode)

    @staticmethod
    def _content_matches(record: Any, sha256: str | None) -> bool:
        if record is None or record.kind != "file" or record.link_count != 1:
            return False
        return record.sha256 is not None and record.sha256 == sha256

    def _apply_base_mode(self, entry: JournalEntry) -> None:
        """Restore only the base mode on an already-restored host file."""
        if os.name == "nt" or entry.base_mode is None:
            return
        host_path = self._validate_target_path(self.root, entry.path)
        try:
            host_path.chmod(stat.S_IMODE(entry.base_mode))
        except OSError as error:
            raise PromotionRecoveryError(
                f"failed to restore mode for {entry.path}: {error}"
            ) from error

    # ------------------------------------------------------------------
    # Path validation (journal content is untrusted)
    # ------------------------------------------------------------------

    def _validate_entry_paths(self, journal: PromotionJournal, entry: JournalEntry) -> None:
        """Reject unsafe journal paths before touching the host filesystem."""
        try:
            normalized = normalize_relative_path(entry.path)
        except ValueError as error:
            raise PromotionRecoveryError(
                f"unsafe promotion journal path: {entry.path!r}"
            ) from error
        if normalized != entry.path:
            raise PromotionRecoveryError(f"unsafe promotion journal path: {entry.path!r}")
        if entry.path == ".agentdiff" or entry.path.startswith(".agentdiff/"):
            raise PromotionRecoveryError(
                f"promotion journal path targets AgentDiff internal state: {entry.path!r}"
            )
        # Validate the host target and every parent now, so a symlink parent
        # is rejected deterministically instead of surfacing as ambiguity.
        self._validate_target_path(self.root, entry.path)
        if entry.change_type in {"modified", "deleted"}:
            if entry.backup_relpath is None:
                raise PromotionRecoveryError(
                    f"promotion journal entry {entry.path!r} has no backup path"
                )
            self._validate_backup_path(journal, entry)

    def _validate_backup_path(self, journal: PromotionJournal, entry: JournalEntry) -> None:
        backup = entry.backup_relpath
        assert backup is not None
        try:
            normalized = normalize_relative_path(backup)
        except ValueError as error:
            raise PromotionRecoveryError(f"unsafe backup path in journal: {backup!r}") from error
        if normalized != backup:
            raise PromotionRecoveryError(f"unsafe backup path in journal: {backup!r}")
        approved_prefix = f".agentdiff/backups/{journal.run_id}/"
        if not backup.startswith(approved_prefix):
            raise PromotionRecoveryError(
                f"backup path escapes the approved backup directory: {backup!r}"
            )
        backup_root = self.root / ".agentdiff" / "backups" / journal.run_id
        self._validate_target_path(self.root, backup, approved_root=backup_root)

    def _validate_target_path(
        self,
        root: Path,
        relative: str,
        *,
        approved_root: Path | None = None,
    ) -> Path:
        try:
            normalized = normalize_relative_path(relative)
        except ValueError as error:
            raise PromotionRecoveryError(f"unsafe path in journal: {relative!r}") from error
        if normalized != relative:
            raise PromotionRecoveryError(f"unsafe path in journal: {relative!r}")
        target = root.joinpath(*normalized.split("/"))
        if approved_root is not None:
            try:
                target.relative_to(approved_root)
            except ValueError as error:
                raise PromotionRecoveryError(
                    f"path escapes the approved directory: {relative!r}"
                ) from error
        current = root
        for part in normalized.split("/")[:-1]:
            current /= part
            try:
                info = current.lstat()
            except FileNotFoundError as error:
                raise PromotionRecoveryError(
                    f"journal parent directory is missing: {current}"
                ) from error
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise PromotionRecoveryError(f"journal parent is not a real directory: {current}")
        return target

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def _remove_created_file(self, entry: JournalEntry) -> None:
        target = self._validate_target_path(self.root, entry.path)
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise PromotionRecoveryError(f"created target is not a regular file: {entry.path}")
        if info.st_nlink != 1:
            raise PromotionRecoveryError(f"created target has unexpected link count: {entry.path}")
        try:
            target.unlink()
        except OSError as error:
            raise PromotionRecoveryError(
                f"failed to remove created file {entry.path}: {error}"
            ) from error

    def _cleanup_promote_temps(self, entry: JournalEntry) -> None:
        """Remove leftover promotion temp files next to a recovered created file.

        ``_atomic_create`` links a fully-written temp file into place and then
        unlinks the temp. A crash between the two leaves the temp behind with
        the same inode; it is only removed here, after the created target has
        been removed, and only for files matching our exact temp prefix.
        """
        target = self._validate_target_path(self.root, entry.path)
        self._cleanup_restore_temps(target.parent)

    @staticmethod
    def _cleanup_restore_temps(directory: Path) -> None:
        """Remove stale ``.agentdiff-promote-*`` temp files inside one directory."""
        try:
            for candidate in directory.iterdir():
                if not candidate.name.startswith(_PROMOTE_TEMP_PREFIX):
                    continue
                info = candidate.lstat()
                if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                    candidate.unlink(missing_ok=True)
        except OSError:
            raise PromotionRecoveryError(
                f"failed to clean promotion temp files in {directory}"
            ) from None

    def _restore_from_backup(self, entry: JournalEntry) -> None:
        """Restore base content and mode from a re-verified backup copy.

        The backup is copied through a validated descriptor while its digest
        and size are recomputed; the verified bytes are written to an fsynced
        temp file that is then atomically replaced onto the host path, so a
        concurrent swap of the backup can never be moved into the tree.
        """
        backup = entry.backup_relpath
        assert backup is not None
        backup_path = self._validate_target_path(self.root, backup)
        host_path = self._validate_target_path(self.root, entry.path)

        backup_info = backup_path.lstat()
        if not stat.S_ISREG(backup_info.st_mode) or stat.S_ISLNK(backup_info.st_mode):
            raise PromotionRecoveryError(f"backup is not a regular file: {entry.path}")
        if backup_info.st_nlink != 1:
            raise PromotionRecoveryError(f"backup has unexpected link count: {entry.path}")

        host_parent = host_path.parent
        if not host_parent.is_dir() or host_parent.is_symlink():
            raise PromotionRecoveryError(f"host parent is not a real directory: {entry.path}")
        self._cleanup_restore_temps(host_parent)

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            source_fd = os.open(backup_path, flags)
        except OSError as error:
            raise PromotionRecoveryError(f"backup is unreadable: {entry.path}") from error
        temp_path: Path | None = None
        try:
            opened = os.fstat(source_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_dev != backup_info.st_dev
                or opened.st_ino != backup_info.st_ino
            ):
                raise PromotionRecoveryError(f"backup identity changed while opening: {entry.path}")
            temp_descriptor, temp_name = tempfile.mkstemp(
                prefix=_PROMOTE_TEMP_PREFIX,
                suffix=".restore",
                dir=str(host_parent),
            )
            temp_path = Path(temp_name)
            digest = hashlib.sha256()
            size = 0
            with (
                os.fdopen(source_fd, "rb", closefd=False) as source,
                os.fdopen(temp_descriptor, "wb") as destination,
            ):
                while chunk := source.read(_CHUNK_SIZE):
                    digest.update(chunk)
                    size += len(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            finished = os.fstat(source_fd)
            if (
                finished.st_dev != opened.st_dev
                or finished.st_ino != opened.st_ino
                or finished.st_size != opened.st_size
                or finished.st_mtime_ns != opened.st_mtime_ns
            ):
                raise PromotionRecoveryError(f"backup changed while restoring: {entry.path}")
            if entry.base_sha256 is not None and digest.hexdigest() != entry.base_sha256:
                raise PromotionRecoveryError(
                    f"backup digest mismatch for {entry.path}; refusing to overwrite host state"
                )
            if entry.base_size is not None and size != entry.base_size:
                raise PromotionRecoveryError(
                    f"backup size mismatch for {entry.path}; refusing to overwrite host state"
                )
            os.replace(temp_path, host_path)
            temp_path = None
            if os.name != "nt" and entry.base_mode is not None:
                host_path.chmod(stat.S_IMODE(entry.base_mode))
        except OSError as error:
            raise PromotionRecoveryError(f"failed to restore {entry.path}: {error}") from error
        finally:
            os.close(source_fd)
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        restored = self._capture_host(entry.path)
        if not self._file_matches(restored, entry.base_sha256, entry.base_mode):
            raise PromotionRecoveryError(
                f"restored file does not match expected base state: {entry.path}"
            )

    def _validate_terminal_consistency(self, journal: PromotionJournal) -> None:
        """A COMMITTED/ROLLED_BACK journal must be internally consistent."""
        if journal.state is JournalState.COMMITTED:
            progressed = [
                entry.path
                for entry in journal.entries
                if entry.state not in {EntryState.APPLIED, EntryState.RECOVERED}
            ]
        else:  # ROLLED_BACK
            progressed = [
                entry.path for entry in journal.entries if entry.state is not EntryState.RECOVERED
            ]
        if progressed:
            raise PromotionRecoveryError(
                "promotion journal is internally inconsistent: "
                f"{journal.state.value} contains unconfirmed entries: " + ", ".join(progressed)
            )

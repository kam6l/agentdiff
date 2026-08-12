"""Conflict-safe filesystem recovery for AgentDiff transactions.

Recovery is deliberately conservative.  AgentDiff restores or removes a path
only when its current state still equals the recorded after-state.  It refuses
symlinks, hardlinks, missing hashes, path escapes, and missing backups.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath

from agentdiff.pathing import normalize_relative_path
from agentdiff.state.filesystem import (
    FileRecord,
    FilesystemManifest,
    FilesystemScanner,
    same_file_state,
)

from .models import RollbackAction, RollbackConflict, RollbackReport
from .store import RunStore

_CHUNK_SIZE = 1024 * 1024


def _safe_relative(value: str) -> PurePosixPath:
    try:
        normalized = normalize_relative_path(value)
    except ValueError as error:
        raise ValueError("unsafe path") from error
    if normalized != value:
        raise ValueError("unsafe path")
    return PurePosixPath(normalized)


class RollbackEngine:
    """Apply verified filesystem recovery for one stored run."""

    def __init__(self, root: str | Path, run_id: str) -> None:
        self.store = RunStore.open(root, run_id)
        self.root = self.store.root
        self.scanner = FilesystemScanner(self.root)

    @classmethod
    def open(cls, root: str | Path, run_id: str) -> "RollbackEngine":
        """Open a stored run for explicit recovery."""

        return cls(root, run_id)

    def rollback(
        self,
        *,
        safe_only: bool = False,
        all_changes: bool = False,
        paths: list[str] | None = None,
    ) -> RollbackReport:
        if safe_only == all_changes:
            raise ValueError("select exactly one of safe_only or all_changes")
        report = RollbackReport(run_id=self.store.run_id)
        integrity = self.store.verify_integrity()
        if not integrity.present:
            report.conflicts.append(
                RollbackConflict("<capsule>", "sealed capsule integrity is required")
            )
            return report
        if not integrity.ok:
            report.conflicts.append(
                RollbackConflict("<capsule>", "capsule integrity verification failed")
            )
            self.store.write_json("rollback-result.json", report.to_dict())
            self.store.append_event(
                "rollback_refused",
                {"integrity": integrity.to_dict()},
            )
            return report
        policy_path = self.store.run_dir / "policy.json"
        if policy_path.exists() or policy_path.is_symlink():
            policy = self.store.read_json("policy.json")
            if not isinstance(policy, dict):
                raise ValueError("run policy must be a mapping")
            rollback = policy.get("rollback", {})
            if not isinstance(rollback, dict):
                raise ValueError("run rollback policy must be a mapping")
            enabled = rollback.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError("run rollback policy enabled value must be a boolean")
            if not enabled:
                raise PermissionError("rollback is disabled by policy for this run")
        before = FilesystemManifest.from_dict(self.store.read_json("before.json"))
        after = FilesystemManifest.from_dict(self.store.read_json("after.json"))
        result = self.store.read_json("result.json")
        raw_changes = result.get("changes", []) if isinstance(result, dict) else []
        if not isinstance(raw_changes, list):
            raise ValueError("run result changes must be a list")
        selected_paths = set(paths or [])

        for raw in raw_changes:
            if not isinstance(raw, dict):
                report.conflicts.append(RollbackConflict("<invalid>", "invalid change record"))
                continue
            path = str(raw.get("path", ""))
            decision = str(raw.get("decision", "review"))
            if selected_paths and path not in selected_paths:
                report.skipped.append(path)
                continue
            if safe_only and decision not in {"deny", "review"}:
                report.skipped.append(path)
                continue
            try:
                relative, target = self._resolve_target(path)
                change_type = str(raw.get("change_type", ""))
                old = before.files.get(path)
                new = after.files.get(path)
                action = self._rollback_one(relative, target, change_type, old, new)
            except (OSError, RuntimeError, ValueError) as exc:
                reason = str(exc) or type(exc).__name__
                report.conflicts.append(RollbackConflict(path or "<invalid>", reason))
            else:
                report.actions.append(action)

        self.store.write_json("rollback-result.json", report.to_dict())
        self.store.append_event(
            "rollback_completed",
            {
                "actions": len(report.actions),
                "conflicts": len(report.conflicts),
                "safe_only": safe_only,
            },
        )
        return report

    def _resolve_target(self, value: str) -> tuple[PurePosixPath, Path]:
        try:
            relative = _safe_relative(value)
        except ValueError as exc:
            raise ValueError("unsafe path") from exc
        target = self.root.joinpath(*relative.parts)
        current = self.root
        for part in relative.parts[:-1]:
            current /= part
            try:
                mode = current.lstat().st_mode
            except FileNotFoundError:
                break
            if stat.S_ISLNK(mode):
                raise ValueError("unsafe path")
            if not stat.S_ISDIR(mode):
                raise ValueError("unsafe path")
        return relative, target

    def _rollback_one(
        self,
        relative: PurePosixPath,
        target: Path,
        change_type: str,
        before: FileRecord | None,
        after: FileRecord | None,
    ) -> RollbackAction:
        path = relative.as_posix()
        if change_type == "created":
            if before is not None or after is None:
                raise ValueError("invalid created-file evidence")
            self._remove_created(path, target, after)
            return RollbackAction(path, "removed", "created by monitored run")
        if change_type == "deleted":
            if before is None or after is not None:
                raise ValueError("invalid deleted-file evidence")
            self._restore_deleted(path, target, before)
            return RollbackAction(path, "restored", "deleted by monitored run")
        if change_type == "modified":
            if before is None or after is None:
                raise ValueError("invalid modified-file evidence")
            self._restore_modified(path, target, before, after)
            return RollbackAction(path, "restored", "modified by monitored run")
        raise ValueError("unsupported change type")

    def _remove_created(self, path: str, target: Path, after: FileRecord) -> None:
        if after.kind != "file" or after.sha256 is None or after.link_count > 1:
            raise RuntimeError("created entry is not safely removable")
        current = self.scanner.capture_one(path)
        if current is None:
            raise RuntimeError("current state differs from recorded after-state")
        if not same_file_state(current, after):
            raise RuntimeError("current state differs from recorded after-state")
        latest = target.lstat()
        if (
            not stat.S_ISREG(latest.st_mode)
            or latest.st_dev != current.device
            or latest.st_ino != current.inode
            or latest.st_nlink > 1
        ):
            raise RuntimeError("current state differs from recorded after-state")
        target.unlink()

    def _restore_modified(
        self,
        path: str,
        target: Path,
        before: FileRecord,
        after: FileRecord,
    ) -> None:
        self._validate_recoverable_record(before)
        self._validate_recoverable_record(after, require_backup=False)
        current = self.scanner.capture_one(path)
        if current is None or not same_file_state(current, after):
            raise RuntimeError("current state differs from recorded after-state")
        backup = self._verified_backup(before)
        self._atomic_overwrite(path, target, backup, before, after)

    def _restore_deleted(self, path: str, target: Path, before: FileRecord) -> None:
        self._validate_recoverable_record(before)
        if target.exists() or target.is_symlink():
            raise RuntimeError("current state differs from recorded after-state")
        if not target.parent.is_dir() or target.parent.is_symlink():
            raise RuntimeError("parent directory is missing or unsafe")
        backup = self._verified_backup(before)
        self._atomic_create(target, backup, before.mode)

    @staticmethod
    def _validate_recoverable_record(
        record: FileRecord,
        *,
        require_backup: bool = True,
    ) -> None:
        if record.kind != "file":
            raise RuntimeError("symlink rollback is unsupported")
        if record.link_count > 1:
            raise RuntimeError("hardlinked file rollback is unsupported")
        if record.sha256 is None:
            raise RuntimeError("file has no verifiable content hash")
        if require_backup and record.backup_path is None:
            raise RuntimeError(record.backup_error or "file has no recovery backup")

    def _verified_backup(self, record: FileRecord) -> Path:
        assert record.backup_path is not None
        relative = _safe_relative(record.backup_path)
        backup_root = self.store.backup_dir.resolve(strict=True)
        backup = self.store.backup_dir.joinpath(*relative.parts)
        current = self.store.backup_dir
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise RuntimeError("unsafe backup path")
        resolved = backup.resolve(strict=True)
        if resolved.parent != backup_root and backup_root not in resolved.parents:
            raise RuntimeError("unsafe backup path")
        if not resolved.is_file() or resolved.is_symlink():
            raise RuntimeError("recovery backup is not a regular file")
        digest = self._hash_path(resolved)
        if digest != record.sha256:
            raise RuntimeError("recovery backup failed integrity verification")
        return resolved

    def _atomic_overwrite(
        self,
        path: str,
        target: Path,
        backup: Path,
        before: FileRecord,
        expected_after: FileRecord,
    ) -> None:
        descriptor, name = tempfile.mkstemp(prefix=".agentdiff-rollback-", dir=target.parent)
        temporary = Path(name)
        try:
            self._copy_backup(backup, descriptor, before.mode)
            # Windows does not permit replacing an open file. Close the
            # flushed temporary before the final conflict check and swap.
            os.close(descriptor)
            descriptor = -1
            latest = self.scanner.capture_one(path)
            if latest is None or not same_file_state(latest, expected_after):
                raise RuntimeError("current state differs from recorded after-state")
            target_info = target.lstat()
            if (
                not stat.S_ISREG(target_info.st_mode)
                or target_info.st_dev != latest.device
                or target_info.st_ino != latest.inode
                or target_info.st_nlink > 1
            ):
                raise RuntimeError("current state differs from recorded after-state")
            os.replace(temporary, target)
            if os.name != "nt":
                target.chmod(before.mode)
        finally:
            if descriptor >= 0:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
            temporary.unlink(missing_ok=True)

    def _atomic_create(self, target: Path, backup: Path, mode: int) -> None:
        descriptor, name = tempfile.mkstemp(prefix=".agentdiff-rollback-", dir=target.parent)
        temporary = Path(name)
        try:
            self._copy_backup(backup, descriptor, mode)
            os.close(descriptor)
            descriptor = -1
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise RuntimeError("current state differs from recorded after-state") from exc
            if os.name != "nt":
                target.chmod(mode)
        finally:
            if descriptor >= 0:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _copy_backup(backup: Path, descriptor: int, mode: int) -> None:
        with backup.open("rb") as source, os.fdopen(descriptor, "wb", closefd=False) as output:
            while chunk := source.read(_CHUNK_SIZE):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if os.name != "nt":
            os.fchmod(descriptor, mode)

    @staticmethod
    def _hash_path(path: Path) -> str:
        digest = hashlib.sha256()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                while chunk := stream.read(_CHUNK_SIZE):
                    digest.update(chunk)
        finally:
            os.close(descriptor)
        return digest.hexdigest()

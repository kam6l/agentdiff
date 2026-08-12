"""Secure, local-first filesystem manifests.

The scanner uses ``lstat``/``O_NOFOLLOW`` where available and never follows
symlinks.  It intentionally ignores AgentDiff's own run store and common build
or dependency directories.  It is evidence collection, not a kernel sandbox.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import stat
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from agentdiff.pathing import (
    glob_could_match_descendant,
    glob_matches,
    normalize_relative_path,
)

SCHEMA_VERSION = 1
_CHUNK_SIZE = 1024 * 1024
_INTERNAL_IGNORED_NAMES = {".agentdiff"}
_HARD_IGNORED_NAMES = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
_DEFAULT_IGNORED_NAMES = {
    ".git",
    *_HARD_IGNORED_NAMES,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_relative(value: str) -> PurePosixPath:
    try:
        normalized = normalize_relative_path(value)
    except ValueError as error:
        raise ValueError("unsafe relative path") from error
    if normalized != value:
        raise ValueError("unsafe relative path")
    return PurePosixPath(normalized)


@dataclass(frozen=True)
class FileRecord:
    """One non-directory filesystem entry in a manifest."""

    path: str
    kind: str
    sha256: str | None
    size: int
    mode: int
    mtime_ns: int
    device: int | None
    inode: int | None
    link_count: int
    symlink_target: str | None = None
    backup_path: str | None = None
    backup_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileRecord":
        return cls(
            path=str(data["path"]),
            kind=str(data["kind"]),
            sha256=str(data["sha256"]) if data.get("sha256") is not None else None,
            size=int(data["size"]),
            mode=int(data["mode"]),
            mtime_ns=int(data["mtime_ns"]),
            device=int(data["device"]) if data.get("device") is not None else None,
            inode=int(data["inode"]) if data.get("inode") is not None else None,
            link_count=int(data.get("link_count", 1)),
            symlink_target=(
                str(data["symlink_target"]) if data.get("symlink_target") is not None else None
            ),
            backup_path=(str(data["backup_path"]) if data.get("backup_path") is not None else None),
            backup_error=(
                str(data["backup_error"]) if data.get("backup_error") is not None else None
            ),
        )


@dataclass(frozen=True)
class FilesystemManifest:
    """Versioned snapshot of filesystem entries below one project root."""

    root: str
    captured_at: str
    files: dict[str, FileRecord]
    unsupported: dict[str, str] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "root": self.root,
            "captured_at": self.captured_at,
            "files": {path: record.to_dict() for path, record in sorted(self.files.items())},
            "unsupported": dict(sorted(self.unsupported.items())),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FilesystemManifest":
        if int(data.get("schema_version", 0)) != SCHEMA_VERSION:
            raise ValueError("unsupported filesystem manifest schema")
        raw_files = data.get("files")
        if not isinstance(raw_files, dict):
            raise ValueError("manifest files must be an object")
        return cls(
            schema_version=SCHEMA_VERSION,
            root=str(data["root"]),
            captured_at=str(data["captured_at"]),
            files={
                str(path): FileRecord.from_dict(record)
                for path, record in raw_files.items()
                if isinstance(record, dict)
            },
            unsupported={
                str(path): str(reason) for path, reason in dict(data.get("unsupported", {})).items()
            },
        )


@dataclass(frozen=True)
class FileChange:
    """A created, modified, or deleted manifest entry."""

    path: str
    change_type: str
    content_changed: bool
    mode_changed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FilesystemScanner:
    """Capture a deterministic manifest without traversing symlinks."""

    def __init__(
        self,
        root: str | Path,
        *,
        backup_dir: str | Path | None = None,
        backup_max_file_mb: float = 25,
        hash_max_file_mb: float = 100,
        ignore_patterns: list[str] | None = None,
        protected_patterns: list[str] | None = None,
    ) -> None:
        candidate = Path(root).expanduser().resolve(strict=True)
        if not candidate.is_dir():
            raise ValueError("filesystem root must be a directory")
        self.root = candidate
        self.backup_dir = Path(backup_dir).resolve() if backup_dir is not None else None
        self.backup_limit = max(0, int(backup_max_file_mb * 1024 * 1024))
        self.hash_limit = max(0, int(hash_max_file_mb * 1024 * 1024))
        self.ignore_patterns = self._load_ignore_patterns(ignore_patterns or [])
        self.protected_patterns = tuple(protected_patterns or ())

    def _load_ignore_patterns(self, supplied: list[str]) -> list[str]:
        patterns = [pattern.strip() for pattern in supplied if pattern.strip()]
        ignore_file = self.root / ".agentdiffignore"
        try:
            if ignore_file.is_file() and not ignore_file.is_symlink():
                patterns.extend(
                    line.strip()
                    for line in ignore_file.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                )
        except OSError:
            pass
        return patterns

    def _is_ignored(self, relative: str, *, is_dir: bool) -> bool:
        parts = PurePosixPath(relative).parts
        # AgentDiff's live capsule must never observe itself. Other default
        # exclusions are overridable when policy explicitly protects them.
        if any(part in _INTERNAL_IGNORED_NAMES for part in parts):
            return True
        protected = any(
            glob_could_match_descendant(relative, pattern)
            if is_dir
            else glob_matches(relative, pattern)
            for pattern in self.protected_patterns
        )
        if protected:
            return False
        if any(part in _HARD_IGNORED_NAMES for part in parts):
            return True
        if any(part in _DEFAULT_IGNORED_NAMES for part in parts):
            return True
        candidate = f"{relative}/" if is_dir else relative
        ignored = False
        for raw_pattern in self.ignore_patterns:
            negate = raw_pattern.startswith("!")
            pattern = raw_pattern[1:] if negate else raw_pattern
            pattern = pattern.lstrip("/")
            if not pattern:
                continue
            if pattern.endswith("/"):
                base = pattern.rstrip("/")
                matched = relative == base or relative.startswith(f"{base}/")
            else:
                matched = fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(
                    candidate, pattern
                )
            if matched:
                ignored = not negate
        return ignored

    def capture(self, *, backup: bool = False) -> FilesystemManifest:
        if backup and self.backup_dir is None:
            raise ValueError("backup_dir is required when backup=True")
        files: dict[str, FileRecord] = {}
        unsupported: dict[str, str] = {}
        self._scan_directory(self.root, files, unsupported, backup=backup)
        return FilesystemManifest(
            root=str(self.root),
            captured_at=_utc_now(),
            files=files,
            unsupported=unsupported,
        )

    def capture_one(self, relative: str) -> FileRecord | None:
        safe = _safe_relative(relative)
        path = self.root.joinpath(*safe.parts)
        if self._has_symlink_parent(path):
            return None
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        return self._record(path, relative, info, backup=False)

    def _scan_directory(
        self,
        directory: Path,
        files: dict[str, FileRecord],
        unsupported: dict[str, str],
        *,
        backup: bool,
    ) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except (OSError, UnicodeError) as exc:
            relative = directory.relative_to(self.root).as_posix() or "."
            unsupported[relative] = f"directory unreadable: {type(exc).__name__}"
            return
        for entry in entries:
            path = Path(entry.path)
            try:
                relative = path.relative_to(self.root).as_posix()
                # ``DirEntry.stat`` can report zeroed file identities on Windows
                # (notably with Python 3.14), while a path-level ``lstat`` returns
                # the stable volume/file IDs also exposed by ``fstat`` below.
                # Use the same identity source on every platform so the secure
                # open-and-verify step does not reject unchanged regular files.
                info = path.lstat()
            except (OSError, ValueError, UnicodeError) as exc:
                unsupported[entry.name] = f"entry unreadable: {type(exc).__name__}"
                continue
            is_directory = stat.S_ISDIR(info.st_mode)
            if self._is_ignored(relative, is_dir=is_directory):
                continue
            if stat.S_ISLNK(info.st_mode):
                record = self._record(path, relative, info, backup=False)
                if record is not None:
                    files[relative] = record
            elif is_directory:
                self._scan_directory(path, files, unsupported, backup=backup)
            elif stat.S_ISREG(info.st_mode):
                record = self._record(path, relative, info, backup=backup)
                if record is not None:
                    files[relative] = record
                    if record.sha256 is None:
                        unsupported[relative] = (
                            record.backup_error
                            or "content hash unavailable; same-size mutations may be undetected"
                        )
            else:
                unsupported[relative] = "special filesystem entry"

    def _record(
        self,
        path: Path,
        relative: str,
        info: os.stat_result,
        *,
        backup: bool,
    ) -> FileRecord | None:
        if stat.S_ISLNK(info.st_mode):
            try:
                target = os.readlink(path)
            except OSError:
                return None
            digest = hashlib.sha256(
                f"symlink:{target}".encode("utf-8", "surrogateescape")
            ).hexdigest()
            return FileRecord(
                path=relative,
                kind="symlink",
                sha256=digest,
                size=int(info.st_size),
                mode=stat.S_IMODE(info.st_mode),
                mtime_ns=int(info.st_mtime_ns),
                device=int(info.st_dev),
                inode=int(info.st_ino),
                link_count=int(info.st_nlink),
                symlink_target=target,
                backup_error="symlink rollback is unsupported" if backup else None,
            )
        if not stat.S_ISREG(info.st_mode):
            return None

        backup_path: str | None = None
        backup_error: str | None = None
        should_backup = backup
        if info.st_size > self.hash_limit:
            return FileRecord(
                path=relative,
                kind="file",
                sha256=None,
                size=int(info.st_size),
                mode=stat.S_IMODE(info.st_mode),
                mtime_ns=int(info.st_mtime_ns),
                device=int(info.st_dev),
                inode=int(info.st_ino),
                link_count=int(info.st_nlink),
                backup_error="file exceeds hash limit" if backup else None,
            )
        if backup and info.st_nlink > 1:
            should_backup = False
            backup_error = "hardlinked file"
        elif backup and info.st_size > self.backup_limit:
            should_backup = False
            backup_error = "file exceeds backup limit"

        destination: Path | None = None
        if should_backup:
            if self.backup_dir is None:
                raise RuntimeError("backup capture requested without a backup directory")
            try:
                safe = _safe_relative(relative)
            except ValueError:
                backup_error = "nonportable path"
            else:
                destination = self.backup_dir.joinpath(*safe.parts)
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        try:
            digest = self._hash_regular_file(path, info, destination)
        except (OSError, RuntimeError):
            if destination is not None:
                destination.unlink(missing_ok=True)
            return FileRecord(
                path=relative,
                kind="file",
                sha256=None,
                size=int(info.st_size),
                mode=stat.S_IMODE(info.st_mode),
                mtime_ns=int(info.st_mtime_ns),
                device=int(info.st_dev),
                inode=int(info.st_ino),
                link_count=int(info.st_nlink),
                backup_error="file changed or became unreadable during capture" if backup else None,
            )
        if destination is not None:
            backup_path = relative
        return FileRecord(
            path=relative,
            kind="file",
            sha256=digest,
            size=int(info.st_size),
            mode=stat.S_IMODE(info.st_mode),
            mtime_ns=int(info.st_mtime_ns),
            device=int(info.st_dev),
            inode=int(info.st_ino),
            link_count=int(info.st_nlink),
            backup_path=backup_path,
            backup_error=backup_error,
        )

    @staticmethod
    def _hash_regular_file(
        path: Path,
        expected: os.stat_result,
        destination: Path | None,
    ) -> str:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(path, flags)
        destination_stream: BinaryIO | None = None
        try:
            opened = os.fstat(source_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != expected.st_dev
                or opened.st_ino != expected.st_ino
            ):
                raise RuntimeError("filesystem entry changed before capture")
            if destination is not None:
                destination_fd = os.open(
                    destination,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                destination_stream = os.fdopen(destination_fd, "wb")
            digest = hashlib.sha256()
            with os.fdopen(source_fd, "rb", closefd=False) as source:
                while chunk := source.read(_CHUNK_SIZE):
                    digest.update(chunk)
                    if destination_stream is not None:
                        destination_stream.write(chunk)
            if destination_stream is not None:
                destination_stream.flush()
                os.fsync(destination_stream.fileno())
            finished = os.fstat(source_fd)
            if finished.st_size != expected.st_size or finished.st_mtime_ns != expected.st_mtime_ns:
                raise RuntimeError("file changed during capture")
            return digest.hexdigest()
        finally:
            if destination_stream is not None:
                destination_stream.close()
            os.close(source_fd)

    def _has_symlink_parent(self, target: Path) -> bool:
        try:
            relative = target.relative_to(self.root)
        except ValueError:
            return True
        current = self.root
        for part in relative.parts[:-1]:
            current /= part
            try:
                if stat.S_ISLNK(current.lstat().st_mode):
                    return True
            except FileNotFoundError:
                return False
        return False


def same_file_state(left: FileRecord, right: FileRecord) -> bool:
    """Return true only when state is strong enough for safe recovery."""

    if left.kind != right.kind or left.mode != right.mode or left.size != right.size:
        return False
    if left.link_count > 1 or right.link_count > 1:
        return False
    if left.kind == "symlink":
        return left.symlink_target == right.symlink_target and left.sha256 == right.sha256
    if left.sha256 is None or right.sha256 is None:
        return False
    return left.sha256 == right.sha256


def diff_manifests(
    before: FilesystemManifest,
    after: FilesystemManifest,
) -> list[FileChange]:
    """Return deterministic changes between two manifests."""

    changes: list[FileChange] = []
    for path in sorted(set(before.files) | set(after.files)):
        old = before.files.get(path)
        new = after.files.get(path)
        if old is None and new is not None:
            changes.append(FileChange(path, "created", True, False))
            continue
        if old is not None and new is None:
            changes.append(FileChange(path, "deleted", True, False))
            continue
        if old is None or new is None:
            raise RuntimeError("manifest diff invariant violated")
        content_changed = (
            old.kind != new.kind
            or old.sha256 != new.sha256
            or old.size != new.size
            or old.symlink_target != new.symlink_target
        )
        if old.kind == new.kind == "file" and (old.sha256 is None or new.sha256 is None):
            content_changed = content_changed or (
                old.mtime_ns != new.mtime_ns or old.device != new.device or old.inode != new.inode
            )
        mode_changed = old.mode != new.mode
        metadata_changed = old.link_count != new.link_count
        if content_changed or mode_changed or metadata_changed:
            changes.append(
                FileChange(
                    path=path,
                    change_type="modified",
                    content_changed=content_changed,
                    mode_changed=mode_changed,
                )
            )
    return changes

"""Staging directory management and fsync validation for multi-file promotion."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING

from agentdiff.pathing import normalize_relative_path

if TYPE_CHECKING:
    from agentdiff.evidence import PatchBundle, PatchEntry

_CHUNK_SIZE = 1024 * 1024


class PromotionStager:
    """Stage replacement contents and pre-mutation backups safely before commit."""

    def __init__(self, root: str | Path, run_id: str) -> None:
        self.root = Path(root).resolve()
        self.run_id = run_id
        self.staging_dir = self.root / ".agentdiff" / "staging" / run_id
        self.backup_dir = self.root / ".agentdiff" / "backups" / run_id

    def prepare(self) -> None:
        self.clean()
        self.staging_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def stage_entry(self, bundle: PatchBundle, entry: PatchEntry) -> Path:
        """Extract and fsync patch entry into staging directory with sha256 check."""
        if entry.change_type == "deleted":
            raise ValueError("deleted entries have no staged content")

        source_path = bundle.entry_path(entry)
        if not source_path.is_file() or source_path.is_symlink():
            raise FileNotFoundError(f"missing patch artifact for {entry.path}")

        normalized = normalize_relative_path(entry.path)
        if normalized != entry.path:
            raise ValueError(f"unsafe staging path: {entry.path!r}")
        target_staged = self.staging_dir.joinpath(*normalized.split("/"))
        target_staged.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._assert_real_directory(target_staged.parent, self.staging_dir)

        source_info = source_path.lstat()
        if not stat.S_ISREG(source_info.st_mode) or source_info.st_nlink != 1:
            raise RuntimeError("staging source is not a single-link regular file")
        hasher = hashlib.sha256()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(source_path, flags)
        try:
            opened = os.fstat(source_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_dev != source_info.st_dev
                or opened.st_ino != source_info.st_ino
            ):
                raise RuntimeError("staging source changed while opening")
            with (
                os.fdopen(source_fd, "rb", closefd=False) as src,
                target_staged.open("wb") as dst,
            ):
                while chunk := src.read(_CHUNK_SIZE):
                    dst.write(chunk)
                    hasher.update(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            finished = os.fstat(source_fd)
            if (
                finished.st_dev != opened.st_dev
                or finished.st_ino != opened.st_ino
                or finished.st_size != opened.st_size
                or finished.st_mtime_ns != opened.st_mtime_ns
            ):
                raise RuntimeError("staging source changed while reading")
        finally:
            os.close(source_fd)

        digest = hasher.hexdigest()
        if entry.result_sha256 is not None and digest != entry.result_sha256:
            raise ValueError(
                f"staged digest mismatch for {entry.path}: expected {entry.result_sha256}, got {digest}"
            )
        if entry.size is not None and target_staged.stat().st_size != entry.size:
            raise ValueError(f"staged size mismatch for {entry.path}")

        mode = entry.result_mode if entry.result_mode is not None else 0o644
        target_staged.chmod(stat.S_IMODE(mode))
        _fsync_directory(target_staged.parent)

        return target_staged

    def backup_host_file(self, relpath: str) -> Path | None:
        """Backup an existing host regular file before mutation.

        The source is opened without following links and its opened identity
        (device, inode, file type) must match the pre-open ``lstat`` so a
        symlink substitution during the copy cannot be recorded as the base.
        """
        normalized = normalize_relative_path(relpath)
        if normalized != relpath:
            raise ValueError(f"unsafe backup path: {relpath!r}")
        host_path = self.root.joinpath(*normalized.split("/"))
        if self._has_symlink_parent(host_path):
            raise RuntimeError(f"unsafe backup parent for {relpath}")
        try:
            host_info = host_path.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(host_info.st_mode) or not stat.S_ISREG(host_info.st_mode):
            return None
        if host_info.st_nlink != 1:
            raise RuntimeError(f"host file has unexpected link count: {relpath}")

        backup_path = self.backup_dir.joinpath(*normalized.split("/"))
        backup_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._assert_real_directory(backup_path.parent, self.backup_dir)

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(host_path, flags)
        try:
            opened = os.fstat(source_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_dev != host_info.st_dev
                or opened.st_ino != host_info.st_ino
            ):
                raise RuntimeError("host file changed while opening backup")
            with (
                os.fdopen(source_fd, "rb", closefd=False) as src,
                backup_path.open("xb") as dst,
            ):
                while chunk := src.read(_CHUNK_SIZE):
                    dst.write(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            finished = os.fstat(source_fd)
            if (
                finished.st_dev != opened.st_dev
                or finished.st_ino != opened.st_ino
                or finished.st_size != opened.st_size
                or finished.st_mtime_ns != opened.st_mtime_ns
            ):
                raise RuntimeError("host file changed while backing up")
        finally:
            os.close(source_fd)
        if os.name != "nt":
            backup_path.chmod(stat.S_IMODE(host_info.st_mode))
        _fsync_directory(backup_path.parent)

        return backup_path

    @staticmethod
    def _has_symlink_parent(target: Path) -> bool:
        current = target.parent
        while True:
            try:
                info = current.lstat()
            except FileNotFoundError:
                return False
            if stat.S_ISLNK(info.st_mode):
                return True
            if current == current.parent:
                return False
            current = current.parent

    @staticmethod
    def _assert_real_directory(path: Path, approved_root: Path) -> None:
        try:
            path.relative_to(approved_root)
        except ValueError as error:
            raise RuntimeError("staging path escapes the approved directory") from error
        try:
            info = path.lstat()
        except FileNotFoundError as error:
            raise RuntimeError("staging directory disappeared") from error
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise RuntimeError("staging path is not a real directory")

    def clean(self) -> None:
        """Clean staging and backup temporary artifacts."""
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir, ignore_errors=True)
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir, ignore_errors=True)


def _fsync_directory(directory: Path) -> None:
    """Best-effort directory fsync so staged renames are durable."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)

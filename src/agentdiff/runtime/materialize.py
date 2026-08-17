"""Workspace materialization for clean-room and isolated runtimes.

Strategies are named accurately:

- ``CLONE`` / CoW: platform-native clone only where actually supported
  (Linux ``FICLONE``). This is a true reflink clone on supporting
  filesystems.
- ``FAST_COPY``: ``copy_file_range`` / platform accelerated copy. This is a
  fast copy primitive, **not** a guaranteed reflink or CoW guarantee.
- ``STREAM_COPY``: portable streaming fallback.

Every strategy preserves regular-file content, size, and POSIX mode
(including the executable bit), verifies the opened source identity, and
rejects symlinks and special files instead of silently dropping or following
them. This is a trust-boundary component: a source swap during materialization
must never leak into the private workspace.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

_CHUNK_SIZE = 1024 * 1024

# Linux FICLONE ioctl (linux/fs.h) — true reflink where the filesystem
# supports it. Request code 0x40049409 (direction IOW, size 4, type 0x94).
_FICLONE = 0x40049409


class MaterializationStrategy(str, Enum):
    AUTO = "auto"
    CLONE = "clone"
    FAST_COPY = "fast_copy"
    STREAM_COPY = "stream_copy"

    # Deprecated aliases kept for callers written against the earlier names.
    REFLINK = "clone"
    COPY = "stream_copy"


@dataclass(frozen=True, slots=True)
class MaterializationReport:
    strategy_used: str
    files_materialized: int
    bytes_materialized: int
    duration_seconds: float


class WorkspaceMaterializer:
    """High-speed, validated workspace materializer for container and clean-room sandboxes."""

    def __init__(
        self,
        strategy: MaterializationStrategy = MaterializationStrategy.AUTO,
        ignored_names: tuple[str, ...] = (".agentdiff", ".git"),
    ) -> None:
        self.strategy = strategy
        self.ignored_names = set(ignored_names)

    def materialize(
        self,
        source_dir: str | Path,
        target_dir: str | Path,
        *,
        filter_fn: Callable[[str], bool] | None = None,
    ) -> MaterializationReport:
        src_raw = Path(source_dir)
        if src_raw.is_symlink():
            raise ValueError("materializer source must be a real directory")
        src = src_raw.resolve(strict=True)
        dst_raw = Path(target_dir)
        if dst_raw.is_symlink():
            raise ValueError("materializer target must be a real directory")
        dst = dst_raw.resolve()
        if dst.exists() and not dst.is_dir():
            raise ValueError("materializer target must be a real directory")
        dst.mkdir(parents=True, exist_ok=True)
        self._assert_real_directory(dst)

        started = time.monotonic()
        files_count = 0
        total_bytes = 0
        strategies_seen: list[str] = []

        for root, dirs, files in os.walk(src, followlinks=False):
            dirs[:] = [d for d in dirs if d not in self.ignored_names]
            rel_root = Path(root).relative_to(src)
            current_dst = dst / rel_root
            current_dst.mkdir(parents=True, exist_ok=True)
            self._assert_real_directory(current_dst)
            self._copy_directory_mode(Path(root), current_dst)

            for filename in files:
                if filename in self.ignored_names:
                    continue
                relpath = (rel_root / filename).as_posix()
                if filter_fn is not None and not filter_fn(relpath):
                    continue
                source_file = Path(root) / filename
                target_file = current_dst / filename
                if target_file.is_symlink() or target_file.exists():
                    raise RuntimeError(f"materializer target already exists: {relpath}")
                size, strategy = self._copy_file(source_file, target_file)
                files_count += 1
                total_bytes += size
                strategies_seen.append(strategy)

        elapsed = time.monotonic() - started
        actual = _dominant_strategy(self.strategy, strategies_seen)
        return MaterializationReport(
            strategy_used=actual,
            files_materialized=files_count,
            bytes_materialized=total_bytes,
            duration_seconds=elapsed,
        )

    def _copy_file(self, src: Path, dst: Path) -> tuple[int, str]:
        """Copy one file preserving content, size, and mode on every path."""
        info = src.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(
                f"materializer refuses symlink {src}: unsafe entries are rejected, not followed"
            )
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError(
                f"materializer refuses special file {src}: unsupported entry types are rejected"
            )
        if info.st_nlink != 1:
            raise RuntimeError(
                f"materializer refuses hardlinked file {src}: hardlink ambiguity is rejected"
            )

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(src, flags)
        try:
            opened = os.fstat(source_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_dev != info.st_dev
                or opened.st_ino != info.st_ino
            ):
                raise RuntimeError("materializer source changed while opening")
            strategy = self._copy_descriptor(source_fd, dst, opened.st_size)
            finished = os.fstat(source_fd)
            if (
                finished.st_dev != opened.st_dev
                or finished.st_ino != opened.st_ino
                or finished.st_size != opened.st_size
                or finished.st_mtime_ns != opened.st_mtime_ns
            ):
                raise RuntimeError("materializer source changed while copying")
        finally:
            os.close(source_fd)
        if os.name != "nt":
            dst.chmod(stat.S_IMODE(info.st_mode))
        return info.st_size, strategy

    def _copy_descriptor(self, source_fd: int, dst: Path, size: int) -> str:
        """Copy from an open source descriptor using the configured strategy."""
        requested = self.strategy
        if requested is MaterializationStrategy.CLONE:
            return self._try_clone(source_fd, dst, size) or self._stream_copy(source_fd, dst, size)
        if requested is MaterializationStrategy.FAST_COPY:
            try:
                return self._fast_copy(source_fd, dst, size)
            except OSError:
                # copy_file_range may be unavailable (e.g. removed in
                # Python 3.14) or unsupported by the filesystem; the report
                # records the actual strategy used.
                return self._stream_copy(source_fd, dst, size)
        if requested is MaterializationStrategy.STREAM_COPY:
            return self._stream_copy(source_fd, dst, size)
        # AUTO: clone when supported, then fast copy, then streaming.
        cloned = self._try_clone(source_fd, dst, size)
        if cloned is not None:
            return cloned
        try:
            return self._fast_copy(source_fd, dst, size)
        except OSError:
            return self._stream_copy(source_fd, dst, size)

    def _try_clone(self, source_fd: int, dst: Path, size: int) -> str | None:
        """Linux FICLONE reflink; returns None when unsupported."""
        if os.name == "nt" or not hasattr(os, "O_NOFOLLOW"):
            return None
        try:
            dst_fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError:
            raise RuntimeError(f"materializer target exists: {dst}") from None
        try:
            import fcntl

            fcntl.ioctl(dst_fd, _FICLONE, source_fd)
            os.fsync(dst_fd)
            return "clone"
        except OSError:
            # Clone unsupported: remove the empty probe file so the
            # fallback strategy can create the destination itself.
            with contextlib.suppress(OSError):
                dst.unlink(missing_ok=True)
            return None
        finally:
            os.close(dst_fd)

    def _fast_copy(self, source_fd: int, dst: Path, size: int) -> str:
        """copy_file_range: an accelerated copy primitive, not a guaranteed reflink."""
        if not hasattr(os, "copy_file_range"):
            raise OSError("copy_file_range is unavailable")
        try:
            dst_fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError:
            raise RuntimeError(f"materializer target exists: {dst}") from None
        try:
            total = 0
            while total < size:
                copied = os.copy_file_range(source_fd, dst_fd, size - total)
                if copied == 0:
                    break
                total += copied
            if total != size:
                raise OSError("copy_file_range produced a short copy")
            os.fsync(dst_fd)
            return "fast_copy"
        except OSError:
            with contextlib.suppress(OSError):
                dst.unlink(missing_ok=True)
            raise
        finally:
            os.close(dst_fd)

    def _stream_copy(self, source_fd: int, dst: Path, size: int) -> str:
        dst_fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        digest = hashlib.sha256()
        copied = 0
        try:
            with (
                os.fdopen(source_fd, "rb", closefd=False) as src,
                os.fdopen(dst_fd, "wb", closefd=False) as output,
            ):
                while chunk := src.read(_CHUNK_SIZE):
                    output.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            if copied != size:
                raise OSError("streaming copy produced a short copy")
            return "stream_copy"
        finally:
            if dst_fd >= 0:
                os.close(dst_fd)

    def _copy_directory_mode(self, src_dir: Path, dst_dir: Path) -> None:
        if os.name == "nt":
            return
        with contextlib.suppress(OSError):
            mode = stat.S_IMODE(src_dir.lstat().st_mode)
            dst_dir.chmod(mode)

    @staticmethod
    def _assert_real_directory(path: Path) -> None:
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"materializer path is not a real directory: {path}")


def _dominant_strategy(requested: MaterializationStrategy, seen: list[str]) -> str:
    if not seen:
        return requested.value
    counts: dict[str, int] = {}
    for name in seen:
        counts[name] = counts.get(name, 0) + 1
    return max(counts, key=lambda name: counts[name])

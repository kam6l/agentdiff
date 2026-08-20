"""Fast copy-on-write / reflink / copy workspace materialization for clean-room runtimes."""

from __future__ import annotations

import os
import shutil
import stat
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

_CHUNK_SIZE = 1024 * 1024


class MaterializationStrategy(str, Enum):
    AUTO = "auto"
    REFLINK = "reflink"
    COPY = "copy"
    FAST_COPY = "fast_copy"
    STREAM_COPY = "stream_copy"


@dataclass(frozen=True, slots=True)
class MaterializationReport:
    strategy_used: str
    files_materialized: int
    bytes_materialized: int
    duration_seconds: float


class WorkspaceMaterializer:
    """High-speed workspace materializer for container and clean-room sandboxes."""

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
        target_path = Path(target_dir)
        if target_path.is_symlink():
            raise ValueError("target directory cannot be a symlink, must be a real directory")
        src = Path(source_dir).resolve(strict=True)
        dst = target_path.resolve()
        dst.mkdir(parents=True, exist_ok=True, mode=0o700)

        started = time.monotonic()
        files_count = 0
        total_bytes = 0

        for root, dirs, files in os.walk(src, followlinks=False):
            # Exclude ignored directories
            dirs[:] = [d for d in dirs if d not in self.ignored_names]
            rel_root = Path(root).relative_to(src)
            current_dst = dst / rel_root
            current_dst.mkdir(mode=0o700, parents=True, exist_ok=True)

            for filename in files:
                if filename in self.ignored_names:
                    continue
                relpath = (rel_root / filename).as_posix()
                if filter_fn is not None and not filter_fn(relpath):
                    continue

                source_file = Path(root) / filename
                target_file = current_dst / filename

                size = self._copy_file(source_file, target_file)
                files_count += 1
                total_bytes += size

        elapsed = time.monotonic() - started
        strategy_name = (
            "stream_copy"
            if self.strategy == MaterializationStrategy.STREAM_COPY
            else (
                "fast_copy"
                if self.strategy == MaterializationStrategy.FAST_COPY
                else self.strategy.value
            )
        )
        return MaterializationReport(
            strategy_used=strategy_name,
            files_materialized=files_count,
            bytes_materialized=total_bytes,
            duration_seconds=elapsed,
        )

    def _copy_file(self, src: Path, dst: Path) -> int:
        info = src.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"symlink rejected in workspace materialization: {src}")
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f"special file rejected in workspace materialization: {src}")
        if info.st_nlink > 1:
            raise RuntimeError(f"hardlink rejected in workspace materialization: {src}")

        # Reflink attempt on POSIX if requested/auto
        if self.strategy in {
            MaterializationStrategy.AUTO,
            MaterializationStrategy.REFLINK,
            MaterializationStrategy.FAST_COPY,
        } and hasattr(os, "copy_file_range"):
            try:
                src_fd = os.open(src, os.O_RDONLY | getattr(os, "O_BINARY", 0))
                dst_fd = os.open(
                    dst,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0),
                    0o644,
                )
                try:
                    total = 0
                    while total < info.st_size:
                        copied = os.copy_file_range(src_fd, dst_fd, info.st_size - total)
                        if copied == 0:
                            break
                        total += copied
                    return total
                finally:
                    os.close(src_fd)
                    os.close(dst_fd)
            except OSError:
                pass

        # Robust streaming fallback
        with open(src, "rb") as input_f, open(dst, "wb") as output_f:
            shutil.copyfileobj(input_f, output_f, length=_CHUNK_SIZE)

        mode = stat.S_IMODE(info.st_mode)
        if os.name != "nt":
            import contextlib

            with contextlib.suppress(OSError):
                dst.chmod(mode)

        return info.st_size

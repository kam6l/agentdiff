"""Advisory workspace lease to prevent concurrent promotion races.

The lease coordinates only AgentDiff-aware promotion processes. The lock
file (``.agentdiff/promotion.lock``) is created once and **never unlinked**:
deleting the pathname while another process holds a lock on the old inode
would let two processes believe they both hold the lease. The lock is an
OS-level exclusive advisory lock (``flock`` on POSIX, ``LockFileEx``-style
byte locking on Windows) that is released automatically when the owning
process exits, so crashed promotions never leave a stale lease.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

_LOCK_BYTE = b"\x00"


class PromotionLockError(RuntimeError):
    """Raised when the repository lease cannot be acquired."""


class WorkspaceLease:
    """Cross-platform advisory lock for AgentDiff promotion transactions."""

    def __init__(self, root: str | Path, run_id: str) -> None:
        self.root = Path(root).resolve()
        self.run_id = run_id
        self.lock_dir = self.root / ".agentdiff"
        self.lock_file = self.lock_dir / "promotion.lock"
        self._fd: int | None = None

    def acquire(self, timeout_seconds: float = 5.0) -> None:
        """Acquire an exclusive advisory lock with timeout.

        The lock file is created once and intentionally left in place on
        release; only the OS-level lock is dropped.
        """
        self.lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_seconds

        while True:
            descriptor = None
            try:
                flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
                descriptor = os.open(str(self.lock_file), flags, 0o600)
                self._lock_descriptor(descriptor)
                # Lock acquired: write lease metadata while the lock is held.
                metadata = {
                    "run_id": self.run_id,
                    "pid": os.getpid(),
                    "platform": platform.platform(),
                    "acquired_at": datetime.now(timezone.utc).isoformat(),
                }
                payload = json.dumps(metadata, indent=2).encode("utf-8")
                os.ftruncate(descriptor, 0)
                os.lseek(descriptor, 0, os.SEEK_SET)
                os.write(descriptor, payload)
                os.fsync(descriptor)
                self._fd = descriptor
                return
            except (BlockingIOError, OSError, PermissionError):
                if descriptor is not None:
                    import contextlib

                    with contextlib.suppress(OSError):
                        os.close(descriptor)
                if time.monotonic() >= deadline:
                    raise PromotionLockError(
                        f"could not acquire promotion lease on {self.lock_file}: "
                        "another process is promoting"
                    ) from None
                time.sleep(0.1)

    @staticmethod
    def _lock_descriptor(descriptor: int) -> None:
        """Apply the platform's exclusive advisory lock (non-blocking)."""
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def release(self) -> None:
        """Unlock and close; the lock file itself is never removed.

        Removing the pathname would open the inode-reuse race described in
        the module docstring, so the file is left in place as the stable
        lock object for every future promotion.
        """
        descriptor = self._fd
        self._fd = None
        if descriptor is None:
            return
        import contextlib

        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                with contextlib.suppress(OSError):
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                with contextlib.suppress(OSError):
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            with contextlib.suppress(OSError):
                os.close(descriptor)

    @contextmanager
    def hold(self, timeout_seconds: float = 5.0) -> Generator[WorkspaceLease, None, None]:
        self.acquire(timeout_seconds=timeout_seconds)
        try:
            yield self
        finally:
            self.release()

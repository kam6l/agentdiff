"""Advisory workspace lease to prevent concurrent promotion races."""

from __future__ import annotations

import contextlib
import json
import os
import platform
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator


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
        """Acquire an exclusive advisory lock with timeout."""
        self.lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_seconds

        while True:
            try:
                flags = os.O_RDWR | os.O_CREAT
                self._fd = os.open(str(self.lock_file), flags, 0o600)
                if os.name == "nt":
                    import msvcrt

                    # Lock 1 byte at position 0 in non-blocking mode
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]

                # Write lease metadata
                metadata = {
                    "run_id": self.run_id,
                    "pid": os.getpid(),
                    "platform": platform.platform(),
                    "acquired_at": datetime.now(timezone.utc).isoformat(),
                }
                os.ftruncate(self._fd, 0)
                os.lseek(self._fd, 0, os.SEEK_SET)
                os.write(self._fd, json.dumps(metadata, indent=2).encode("utf-8"))
                return
            except (BlockingIOError, OSError, PermissionError) as exc:
                if self._fd is not None:
                    with contextlib.suppress(OSError):
                        os.close(self._fd)
                    self._fd = None
                if time.monotonic() >= deadline:
                    msg = (
                        f"could not acquire promotion lease on {self.lock_file}: "
                        "another process is promoting"
                    )
                    raise PromotionLockError(msg) from exc
                time.sleep(0.1)

    def release(self) -> None:
        """Release the advisory lock and clean up lease metadata."""
        if self._fd is not None:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(self._fd, 0, os.SEEK_SET)
                    with contextlib.suppress(OSError):
                        msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    with contextlib.suppress(OSError):
                        fcntl.flock(self._fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]

                os.close(self._fd)
            finally:
                self._fd = None
                with contextlib.suppress(OSError):
                    if self.lock_file.is_file():
                        self.lock_file.unlink(missing_ok=True)

    @contextmanager
    def hold(self, timeout_seconds: float = 5.0) -> Generator[WorkspaceLease, None, None]:
        self.acquire(timeout_seconds=timeout_seconds)
        try:
            yield self
        finally:
            self.release()

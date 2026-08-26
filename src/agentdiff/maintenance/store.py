"""Symlink-safe atomic local storage for maintenance graph snapshots."""

from __future__ import annotations

import contextlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from .graph import MaintenanceGraph

_DEFAULT_MAX_BYTES = 16 * 1024 * 1024


@runtime_checkable
class MaintenanceGraphStore(Protocol):
    """Storage interface for one canonical maintenance graph snapshot."""

    def load(self) -> MaintenanceGraph | None:
        """Load the current graph, or return ``None`` when none exists."""
        ...

    def save(self, graph: MaintenanceGraph) -> Path:
        """Atomically replace the current graph snapshot."""
        ...


class LocalJSONMaintenanceStore:
    """Persist one graph as bounded, private, atomic JSON on local disk."""

    def __init__(
        self, path: str | os.PathLike[str], *, max_bytes: int = _DEFAULT_MAX_BYTES
    ) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")
        unresolved = Path(path).expanduser()
        self.path = unresolved if unresolved.is_absolute() else Path.cwd() / unresolved
        self.path = self.path.absolute()
        self.max_bytes = max_bytes

    def load(self) -> MaintenanceGraph | None:
        self._assert_no_symlink_components(include_leaf=True)
        try:
            identity = self.path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(identity.st_mode):
            raise ValueError("maintenance store must be a regular, non-symlink file")

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
        except OSError as error:
            raise ValueError("maintenance store could not be opened safely") from error
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != identity.st_dev
                or opened.st_ino != identity.st_ino
            ):
                raise ValueError("maintenance store identity changed while opening")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read(self.max_bytes + 1)
        finally:
            os.close(descriptor)
        if len(payload) > self.max_bytes:
            raise ValueError("maintenance store exceeds its size limit")
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("maintenance store contains invalid JSON") from error
        return MaintenanceGraph.from_dict(decoded)

    def save(self, graph: MaintenanceGraph) -> Path:
        if not isinstance(graph, MaintenanceGraph):
            raise TypeError("graph must be a MaintenanceGraph")
        self._assert_no_symlink_components(include_leaf=True)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._assert_no_symlink_components(include_leaf=False)
        parent_identity = self.path.parent.lstat()
        if not stat.S_ISDIR(parent_identity.st_mode):
            raise ValueError("maintenance store parent must be a real directory")
        self._assert_existing_destination()

        payload = (
            json.dumps(
                graph.to_dict(),
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        if len(payload) > self.max_bytes:
            raise ValueError("maintenance graph exceeds the store size limit")

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self._assert_no_symlink_components(include_leaf=False)
            current_parent = self.path.parent.lstat()
            if (
                current_parent.st_dev != parent_identity.st_dev
                or current_parent.st_ino != parent_identity.st_ino
            ):
                raise ValueError("maintenance store parent identity changed during write")
            self._assert_existing_destination()
            os.replace(temporary, self.path)
            if os.name != "nt":
                self.path.chmod(0o600)
            self._fsync_parent()
        finally:
            temporary.unlink(missing_ok=True)
        return self.path

    def _assert_existing_destination(self) -> None:
        try:
            identity = self.path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISREG(identity.st_mode):
            raise ValueError("maintenance store must be a regular, non-symlink file")

    def _assert_no_symlink_components(self, *, include_leaf: bool) -> None:
        candidates = [*reversed(self.path.parents)]
        if include_leaf:
            candidates.append(self.path)
        for candidate in candidates:
            try:
                identity = candidate.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(identity.st_mode):
                raise ValueError("maintenance store path cannot contain symlinks")

    def _fsync_parent(self) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor: int | None = None
        try:
            descriptor = os.open(self.path.parent, flags)
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            if descriptor is not None:
                with contextlib.suppress(OSError):
                    os.close(descriptor)

"""
Filesystem and Environment Diff Engine for AgentDiff.

Captures lightweight snapshots of system state and computes
deterministic diffs between pre- and post-execution states.
"""

import fnmatch
import hashlib
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class DiffType(Enum):
    """Types of state differences detected."""

    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    FILE_PERMISSIONS = "file_permissions"
    DIR_CREATED = "dir_created"
    DIR_DELETED = "dir_deleted"
    ENV_VAR_ADDED = "env_var_added"
    ENV_VAR_MODIFIED = "env_var_modified"
    ENV_VAR_REMOVED = "env_var_removed"
    PROCESS_SPAWNED = "process_spawned"
    PROCESS_TERMINATED = "process_terminated"
    PORT_OPENED = "port_opened"
    PORT_CLOSED = "port_closed"


@dataclass
class DiffEntry:
    """A single state difference entry."""

    diff_type: DiffType
    path: str
    old_value: str | None = None
    new_value: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.diff_type.value,
            "path": self.path,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiffEntry":
        return cls(
            diff_type=DiffType(data["type"]),
            path=data["path"],
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", time.time()),
        )


@dataclass
class FilesystemSnapshot:
    """Lightweight snapshot of filesystem state for a set of paths."""

    file_hashes: dict[str, str] = field(default_factory=dict)  # path -> sha256
    file_sizes: dict[str, int] = field(default_factory=dict)
    file_mtimes: dict[str, float] = field(default_factory=dict)
    file_modes: dict[str, int] = field(default_factory=dict)
    directories: set[str] = field(default_factory=set)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_hashes": self.file_hashes,
            "file_sizes": self.file_sizes,
            "file_mtimes": self.file_mtimes,
            "file_modes": self.file_modes,
            "directories": list(self.directories),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FilesystemSnapshot":
        return cls(
            file_hashes=data.get("file_hashes", {}),
            file_sizes=data.get("file_sizes", {}),
            file_mtimes=data.get("file_mtimes", {}),
            file_modes=data.get("file_modes", {}),
            directories=set(data.get("directories", [])),
            timestamp=data.get("timestamp", time.time()),
        )


@dataclass
class EnvironmentSnapshot:
    """Snapshot of environment variables and process state."""

    env_vars: dict[str, str] = field(default_factory=dict)
    open_ports: set[int] = field(default_factory=set)
    process_pids: set[int] = field(default_factory=set)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "env_vars": self.env_vars,
            "open_ports": list(self.open_ports),
            "process_pids": list(self.process_pids),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvironmentSnapshot":
        return cls(
            env_vars=data.get("env_vars", {}),
            open_ports=set(data.get("open_ports", [])),
            process_pids=set(data.get("process_pids", [])),
            timestamp=data.get("timestamp", time.time()),
        )


@dataclass
class DiffResult:
    """Complete diff result between two snapshots."""

    filesystem_diffs: list[DiffEntry] = field(default_factory=list)
    environment_diffs: list[DiffEntry] = field(default_factory=list)
    pre_fs_snapshot: FilesystemSnapshot | None = None
    post_fs_snapshot: FilesystemSnapshot | None = None
    pre_env_snapshot: EnvironmentSnapshot | None = None
    post_env_snapshot: EnvironmentSnapshot | None = None
    duration_seconds: float = 0.0

    @property
    def all_diffs(self) -> list[DiffEntry]:
        return self.filesystem_diffs + self.environment_diffs

    @property
    def summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for diff in self.all_diffs:
            summary[diff.diff_type.value] = summary.get(diff.diff_type.value, 0) + 1
        return summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "filesystem_diffs": [d.to_dict() for d in self.filesystem_diffs],
            "environment_diffs": [d.to_dict() for d in self.environment_diffs],
            "pre_fs_snapshot": self.pre_fs_snapshot.to_dict() if self.pre_fs_snapshot else None,
            "post_fs_snapshot": self.post_fs_snapshot.to_dict() if self.post_fs_snapshot else None,
            "pre_env_snapshot": self.pre_env_snapshot.to_dict() if self.pre_env_snapshot else None,
            "post_env_snapshot": self.post_env_snapshot.to_dict()
            if self.post_env_snapshot
            else None,
            "duration_seconds": self.duration_seconds,
            "summary": self.summary,
        }


class DiffEngine:
    """
    Core diff engine for capturing and comparing system state snapshots.

    Supports:
    - Filesystem content hashing (SHA256)
    - File metadata (size, mtime, permissions)
    - Directory structure
    - Environment variables
    - Open network ports
    - Process PIDs
    """

    def __init__(
        self,
        watch_paths: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
        max_file_size_mb: int = 100,
        hash_workers: int = 4,
        env_denylist: list[str] | None = None,
        capture_env_vars: bool = True,
        capture_processes: bool = True,
        capture_ports: bool = True,
    ):
        paths = watch_paths or [str(Path.cwd())]
        self.watch_paths: list[Path] = [Path(path).resolve() for path in paths]
        self.ignore_patterns = ignore_patterns or [
            "**/__pycache__/**",
            "**/.git/**",
            "**/.agentdiff/**",
            "**/node_modules/**",
            "**/.venv/**",
            "**/venv/**",
            "**/*.pyc",
            "**/*.pyo",
            "**/*.tmp",
            "**/*.swp",
        ]
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.hash_workers = hash_workers
        self.capture_env_vars = capture_env_vars
        self.capture_processes = capture_processes
        self.capture_ports = capture_ports
        self.env_denylist = env_denylist or [
            "*API_KEY*",
            "*CREDENTIAL*",
            "*PASSWORD*",
            "*PRIVATE_KEY*",
            "*SECRET*",
            "*TOKEN*",
        ]

    def _should_ignore(self, path: Path) -> bool:
        """Check if path matches any ignore pattern."""
        return any(path.match(pattern) for pattern in self.ignore_patterns)

    def _hash_file(self, path: Path) -> str | None:
        """Compute SHA256 hash of file content."""
        try:
            if path.stat().st_size > self.max_file_size:
                return None
            hasher = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError:
            return None

    def _collect_filesystem(self) -> FilesystemSnapshot:
        """Collect filesystem snapshot for all watch paths."""
        file_hashes = {}
        file_sizes = {}
        file_mtimes = {}
        file_modes = {}
        directories = set()

        for watch_path in self.watch_paths:
            if not watch_path.exists():
                continue

            for item in watch_path.rglob("*"):
                if self._should_ignore(item):
                    continue

                try:
                    stat = item.stat()
                    abs_path = str(item)

                    if item.is_file():
                        file_hashes[abs_path] = self._hash_file(item) or ""
                        file_sizes[abs_path] = stat.st_size
                        file_mtimes[abs_path] = stat.st_mtime
                        file_modes[abs_path] = stat.st_mode
                    elif item.is_dir():
                        directories.add(abs_path)
                except OSError:
                    continue

        return FilesystemSnapshot(
            file_hashes=file_hashes,
            file_sizes=file_sizes,
            file_mtimes=file_mtimes,
            file_modes=file_modes,
            directories=directories,
        )

    def _collect_environment(self) -> EnvironmentSnapshot:
        """Collect an environment snapshot without serializing likely secrets."""
        env_vars = {
            key: value
            for key, value in os.environ.items()
            if self.capture_env_vars
            and not any(
                fnmatch.fnmatch(key.upper(), pattern.upper()) for pattern in self.env_denylist
            )
        }

        # Collect open ports (Linux/Unix)
        open_ports = set()
        if self.capture_ports:
            try:
                import psutil
            except ImportError:
                pass
            else:
                try:
                    for conn in psutil.net_connections(kind="inet"):
                        if conn.status == "LISTEN" and conn.laddr:
                            open_ports.add(conn.laddr.port)
                except (OSError, psutil.Error):
                    pass

        # Collect process PIDs
        process_pids = set()
        if self.capture_processes:
            try:
                import psutil
            except ImportError:
                pass
            else:
                try:
                    for proc in psutil.process_iter(["pid"]):
                        process_pids.add(proc.info["pid"])
                except (OSError, psutil.Error):
                    pass

        return EnvironmentSnapshot(
            env_vars=env_vars,
            open_ports=open_ports,
            process_pids=process_pids,
        )

    def snapshot(self) -> tuple[FilesystemSnapshot, EnvironmentSnapshot]:
        """Capture complete system snapshot."""
        with ThreadPoolExecutor(max_workers=2) as executor:
            fs_future = executor.submit(self._collect_filesystem)
            env_future = executor.submit(self._collect_environment)
            fs_snapshot = fs_future.result()
            env_snapshot = env_future.result()
        return fs_snapshot, env_snapshot

    def diff(
        self,
        pre_fs: FilesystemSnapshot,
        post_fs: FilesystemSnapshot,
        pre_env: EnvironmentSnapshot,
        post_env: EnvironmentSnapshot,
    ) -> DiffResult:
        """Compute diff between two snapshots."""
        start = time.time()
        fs_diffs = []
        env_diffs = []

        # Filesystem diffs
        all_paths = set(pre_fs.file_hashes.keys()) | set(post_fs.file_hashes.keys())

        for path in sorted(all_paths):
            pre_hash = pre_fs.file_hashes.get(path)
            post_hash = post_fs.file_hashes.get(path)

            if pre_hash is None and post_hash is not None:
                # File created
                fs_diffs.append(
                    DiffEntry(
                        diff_type=DiffType.FILE_CREATED,
                        path=path,
                        new_value=post_hash,
                        metadata={"size": post_fs.file_sizes.get(path)},
                    )
                )
            elif pre_hash is not None and post_hash is None:
                # File deleted
                fs_diffs.append(
                    DiffEntry(
                        diff_type=DiffType.FILE_DELETED,
                        path=path,
                        old_value=pre_hash,
                        metadata={"size": pre_fs.file_sizes.get(path)},
                    )
                )
            elif pre_hash != post_hash:
                # File modified
                fs_diffs.append(
                    DiffEntry(
                        diff_type=DiffType.FILE_MODIFIED,
                        path=path,
                        old_value=pre_hash,
                        new_value=post_hash,
                        metadata={
                            "old_size": pre_fs.file_sizes.get(path),
                            "new_size": post_fs.file_sizes.get(path),
                        },
                    )
                )

        # Directory diffs
        pre_dirs = pre_fs.directories
        post_dirs = post_fs.directories

        for d in post_dirs - pre_dirs:
            fs_diffs.append(
                DiffEntry(
                    diff_type=DiffType.DIR_CREATED,
                    path=d,
                )
            )
        for d in pre_dirs - post_dirs:
            fs_diffs.append(
                DiffEntry(
                    diff_type=DiffType.DIR_DELETED,
                    path=d,
                )
            )

        # Permission diffs
        for path in set(pre_fs.file_modes.keys()) & set(post_fs.file_modes.keys()):
            if pre_fs.file_modes[path] != post_fs.file_modes[path]:
                fs_diffs.append(
                    DiffEntry(
                        diff_type=DiffType.FILE_PERMISSIONS,
                        path=path,
                        old_value=oct(pre_fs.file_modes[path]),
                        new_value=oct(post_fs.file_modes[path]),
                    )
                )

        # Environment variable diffs
        all_env_keys = set(pre_env.env_vars.keys()) | set(post_env.env_vars.keys())
        for key in sorted(all_env_keys):
            pre_val = pre_env.env_vars.get(key)
            post_val = post_env.env_vars.get(key)

            if pre_val is None and post_val is not None:
                env_diffs.append(
                    DiffEntry(
                        diff_type=DiffType.ENV_VAR_ADDED,
                        path=key,
                        new_value=post_val,
                    )
                )
            elif pre_val is not None and post_val is None:
                env_diffs.append(
                    DiffEntry(
                        diff_type=DiffType.ENV_VAR_REMOVED,
                        path=key,
                        old_value=pre_val,
                    )
                )
            elif pre_val != post_val:
                env_diffs.append(
                    DiffEntry(
                        diff_type=DiffType.ENV_VAR_MODIFIED,
                        path=key,
                        old_value=pre_val,
                        new_value=post_val,
                    )
                )

        # Process diffs
        spawned = post_env.process_pids - pre_env.process_pids
        terminated = pre_env.process_pids - post_env.process_pids
        for pid in spawned:
            env_diffs.append(
                DiffEntry(
                    diff_type=DiffType.PROCESS_SPAWNED,
                    path=str(pid),
                )
            )
        for pid in terminated:
            env_diffs.append(
                DiffEntry(
                    diff_type=DiffType.PROCESS_TERMINATED,
                    path=str(pid),
                )
            )

        # Port diffs
        opened = post_env.open_ports - pre_env.open_ports
        closed = pre_env.open_ports - post_env.open_ports
        for port in opened:
            env_diffs.append(
                DiffEntry(
                    diff_type=DiffType.PORT_OPENED,
                    path=str(port),
                )
            )
        for port in closed:
            env_diffs.append(
                DiffEntry(
                    diff_type=DiffType.PORT_CLOSED,
                    path=str(port),
                )
            )

        return DiffResult(
            filesystem_diffs=fs_diffs,
            environment_diffs=env_diffs,
            pre_fs_snapshot=pre_fs,
            post_fs_snapshot=post_fs,
            pre_env_snapshot=pre_env,
            post_env_snapshot=post_env,
            duration_seconds=time.time() - start,
        )

    def diff_from_snapshots(
        self,
        pre_snapshot: tuple,
        post_snapshot: tuple,
    ) -> DiffResult:
        """Convenience method to diff from snapshot tuples."""
        return self.diff(
            pre_snapshot[0],
            post_snapshot[0],
            pre_snapshot[1],
            post_snapshot[1],
        )

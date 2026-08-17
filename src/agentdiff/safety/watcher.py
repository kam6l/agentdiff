"""Hybrid event-driven and deterministic polling safety watcher."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agentdiff.policy import Policy
from agentdiff.state import FilesystemManifest

from .controller import SafetyController


@dataclass
class WatcherStats:
    hints_received: int = 0
    full_scans_performed: int = 0
    last_scan_duration: float = 0.0


class HybridSafetyWatcher:
    """Hybrid watcher that uses fast event hints to accelerate deterministic safety audits.

    Watcher events are strictly acceleration hints: security verdicts and budget
    enforcement decisions are always computed from ground-truth filesystem snapshots.
    """

    def __init__(
        self,
        *,
        root: str | Path,
        policy: Policy,
        before: FilesystemManifest,
        backend: str = "local-hybrid",
        isolated_workspace: bool = False,
        controller: SafetyController | None = None,
        on_terminate: Callable[[], None] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.policy = policy
        self.before = before
        self.controller = controller or SafetyController(
            policy=policy,
            before=before,
            backend=backend,
            isolated_workspace=isolated_workspace,
        )
        self.on_terminate = on_terminate
        self.stats = WatcherStats()
        self._dirty = False

    def notify_event(self, path: str | None = None) -> None:
        """Receive an OS or runtime filesystem event hint."""
        self.stats.hints_received += 1
        self._dirty = True

    def poll(
        self,
        *,
        duration_seconds: float,
        processes_spawned: int,
        force: bool = False,
    ) -> bool:
        """Evaluate safety state using dirty hints or periodic schedule."""
        force_fs = force or self._dirty
        start = time.monotonic()
        should_terminate = self.controller.observe(
            root=self.root,
            duration_seconds=duration_seconds,
            processes_spawned=processes_spawned,
            force_filesystem=force_fs,
            runtime_active=True,
        )
        if force_fs:
            self.stats.full_scans_performed += 1
            self.stats.last_scan_duration = time.monotonic() - start
            self._dirty = False

        if should_terminate and self.on_terminate is not None:
            self.on_terminate()

        return should_terminate

"""Hybrid event-driven and deterministic polling safety watcher.

The watcher uses fast event hints to accelerate deterministic safety audits:

    OS filesystem event source
            ↓
    dirty path/directory queue
            ↓
    targeted policy checks      (acceleration hints, never verdicts)
            +
    periodic full reconciliation (authoritative)
            ↓
    SafetyController

Rules enforced here:

- Watcher events are strictly hints. Security verdicts and budget
  enforcement always come from authoritative full captures via
  :class:`SafetyController`.
- Targeted dirty-path checks fail fast on clearly protected paths but never
  compute budgets.
- Full reconciliation runs on a configurable cadence, after a configurable
  number of events, on overflow, and whenever a targeted check cannot
  resolve the dirty state.
- If the event backend fails or is unsupported, the watcher degrades to
  polling and records ``status: degraded`` with the reason; it never
  silently stops live observation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agentdiff.policy import Policy
from agentdiff.state import FilesystemManifest, FilesystemScanner

from .controller import SafetyController
from .watchers.base import EventSource
from .watchers.polling import PollingEventSource


@dataclass
class WatcherStats:
    hints_received: int = 0
    targeted_checks_performed: int = 0
    full_scans_performed: int = 0
    last_scan_duration: float = 0.0


@dataclass
class WatcherStatus:
    backend: str = "polling"
    status: str = "active"
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"backend": self.backend, "status": self.status, "reason": self.reason}


class HybridSafetyWatcher:
    """Hybrid watcher that uses fast event hints to accelerate deterministic safety audits."""

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
        event_source: EventSource | None = None,
        reconcile_interval_seconds: float = 2.0,
        max_dirty_before_reconcile: int = 100,
        reconcile_after_event_seconds: float = 0.1,
    ) -> None:
        if reconcile_interval_seconds <= 0:
            raise ValueError("reconcile_interval_seconds must be greater than zero")
        if max_dirty_before_reconcile <= 0:
            raise ValueError("max_dirty_before_reconcile must be greater than zero")
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
        self.reconcile_interval_seconds = reconcile_interval_seconds
        self.max_dirty_before_reconcile = max_dirty_before_reconcile
        self.reconcile_after_event_seconds = reconcile_after_event_seconds
        self._dirty_paths: set[str] = set()
        self._dirty_directories: set[str] = set()
        self._last_full_scan = time.monotonic()
        self._last_event = 0.0
        self._event_source: EventSource | None = event_source
        self._observe_root = self.root
        self._scanner_cache: dict[Path, FilesystemScanner] = {}
        self.status = WatcherStatus(backend=event_source.backend if event_source else "polling")
        self._started = False

    @property
    def report(self):
        """Delegated safety report of the wrapped controller."""
        return self.controller.report

    # ------------------------------------------------------------------
    # Event lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the event source; degrade to polling on failure."""
        if self._started:
            return
        self._started = True
        if self._event_source is None:
            return
        try:
            self._event_source.start()
            self.status = WatcherStatus(backend=self._event_source.backend, status="active")
        except (OSError, RuntimeError) as error:
            self._event_source = PollingEventSource()
            self.status = WatcherStatus(
                backend=self._event_source.backend,
                status="degraded",
                reason=f"event backend failed to start: {error}",
            )

    def stop(self) -> None:
        if self._event_source is not None and self._started:
            try:
                self._event_source.stop()
            finally:
                self._started = False

    def notify_event(self, path: str | None = None) -> None:
        """Receive an OS or runtime filesystem event hint."""
        self.stats.hints_received += 1
        self._last_event = time.monotonic()
        if not path:
            self._dirty_directories.add("")
            return
        normalized = path.replace("\\", "/")
        try:
            relative = str(Path(normalized).relative_to(self.root)).replace("\\", "/")
        except ValueError:
            relative = normalized
        self._dirty_paths.add(relative)
        self._dirty_directories.add(str(Path(relative).parent) if relative else "")

    def drain_events(self) -> None:
        if self._event_source is None:
            return
        try:
            for event_path in self._event_source.drain():
                self.notify_event(event_path)
        except (OSError, RuntimeError):
            self._degrade("event drain failed")

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def poll(
        self,
        *,
        duration_seconds: float,
        processes_spawned: int,
        force: bool = False,
    ) -> bool:
        """Evaluate safety using dirty hints, targeted checks, and scheduled scans."""
        self.drain_events()
        if self.controller.report.terminated:
            return True
        self.controller.check_budgets(
            duration_seconds=duration_seconds,
            processes_spawned=processes_spawned,
            runtime_active=True,
        )
        if self.controller.report.terminated:
            self._signal_terminate()
            return True

        now = time.monotonic()
        due_for_reconcile = (
            force
            or now - self._last_full_scan >= self.reconcile_interval_seconds
            or len(self._dirty_paths) >= self.max_dirty_before_reconcile
            or (self._dirty_paths and now - self._last_event >= self.reconcile_after_event_seconds)
        )
        if due_for_reconcile:
            self._full_reconcile(runtime_active=True)
        else:
            self._targeted_check(runtime_active=True)
        if self.controller.report.terminated:
            self._signal_terminate()
            return True
        return False

    def observe(
        self,
        *,
        root: str | Path,
        duration_seconds: float,
        processes_spawned: int,
        force_filesystem: bool = False,
        runtime_active: bool = True,
    ) -> bool:
        """Controller-compatible entry point used by runtime backends.

        The per-call ``root`` is authoritative for this observation window:
        isolated backends observe their private workspace, local backends
        observe the live host root.
        """
        self._observe_root = Path(root).resolve()
        if not runtime_active:
            self._full_reconcile(runtime_active=False)
            return self.controller.report.terminated
        return self.poll(
            duration_seconds=duration_seconds,
            processes_spawned=processes_spawned,
            force=force_filesystem,
        )

    @property
    def terminated(self) -> bool:
        return self.controller.report.terminated

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _scanner_for(self) -> FilesystemScanner:
        scanner = self._scanner_cache.get(self._observe_root)
        if scanner is None:
            scanner = FilesystemScanner(
                self._observe_root,
                protected_patterns=list(self.policy.filesystem.deny),
            )
            self._scanner_cache[self._observe_root] = scanner
        return scanner

    def _targeted_check(self, *, runtime_active: bool) -> None:
        """Fail fast on dirty paths that clearly hit a protected pattern."""
        if self.policy.version < 2:
            self._dirty_paths.clear()
            self._dirty_directories.clear()
            return
        scanner = self._scanner_for()
        for relative in sorted(self._dirty_paths):
            self.stats.targeted_checks_performed += 1
            try:
                record = scanner.capture_one(relative)
            except (OSError, ValueError):
                # Cannot resolve dirty state cheaply: force a full reconcile.
                self._full_reconcile(runtime_active=runtime_active)
                return
            before_record = self.before.files.get(relative)
            changed = record is not None and (
                before_record is None
                or record.sha256 != before_record.sha256
                or record.size != before_record.size
                or record.mode != before_record.mode
            )
            if changed:
                self.controller.check_path(relative, runtime_active=runtime_active)
                if self.controller.report.terminated:
                    return
        self._dirty_paths.clear()
        self._dirty_directories.clear()

    def _full_reconcile(self, *, runtime_active: bool) -> None:
        start = time.monotonic()
        self.controller.check_filesystem(self._observe_root, runtime_active=runtime_active)
        self.stats.full_scans_performed += 1
        self.stats.last_scan_duration = time.monotonic() - start
        self._last_full_scan = time.monotonic()
        self._dirty_paths.clear()
        self._dirty_directories.clear()

    def _signal_terminate(self) -> None:
        if self.on_terminate is not None:
            self.on_terminate()

    def _degrade(self, reason: str) -> None:
        self._event_source = PollingEventSource()
        self.status = WatcherStatus(
            backend=self._event_source.backend,
            status="degraded",
            reason=reason,
        )

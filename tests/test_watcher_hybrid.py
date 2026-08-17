"""Hybrid safety watcher: dirty-path targeting, reconciliation, degradation."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentdiff.policy import load_policy
from agentdiff.safety import HybridSafetyWatcher, SafetyController
from agentdiff.safety.watchers.base import EventSource
from agentdiff.state import FilesystemScanner


class FakeEventSource:
    backend = "fake"

    def __init__(self, events: list[str | None]) -> None:
        self._events = list(events)
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def drain(self) -> list[str | None]:
        pending, self._events = self._events, []
        return pending

    def stop(self) -> None:
        self.stopped = True


class ExplodingEventSource:
    backend = "exploding"

    def start(self) -> None:
        raise RuntimeError("no event backend on this platform")

    def drain(self) -> list[str | None]:
        return []

    def stop(self) -> None:
        return None


def watcher(tmp_path: Path, *, policy_version: int = 2, **kwargs):
    policy = load_policy(
        {
            "version": policy_version,
            "filesystem": {"deny": ["**.env", "secret.txt"], "default": "allow"},
        }
    )
    before = FilesystemScanner(tmp_path).capture()
    return HybridSafetyWatcher(root=tmp_path, policy=policy, before=before, **kwargs)


def test_watcher_tracks_dirty_paths_and_runs_targeted_check(tmp_path: Path) -> None:
    source = FakeEventSource([])
    w = watcher(tmp_path, event_source=source, reconcile_interval_seconds=60)
    w.start()
    w.notify_event(str(tmp_path / "src" / "app.py"))
    assert w.stats.hints_received == 1
    assert "src/app.py" in w._dirty_paths

    terminated = w.poll(duration_seconds=1.0, processes_spawned=1)
    assert terminated is False
    assert w.stats.targeted_checks_performed >= 1
    assert w.stats.full_scans_performed == 0
    w.stop()
    assert source.stopped is True


def test_watcher_terminates_on_protected_dirty_path(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("do not touch", encoding="utf-8")
    w = watcher(tmp_path, reconcile_interval_seconds=60)
    # The protected file already exists in `before`, so mark it modified via
    # a dirty hint and force the targeted check to see a change.
    (tmp_path / "secret.txt").write_text("touched", encoding="utf-8")
    w.notify_event("secret.txt")
    terminated = w.poll(duration_seconds=1.0, processes_spawned=1)
    assert terminated is True
    assert w.controller.report.termination_reason == "protected_path"


def test_watcher_periodic_full_reconciliation(tmp_path: Path) -> None:
    w = watcher(tmp_path, reconcile_interval_seconds=60)
    w.poll(duration_seconds=1.0, processes_spawned=1, force=True)
    w.poll(duration_seconds=1.0, processes_spawned=1, force=True)
    assert w.stats.full_scans_performed >= 1


def test_watcher_degrades_to_polling_on_backend_failure(tmp_path: Path) -> None:
    source = ExplodingEventSource()
    w = watcher(tmp_path, event_source=source)
    w.start()
    assert w.status.status == "degraded"
    assert w.status.backend == "polling"
    assert "failed to start" in w.status.reason
    # Degraded watcher must still observe.
    assert w.poll(duration_seconds=1.0, processes_spawned=1) is False


def test_watcher_overflow_triggers_full_reconcile(tmp_path: Path) -> None:
    w = watcher(tmp_path, max_dirty_before_reconcile=3, reconcile_interval_seconds=60)
    for name in ("a.py", "b.py", "c.py", "d.py"):
        w.notify_event(name)
    w.poll(duration_seconds=1.0, processes_spawned=1)
    assert w.stats.full_scans_performed == 1


def test_watcher_drains_events_from_source(tmp_path: Path) -> None:
    source = FakeEventSource(["one.py", "two.py", None])
    w = watcher(tmp_path, event_source=source)
    w.start()
    w.poll(duration_seconds=1.0, processes_spawned=1)
    assert w.stats.hints_received == 3
    assert w.stats.targeted_checks_performed >= 1
    w.stop()


def test_watcher_observe_interface_matches_controller(tmp_path: Path) -> None:
    w = watcher(tmp_path)
    assert w.observe(
        root=tmp_path,
        duration_seconds=1.0,
        processes_spawned=1,
        force_filesystem=True,
        runtime_active=True,
    ) is False
    assert w.terminated is False
    assert w.report is w.controller.report


def test_watcher_force_reconcile_uses_authoritative_capture(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("one", encoding="utf-8")
    w = watcher(tmp_path, reconcile_interval_seconds=60)
    (tmp_path / "app.py").write_text("two", encoding="utf-8")
    # Without events or force, the dirty path is not known and no scan runs.
    assert w.poll(duration_seconds=1.0, processes_spawned=1) is False
    assert w.stats.full_scans_performed == 0
    # A forced observation performs the authoritative full capture.
    assert (
        w.observe(
            root=tmp_path,
            duration_seconds=1.0,
            processes_spawned=1,
            force_filesystem=True,
        )
        is False
    )
    assert w.stats.full_scans_performed == 1

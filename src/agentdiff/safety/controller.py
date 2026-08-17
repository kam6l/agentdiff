"""Deterministic live mutation and process budget controller.

The controller observes user-space state at polling boundaries. It never calls
that observation syscall interception. A backend may terminate the owned
execution domain when :attr:`terminated` becomes true; Docker additionally
keeps observed mutations away from the host repository.

The controller exposes cheap budget checks separately from the expensive
full filesystem reconciliation so a hybrid watcher can run targeted dirty-path
checks between authoritative full captures.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from agentdiff.policy import Policy, PolicyAction, PolicyEngine

if TYPE_CHECKING:
    from pathlib import Path
from agentdiff.state import FilesystemManifest, FilesystemScanner, diff_manifests

from .models import ControlLevel, SafetyEvent, SafetyReport


class SafetyController:
    """Evaluate live observations against one immutable policy."""

    def __init__(
        self,
        *,
        policy: Policy,
        before: FilesystemManifest,
        backend: str,
        isolated_workspace: bool,
        filesystem_poll_interval: float = 0.2,
    ) -> None:
        if filesystem_poll_interval <= 0:
            raise ValueError("filesystem_poll_interval must be greater than zero")
        self.policy = policy
        self.before = before
        self.engine = PolicyEngine(policy)
        self.filesystem_poll_interval = filesystem_poll_interval
        self._last_filesystem_poll = 0.0
        filesystem_level = ControlLevel.SANDBOXED if isolated_workspace else ControlLevel.OBSERVED
        self.report = SafetyReport(
            backend=backend,
            enforcement={
                "duration": ControlLevel.BLOCKED,
                "filesystem_mutations": filesystem_level,
                "protected_paths": filesystem_level,
                "processes": ControlLevel.OBSERVED,
            },
        )

    @property
    def terminated(self) -> bool:
        return self.report.terminated

    def observe(
        self,
        *,
        root: str | Path,
        duration_seconds: float,
        processes_spawned: int,
        force_filesystem: bool = False,
        runtime_active: bool = True,
    ) -> bool:
        """Record current state and return whether execution must terminate."""
        if self.report.terminated:
            return True
        self.check_budgets(
            duration_seconds=duration_seconds,
            processes_spawned=processes_spawned,
            runtime_active=runtime_active,
        )
        now = time.monotonic()
        if force_filesystem or now - self._last_filesystem_poll >= self.filesystem_poll_interval:
            self._last_filesystem_poll = now
            self.check_filesystem(root, runtime_active=runtime_active)
        return self.report.terminated

    def check_budgets(
        self,
        *,
        duration_seconds: float,
        processes_spawned: int,
        runtime_active: bool,
    ) -> None:
        """Cheap duration/process budget checks (no filesystem work)."""
        if self.report.terminated:
            return
        self._check_limit(
            "duration_seconds",
            duration_seconds,
            self.policy.limits.duration_seconds,
            runtime_active=runtime_active,
        )
        self._check_limit(
            "processes_spawned",
            processes_spawned,
            self.policy.limits.processes_spawned,
            runtime_active=runtime_active,
        )

    def check_filesystem(self, root: str | Path, *, runtime_active: bool) -> None:
        """Full authoritative reconciliation against the pre-run manifest.

        This is the only place filesystem budgets and protected-path verdicts
        are computed: event-driven dirty-path checks are hints, never truth.
        """
        if self.policy.version < 2:
            return
        try:
            current = FilesystemScanner(
                root,
                protected_patterns=list(self.policy.filesystem.deny),
            ).capture()
        except (OSError, ValueError) as error:
            self._terminate(
                metric="filesystem_observation",
                observed=type(error).__name__,
                limit=None,
                detail="live filesystem state became ambiguous",
                runtime_active=runtime_active,
            )
            return
        changes = diff_manifests(self.before, current)
        deleted = sum(change.change_type == "deleted" for change in changes)
        self._check_limit(
            "files_changed",
            len(changes),
            self.policy.limits.files_changed,
            runtime_active=runtime_active,
        )
        self._check_limit(
            "files_deleted",
            deleted,
            self.policy.limits.files_deleted,
            runtime_active=runtime_active,
        )
        if self.report.terminated:
            return
        for change in changes:
            decision = self.engine.decide_path(change.path, phase="intercept")
            if decision.action is PolicyAction.DENY:
                self._terminate(
                    metric="protected_path",
                    observed=change.change_type,
                    limit=None,
                    detail=(
                        "protected mutation was observed; the owned runtime is terminated, "
                        "but the write was not syscall-intercepted"
                    ),
                    path=change.path,
                    runtime_active=runtime_active,
                )
                return

    def check_path(self, relative: str, *, runtime_active: bool) -> None:
        """Targeted policy check for one dirty path (acceleration hint only).

        This never replaces :meth:`check_filesystem`; it only fails fast on
        clearly protected paths between authoritative reconciliations.
        """
        if self.report.terminated or self.policy.version < 2:
            return
        decision = self.engine.decide_path(relative, phase="intercept")
        if decision.action is PolicyAction.DENY:
            self._terminate(
                metric="protected_path",
                observed="targeted_check",
                limit=None,
                detail=(
                    "protected path was modified; the owned runtime is terminated, "
                    "but the write was not syscall-intercepted"
                ),
                path=relative,
                runtime_active=runtime_active,
            )

    def _check_limit(
        self,
        name: str,
        observed: float,
        limit: int | None,
        *,
        runtime_active: bool,
    ) -> None:
        if limit is None or self.report.terminated:
            return
        if self.policy.version < 2:
            return
        reached = observed > 0 if limit == 0 else observed >= limit
        if reached:
            self._terminate(
                metric=name,
                observed=observed,
                limit=limit,
                detail=f"live {name} budget reached",
                runtime_active=runtime_active,
            )

    def _terminate(
        self,
        *,
        metric: str,
        observed: float | str,
        limit: int | None,
        detail: str,
        path: str | None = None,
        runtime_active: bool,
    ) -> None:
        if self.report.terminated:
            return
        event = SafetyEvent(
            sequence=len(self.report.events) + 1,
            metric=metric,
            observed=observed,
            limit=limit,
            level=ControlLevel.BLOCKED if runtime_active else ControlLevel.OBSERVED,
            action="terminate_runtime" if runtime_active else "report_post_run",
            detail=detail,
            path=path,
        )
        self.report.events.append(event)
        if runtime_active:
            self.report.terminated = True
            self.report.termination_reason = metric

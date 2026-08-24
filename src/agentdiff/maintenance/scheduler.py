"""Pure deterministic planning for maintenance work.

The scheduler reserves no real resources and starts no work. It orders an
immutable queue, evaluates an immutable state snapshot, and returns auditable
decisions that an external orchestrator may choose to apply.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from ._canonical import (
    canonical_sha256,
    clean_bool,
    clean_int_range,
    clean_text,
    clean_timestamp,
    reject_unknown,
    require_mapping,
)


class SchedulerAction(str, Enum):
    """One side-effect-free planning decision."""

    SCHEDULE = "SCHEDULE"
    RUN = "RUN"
    DEFER = "DEFER"


class SchedulerMode(str, Enum):
    """Explicit scheduler control state."""

    RUNNING = "RUNNING"
    PAUSED = "PAUSED"


class SchedulerReason(str, Enum):
    """Stable audit reasons emitted by the scheduler policy."""

    READY = "ready"
    SCHEDULER_INPUTS_INCOMPLETE = "scheduler_inputs_incomplete"
    ITEM_INPUTS_INCOMPLETE = "item_inputs_incomplete"
    SCHEDULER_PAUSED = "scheduler_paused"
    MAINTENANCE_WINDOW_CLOSED = "maintenance_window_closed"
    CPU_REQUEST_EXCEEDS_LIMIT = "cpu_request_exceeds_limit"
    MEMORY_REQUEST_EXCEEDS_LIMIT = "memory_request_exceeds_limit"
    RATE_REQUEST_EXCEEDS_LIMIT = "rate_request_exceeds_limit"
    GLOBAL_CONCURRENCY_EXHAUSTED = "global_concurrency_exhausted"
    REPOSITORY_CONCURRENCY_EXHAUSTED = "repository_concurrency_exhausted"
    CPU_CURRENTLY_EXHAUSTED = "cpu_currently_exhausted"
    MEMORY_CURRENTLY_EXHAUSTED = "memory_currently_exhausted"
    RATE_CURRENTLY_EXHAUSTED = "rate_currently_exhausted"


@dataclass(frozen=True, slots=True)
class SchedulerResources:
    """Integer resource reservation requested by one maintenance item."""

    cpu_millis: int
    memory_mb: int
    rate_units: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cpu_millis",
            clean_int_range(self.cpu_millis, field="cpu_millis", minimum=1),
        )
        object.__setattr__(
            self,
            "memory_mb",
            clean_int_range(self.memory_mb, field="memory_mb", minimum=1),
        )
        object.__setattr__(
            self,
            "rate_units",
            clean_int_range(self.rate_units, field="rate_units", minimum=0),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "cpu_millis": self.cpu_millis,
            "memory_mb": self.memory_mb,
            "rate_units": self.rate_units,
        }

    @classmethod
    def from_dict(cls, value: object) -> SchedulerResources:
        data = require_mapping(value, field="SchedulerResources")
        reject_unknown(
            data,
            frozenset({"cpu_millis", "memory_mb", "rate_units"}),
            field="SchedulerResources",
        )
        return cls(
            cpu_millis=data.get("cpu_millis", 0),
            memory_mb=data.get("memory_mb", 0),
            rate_units=data.get("rate_units", -1),
        )


@dataclass(frozen=True, slots=True)
class SchedulerLimits:
    """Global resource and concurrency policy limits."""

    global_concurrency: int
    per_repository_concurrency: int
    cpu_millis: int
    memory_mb: int
    rate_units: int

    def __post_init__(self) -> None:
        for field in (
            "global_concurrency",
            "per_repository_concurrency",
            "cpu_millis",
            "memory_mb",
        ):
            object.__setattr__(
                self,
                field,
                clean_int_range(getattr(self, field), field=field, minimum=1),
            )
        object.__setattr__(
            self,
            "rate_units",
            clean_int_range(self.rate_units, field="rate_units", minimum=0),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "global_concurrency": self.global_concurrency,
            "per_repository_concurrency": self.per_repository_concurrency,
            "cpu_millis": self.cpu_millis,
            "memory_mb": self.memory_mb,
            "rate_units": self.rate_units,
        }

    @classmethod
    def from_dict(cls, value: object) -> SchedulerLimits:
        data = require_mapping(value, field="SchedulerLimits")
        reject_unknown(
            data,
            frozenset(
                {
                    "global_concurrency",
                    "per_repository_concurrency",
                    "cpu_millis",
                    "memory_mb",
                    "rate_units",
                }
            ),
            field="SchedulerLimits",
        )
        return cls(
            global_concurrency=data.get("global_concurrency", 0),
            per_repository_concurrency=data.get("per_repository_concurrency", 0),
            cpu_millis=data.get("cpu_millis", 0),
            memory_mb=data.get("memory_mb", 0),
            rate_units=data.get("rate_units", -1),
        )


@dataclass(frozen=True, slots=True)
class MaintenanceQueueItem:
    """One complete, resource-bounded maintenance request."""

    stable_id: str
    repository_id: str
    priority: int
    resources: SchedulerResources
    maintenance_window_open: bool
    inputs_complete: bool
    deadline: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stable_id",
            clean_text(self.stable_id, field="stable_id", required=True, max_length=256),
        )
        object.__setattr__(
            self,
            "repository_id",
            clean_text(
                self.repository_id,
                field="repository_id",
                required=True,
                max_length=512,
            ),
        )
        object.__setattr__(
            self,
            "priority",
            clean_int_range(self.priority, field="priority", minimum=0, maximum=100),
        )
        if not isinstance(self.resources, SchedulerResources):
            raise ValueError("resources must be SchedulerResources")
        object.__setattr__(
            self,
            "maintenance_window_open",
            clean_bool(self.maintenance_window_open, field="maintenance_window_open"),
        )
        object.__setattr__(
            self,
            "inputs_complete",
            clean_bool(self.inputs_complete, field="inputs_complete"),
        )
        object.__setattr__(
            self,
            "deadline",
            clean_timestamp(self.deadline, field="deadline", required=False),
        )

    @property
    def digest(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable_id": self.stable_id,
            "repository_id": self.repository_id,
            "priority": self.priority,
            "resources": self.resources.to_dict(),
            "maintenance_window_open": self.maintenance_window_open,
            "inputs_complete": self.inputs_complete,
            "deadline": self.deadline,
        }

    @classmethod
    def from_dict(cls, value: object) -> MaintenanceQueueItem:
        data = require_mapping(value, field="MaintenanceQueueItem")
        reject_unknown(
            data,
            frozenset(
                {
                    "stable_id",
                    "repository_id",
                    "priority",
                    "resources",
                    "maintenance_window_open",
                    "inputs_complete",
                    "deadline",
                }
            ),
            field="MaintenanceQueueItem",
        )
        return cls(
            stable_id=data.get("stable_id", ""),
            repository_id=data.get("repository_id", ""),
            priority=data.get("priority", -1),
            resources=SchedulerResources.from_dict(data.get("resources")),
            maintenance_window_open=clean_bool(
                data.get("maintenance_window_open"), field="maintenance_window_open"
            ),
            inputs_complete=clean_bool(data.get("inputs_complete"), field="inputs_complete"),
            deadline=data.get("deadline", ""),
        )


@dataclass(frozen=True, slots=True)
class ActiveMaintenanceRun:
    """One already-running reservation included in a scheduler snapshot."""

    stable_id: str
    repository_id: str
    resources: SchedulerResources

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stable_id",
            clean_text(self.stable_id, field="active.stable_id", required=True, max_length=256),
        )
        object.__setattr__(
            self,
            "repository_id",
            clean_text(
                self.repository_id,
                field="active.repository_id",
                required=True,
                max_length=512,
            ),
        )
        if not isinstance(self.resources, SchedulerResources):
            raise ValueError("active resources must be SchedulerResources")

    def to_dict(self) -> dict[str, Any]:
        return {
            "stable_id": self.stable_id,
            "repository_id": self.repository_id,
            "resources": self.resources.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> ActiveMaintenanceRun:
        data = require_mapping(value, field="ActiveMaintenanceRun")
        reject_unknown(
            data,
            frozenset({"stable_id", "repository_id", "resources"}),
            field="ActiveMaintenanceRun",
        )
        return cls(
            stable_id=data.get("stable_id", ""),
            repository_id=data.get("repository_id", ""),
            resources=SchedulerResources.from_dict(data.get("resources")),
        )


@dataclass(frozen=True, slots=True)
class MaintenanceSchedulerState:
    """One validated point-in-time scheduler state."""

    mode: SchedulerMode
    limits: SchedulerLimits
    active_runs: tuple[ActiveMaintenanceRun, ...]
    rate_units_used: int
    inputs_complete: bool

    def __post_init__(self) -> None:
        try:
            mode = SchedulerMode(self.mode)
        except ValueError as error:
            raise ValueError("scheduler mode is invalid") from error
        object.__setattr__(self, "mode", mode)
        if not isinstance(self.limits, SchedulerLimits):
            raise ValueError("limits must be SchedulerLimits")
        if not isinstance(self.active_runs, tuple) or any(
            not isinstance(run, ActiveMaintenanceRun) for run in self.active_runs
        ):
            raise ValueError("active_runs must be a tuple of ActiveMaintenanceRun values")
        active_runs = tuple(sorted(self.active_runs, key=lambda run: run.stable_id))
        active_ids = [run.stable_id for run in active_runs]
        if len(active_ids) != len(set(active_ids)):
            raise ValueError("active_runs contains duplicate stable IDs")
        object.__setattr__(self, "active_runs", active_runs)
        object.__setattr__(
            self,
            "rate_units_used",
            clean_int_range(self.rate_units_used, field="rate_units_used", minimum=0),
        )
        object.__setattr__(
            self,
            "inputs_complete",
            clean_bool(self.inputs_complete, field="inputs_complete"),
        )
        self._validate_usage()

    def _validate_usage(self) -> None:
        if len(self.active_runs) > self.limits.global_concurrency:
            raise ValueError("active runs exceed global concurrency")
        repository_counts: dict[str, int] = {}
        for run in self.active_runs:
            repository_counts[run.repository_id] = repository_counts.get(run.repository_id, 0) + 1
        if any(
            count > self.limits.per_repository_concurrency for count in repository_counts.values()
        ):
            raise ValueError("active runs exceed per-repository concurrency")
        used_cpu = sum(run.resources.cpu_millis for run in self.active_runs)
        used_memory = sum(run.resources.memory_mb for run in self.active_runs)
        active_rate = sum(run.resources.rate_units for run in self.active_runs)
        if used_cpu > self.limits.cpu_millis:
            raise ValueError("active runs exceed the CPU budget")
        if used_memory > self.limits.memory_mb:
            raise ValueError("active runs exceed the memory budget")
        if self.rate_units_used > self.limits.rate_units:
            raise ValueError("rate usage exceeds the rate budget")
        if self.rate_units_used < active_rate:
            raise ValueError("rate usage does not account for active reservations")

    @property
    def used_cpu_millis(self) -> int:
        return sum(run.resources.cpu_millis for run in self.active_runs)

    @property
    def used_memory_mb(self) -> int:
        return sum(run.resources.memory_mb for run in self.active_runs)

    @property
    def digest(self) -> str:
        return canonical_sha256(self.to_dict())

    def pause(self) -> MaintenanceSchedulerState:
        """Return an immutable paused snapshot."""

        return (
            self if self.mode is SchedulerMode.PAUSED else replace(self, mode=SchedulerMode.PAUSED)
        )

    def resume(self) -> MaintenanceSchedulerState:
        """Return an immutable running snapshot."""

        return (
            self
            if self.mode is SchedulerMode.RUNNING
            else replace(self, mode=SchedulerMode.RUNNING)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "limits": self.limits.to_dict(),
            "active_runs": [run.to_dict() for run in self.active_runs],
            "rate_units_used": self.rate_units_used,
            "inputs_complete": self.inputs_complete,
        }

    @classmethod
    def from_dict(cls, value: object) -> MaintenanceSchedulerState:
        data = require_mapping(value, field="MaintenanceSchedulerState")
        reject_unknown(
            data,
            frozenset({"mode", "limits", "active_runs", "rate_units_used", "inputs_complete"}),
            field="MaintenanceSchedulerState",
        )
        raw_runs = data.get("active_runs")
        if not isinstance(raw_runs, list):
            raise ValueError("active_runs must be a list")
        try:
            mode = SchedulerMode(data.get("mode", ""))
        except ValueError as error:
            raise ValueError("scheduler mode is invalid") from error
        return cls(
            mode=mode,
            limits=SchedulerLimits.from_dict(data.get("limits")),
            active_runs=tuple(ActiveMaintenanceRun.from_dict(run) for run in raw_runs),
            rate_units_used=data.get("rate_units_used", -1),
            inputs_complete=clean_bool(data.get("inputs_complete"), field="inputs_complete"),
        )


@dataclass(frozen=True, slots=True)
class MaintenanceScheduleDecision:
    """Auditable decision for one canonical queue position."""

    queue_position: int
    stable_id: str
    repository_id: str
    priority: int
    deadline: str
    resources: SchedulerResources
    item_digest: str
    action: SchedulerAction
    reasons: tuple[SchedulerReason, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_position": self.queue_position,
            "stable_id": self.stable_id,
            "repository_id": self.repository_id,
            "priority": self.priority,
            "deadline": self.deadline,
            "resources": self.resources.to_dict(),
            "item_digest": self.item_digest,
            "action": self.action.value,
            "reasons": [reason.value for reason in self.reasons],
        }


@dataclass(frozen=True, slots=True)
class MaintenanceSchedule:
    """One deterministic batch plan and its projected reservations."""

    mode: SchedulerMode
    state_digest: str
    decisions: tuple[MaintenanceScheduleDecision, ...]
    starting_active_runs: int
    planned_active_runs: int
    starting_cpu_millis: int
    planned_cpu_millis: int
    starting_memory_mb: int
    planned_memory_mb: int
    starting_rate_units: int
    planned_rate_units: int

    @property
    def digest(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "state_digest": self.state_digest,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "starting_active_runs": self.starting_active_runs,
            "planned_active_runs": self.planned_active_runs,
            "starting_cpu_millis": self.starting_cpu_millis,
            "planned_cpu_millis": self.planned_cpu_millis,
            "starting_memory_mb": self.starting_memory_mb,
            "planned_memory_mb": self.planned_memory_mb,
            "starting_rate_units": self.starting_rate_units,
            "planned_rate_units": self.planned_rate_units,
        }


class MaintenanceScheduler:
    """Order and plan maintenance items without performing side effects."""

    def plan(
        self,
        items: tuple[MaintenanceQueueItem, ...],
        state: MaintenanceSchedulerState,
    ) -> MaintenanceSchedule:
        if not isinstance(items, tuple) or any(
            not isinstance(item, MaintenanceQueueItem) for item in items
        ):
            raise TypeError("items must be a tuple of MaintenanceQueueItem values")
        if not isinstance(state, MaintenanceSchedulerState):
            raise TypeError("state must be a MaintenanceSchedulerState")
        item_ids = [item.stable_id for item in items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("queue contains duplicate stable IDs")
        active_ids = {run.stable_id for run in state.active_runs}
        if active_ids.intersection(item_ids):
            raise ValueError("queue contains an item that is already active")

        ordered = tuple(sorted(items, key=self._order_key))
        active_count = len(state.active_runs)
        used_cpu = state.used_cpu_millis
        used_memory = state.used_memory_mb
        used_rate = state.rate_units_used
        starting_active = active_count
        starting_cpu = used_cpu
        starting_memory = used_memory
        starting_rate = used_rate
        repository_counts: dict[str, int] = {}
        for run in state.active_runs:
            repository_counts[run.repository_id] = repository_counts.get(run.repository_id, 0) + 1

        decisions: list[MaintenanceScheduleDecision] = []
        for position, item in enumerate(ordered, start=1):
            defer_reasons = self._defer_reasons(item, state)
            if defer_reasons:
                decisions.append(
                    self._decision(position, item, SchedulerAction.DEFER, defer_reasons)
                )
                continue

            schedule_reasons: list[SchedulerReason] = []
            if active_count >= state.limits.global_concurrency:
                schedule_reasons.append(SchedulerReason.GLOBAL_CONCURRENCY_EXHAUSTED)
            if (
                repository_counts.get(item.repository_id, 0)
                >= state.limits.per_repository_concurrency
            ):
                schedule_reasons.append(SchedulerReason.REPOSITORY_CONCURRENCY_EXHAUSTED)
            if used_cpu + item.resources.cpu_millis > state.limits.cpu_millis:
                schedule_reasons.append(SchedulerReason.CPU_CURRENTLY_EXHAUSTED)
            if used_memory + item.resources.memory_mb > state.limits.memory_mb:
                schedule_reasons.append(SchedulerReason.MEMORY_CURRENTLY_EXHAUSTED)
            if used_rate + item.resources.rate_units > state.limits.rate_units:
                schedule_reasons.append(SchedulerReason.RATE_CURRENTLY_EXHAUSTED)
            if schedule_reasons:
                decisions.append(
                    self._decision(
                        position,
                        item,
                        SchedulerAction.SCHEDULE,
                        tuple(schedule_reasons),
                    )
                )
                continue

            active_count += 1
            repository_counts[item.repository_id] = repository_counts.get(item.repository_id, 0) + 1
            used_cpu += item.resources.cpu_millis
            used_memory += item.resources.memory_mb
            used_rate += item.resources.rate_units
            decisions.append(
                self._decision(
                    position,
                    item,
                    SchedulerAction.RUN,
                    (SchedulerReason.READY,),
                )
            )

        return MaintenanceSchedule(
            mode=state.mode,
            state_digest=state.digest,
            decisions=tuple(decisions),
            starting_active_runs=starting_active,
            planned_active_runs=active_count,
            starting_cpu_millis=starting_cpu,
            planned_cpu_millis=used_cpu,
            starting_memory_mb=starting_memory,
            planned_memory_mb=used_memory,
            starting_rate_units=starting_rate,
            planned_rate_units=used_rate,
        )

    @staticmethod
    def _order_key(item: MaintenanceQueueItem) -> tuple[int, int, str, str]:
        has_no_deadline = 1 if not item.deadline else 0
        return (-item.priority, has_no_deadline, item.deadline, item.stable_id)

    @staticmethod
    def _defer_reasons(
        item: MaintenanceQueueItem,
        state: MaintenanceSchedulerState,
    ) -> tuple[SchedulerReason, ...]:
        reasons: list[SchedulerReason] = []
        if not state.inputs_complete:
            reasons.append(SchedulerReason.SCHEDULER_INPUTS_INCOMPLETE)
        if not item.inputs_complete:
            reasons.append(SchedulerReason.ITEM_INPUTS_INCOMPLETE)
        if state.mode is SchedulerMode.PAUSED:
            reasons.append(SchedulerReason.SCHEDULER_PAUSED)
        if not item.maintenance_window_open:
            reasons.append(SchedulerReason.MAINTENANCE_WINDOW_CLOSED)
        if item.resources.cpu_millis > state.limits.cpu_millis:
            reasons.append(SchedulerReason.CPU_REQUEST_EXCEEDS_LIMIT)
        if item.resources.memory_mb > state.limits.memory_mb:
            reasons.append(SchedulerReason.MEMORY_REQUEST_EXCEEDS_LIMIT)
        if item.resources.rate_units > state.limits.rate_units:
            reasons.append(SchedulerReason.RATE_REQUEST_EXCEEDS_LIMIT)
        return tuple(reasons)

    @staticmethod
    def _decision(
        position: int,
        item: MaintenanceQueueItem,
        action: SchedulerAction,
        reasons: tuple[SchedulerReason, ...],
    ) -> MaintenanceScheduleDecision:
        return MaintenanceScheduleDecision(
            queue_position=position,
            stable_id=item.stable_id,
            repository_id=item.repository_id,
            priority=item.priority,
            deadline=item.deadline,
            resources=item.resources,
            item_digest=item.digest,
            action=action,
            reasons=reasons,
        )

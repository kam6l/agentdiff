"""Focused tests for deterministic side-effect-free maintenance scheduling."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from agentdiff.maintenance import (
    ActiveMaintenanceRun,
    MaintenanceQueueItem,
    MaintenanceScheduler,
    MaintenanceSchedulerState,
    SchedulerAction,
    SchedulerLimits,
    SchedulerMode,
    SchedulerReason,
    SchedulerResources,
)


def _resources(
    *,
    cpu_millis: int = 100,
    memory_mb: int = 256,
    rate_units: int = 1,
) -> SchedulerResources:
    return SchedulerResources(
        cpu_millis=cpu_millis,
        memory_mb=memory_mb,
        rate_units=rate_units,
    )


def _limits(
    *,
    global_concurrency: int = 4,
    per_repository_concurrency: int = 1,
    cpu_millis: int = 4_000,
    memory_mb: int = 8_192,
    rate_units: int = 100,
) -> SchedulerLimits:
    return SchedulerLimits(
        global_concurrency=global_concurrency,
        per_repository_concurrency=per_repository_concurrency,
        cpu_millis=cpu_millis,
        memory_mb=memory_mb,
        rate_units=rate_units,
    )


def _state(
    *,
    mode: SchedulerMode = SchedulerMode.RUNNING,
    limits: SchedulerLimits | None = None,
    active_runs: tuple[ActiveMaintenanceRun, ...] = (),
    rate_units_used: int = 0,
    inputs_complete: bool = True,
) -> MaintenanceSchedulerState:
    return MaintenanceSchedulerState(
        mode=mode,
        limits=limits or _limits(),
        active_runs=active_runs,
        rate_units_used=rate_units_used,
        inputs_complete=inputs_complete,
    )


def _item(
    stable_id: str,
    *,
    repository_id: str = "repo/default",
    priority: int = 50,
    resources: SchedulerResources | None = None,
    maintenance_window_open: bool = True,
    inputs_complete: bool = True,
    deadline: str = "",
) -> MaintenanceQueueItem:
    return MaintenanceQueueItem(
        stable_id=stable_id,
        repository_id=repository_id,
        priority=priority,
        resources=resources or _resources(),
        maintenance_window_open=maintenance_window_open,
        inputs_complete=inputs_complete,
        deadline=deadline,
    )


def _active(
    stable_id: str,
    *,
    repository_id: str = "repo/active",
    resources: SchedulerResources | None = None,
) -> ActiveMaintenanceRun:
    return ActiveMaintenanceRun(
        stable_id=stable_id,
        repository_id=repository_id,
        resources=resources or _resources(),
    )


def test_queue_order_is_priority_then_deadline_then_stable_id() -> None:
    items = (
        _item("priority-80", priority=80, deadline="2026-08-01T00:00:00Z"),
        _item("no-deadline", priority=90),
        _item("same-b", priority=90, deadline="2026-08-02T00:00:00Z"),
        _item("later", priority=90, deadline="2026-08-03T00:00:00Z"),
        _item("same-a", priority=90, deadline="2026-08-02T00:00:00Z"),
    )
    state = _state(limits=_limits(global_concurrency=10, per_repository_concurrency=10))
    scheduler = MaintenanceScheduler()

    forward = scheduler.plan(items, state)
    reverse = scheduler.plan(tuple(reversed(items)), state)

    expected = ("same-a", "same-b", "later", "no-deadline", "priority-80")
    assert tuple(decision.stable_id for decision in forward.decisions) == expected
    assert tuple(decision.queue_position for decision in forward.decisions) == (1, 2, 3, 4, 5)
    assert forward.decisions[0].priority == 90
    assert forward.decisions[0].deadline == "2026-08-02T00:00:00+00:00"
    assert forward.decisions[0].resources == items[2].resources
    assert forward.state_digest == state.digest
    assert forward == reverse
    assert forward.digest == reverse.digest


def test_inputs_are_immutable_canonical_and_round_trip() -> None:
    item = _item(
        "canonical",
        deadline="2026-08-22T05:00:00-07:00",
    )
    first = _active("b", repository_id="repo/b")
    second = _active("a", repository_id="repo/a")
    state = _state(
        active_runs=(first, second),
        rate_units_used=2,
        limits=_limits(per_repository_concurrency=2),
    )

    restored_item = MaintenanceQueueItem.from_dict(json.loads(json.dumps(item.to_dict())))
    restored_state = MaintenanceSchedulerState.from_dict(json.loads(json.dumps(state.to_dict())))

    assert restored_item == item
    assert item.deadline == "2026-08-22T12:00:00+00:00"
    assert restored_state == state
    assert tuple(run.stable_id for run in state.active_runs) == ("a", "b")
    assert replace(item, priority=51).digest != item.digest
    with pytest.raises(AttributeError):
        item.priority = 10  # type: ignore[misc]


def test_pause_and_resume_are_explicit_and_side_effect_free() -> None:
    scheduler = MaintenanceScheduler()
    running = _state()
    paused = running.pause()
    item = _item("pause-me")

    paused_plan = scheduler.plan((item,), paused)

    assert running.mode is SchedulerMode.RUNNING
    assert paused.mode is SchedulerMode.PAUSED
    assert paused_plan.decisions[0].action is SchedulerAction.DEFER
    assert paused_plan.decisions[0].reasons == (SchedulerReason.SCHEDULER_PAUSED,)
    assert paused.resume() == running
    assert scheduler.plan((item,), paused.resume()).decisions[0].action is SchedulerAction.RUN


def test_closed_maintenance_window_defers_without_reserving_resources() -> None:
    state = _state()
    item = _item("closed-window", maintenance_window_open=False)

    plan = MaintenanceScheduler().plan((item,), state)

    assert plan.decisions[0].action is SchedulerAction.DEFER
    assert plan.decisions[0].reasons == (SchedulerReason.MAINTENANCE_WINDOW_CLOSED,)
    assert plan.planned_active_runs == plan.starting_active_runs
    assert plan.planned_cpu_millis == plan.starting_cpu_millis


def test_incomplete_scheduler_and_item_inputs_fail_closed() -> None:
    state = _state(inputs_complete=False)
    item = _item("incomplete", inputs_complete=False)

    decision = MaintenanceScheduler().plan((item,), state).decisions[0]

    assert decision.action is SchedulerAction.DEFER
    assert decision.reasons == (
        SchedulerReason.SCHEDULER_INPUTS_INCOMPLETE,
        SchedulerReason.ITEM_INPUTS_INCOMPLETE,
    )


def test_impossible_resource_request_is_deferred_not_scheduled() -> None:
    state = _state(limits=_limits(cpu_millis=100, memory_mb=100, rate_units=1))
    item = _item(
        "impossible",
        resources=_resources(cpu_millis=101, memory_mb=101, rate_units=2),
    )

    decision = MaintenanceScheduler().plan((item,), state).decisions[0]

    assert decision.action is SchedulerAction.DEFER
    assert decision.reasons == (
        SchedulerReason.CPU_REQUEST_EXCEEDS_LIMIT,
        SchedulerReason.MEMORY_REQUEST_EXCEEDS_LIMIT,
        SchedulerReason.RATE_REQUEST_EXCEEDS_LIMIT,
    )


def test_global_concurrency_exhaustion_schedules_for_later() -> None:
    active = _active("running")
    state = _state(
        active_runs=(active,),
        limits=_limits(global_concurrency=1, per_repository_concurrency=1),
        rate_units_used=active.resources.rate_units,
    )

    decision = (
        MaintenanceScheduler()
        .plan((_item("waiting", repository_id="repo/other"),), state)
        .decisions[0]
    )

    assert decision.action is SchedulerAction.SCHEDULE
    assert decision.reasons == (SchedulerReason.GLOBAL_CONCURRENCY_EXHAUSTED,)


def test_per_repository_concurrency_isolated_from_other_repositories() -> None:
    active = _active("running", repository_id="repo/a")
    state = _state(
        active_runs=(active,),
        limits=_limits(global_concurrency=3, per_repository_concurrency=1),
        rate_units_used=active.resources.rate_units,
    )
    same = _item("same", repository_id="repo/a", priority=90)
    other = _item("other", repository_id="repo/b", priority=80)

    decisions = MaintenanceScheduler().plan((other, same), state).decisions

    assert decisions[0].stable_id == "same"
    assert decisions[0].action is SchedulerAction.SCHEDULE
    assert decisions[0].reasons == (SchedulerReason.REPOSITORY_CONCURRENCY_EXHAUSTED,)
    assert decisions[1].stable_id == "other"
    assert decisions[1].action is SchedulerAction.RUN


@pytest.mark.parametrize(
    ("limits", "active_resources", "rate_used", "item_resources", "reason"),
    (
        (
            _limits(cpu_millis=100),
            _resources(cpu_millis=80),
            1,
            _resources(cpu_millis=21),
            SchedulerReason.CPU_CURRENTLY_EXHAUSTED,
        ),
        (
            _limits(memory_mb=100),
            _resources(memory_mb=80),
            1,
            _resources(memory_mb=21),
            SchedulerReason.MEMORY_CURRENTLY_EXHAUSTED,
        ),
        (
            _limits(rate_units=10),
            _resources(rate_units=1),
            9,
            _resources(rate_units=2),
            SchedulerReason.RATE_CURRENTLY_EXHAUSTED,
        ),
    ),
)
def test_current_resource_pressure_schedules_for_later(
    limits: SchedulerLimits,
    active_resources: SchedulerResources,
    rate_used: int,
    item_resources: SchedulerResources,
    reason: SchedulerReason,
) -> None:
    active = _active("running", resources=active_resources)
    state = _state(
        limits=limits,
        active_runs=(active,),
        rate_units_used=rate_used,
    )
    item = _item("waiting", repository_id="repo/other", resources=item_resources)

    decision = MaintenanceScheduler().plan((item,), state).decisions[0]

    assert decision.action is SchedulerAction.SCHEDULE
    assert decision.reasons == (reason,)


def test_batch_planning_reserves_capacity_without_mutating_state() -> None:
    state = _state(limits=_limits(global_concurrency=2, per_repository_concurrency=2))
    items = (
        _item("third", repository_id="repo/c", priority=10),
        _item("first", repository_id="repo/a", priority=30),
        _item("second", repository_id="repo/b", priority=20),
    )
    original = state.to_dict()

    plan = MaintenanceScheduler().plan(items, state)

    assert tuple(decision.action for decision in plan.decisions) == (
        SchedulerAction.RUN,
        SchedulerAction.RUN,
        SchedulerAction.SCHEDULE,
    )
    assert plan.decisions[2].reasons == (SchedulerReason.GLOBAL_CONCURRENCY_EXHAUSTED,)
    assert plan.planned_active_runs == 2
    assert plan.planned_cpu_millis == 200
    assert plan.planned_memory_mb == 512
    assert plan.planned_rate_units == 2
    assert state.to_dict() == original


def test_planned_runs_also_enforce_per_repository_concurrency() -> None:
    state = _state(limits=_limits(global_concurrency=3, per_repository_concurrency=1))
    items = (
        _item("repo-a-2", repository_id="repo/a", priority=20),
        _item("repo-b", repository_id="repo/b", priority=10),
        _item("repo-a-1", repository_id="repo/a", priority=30),
    )

    decisions = MaintenanceScheduler().plan(items, state).decisions

    assert tuple(decision.action for decision in decisions) == (
        SchedulerAction.RUN,
        SchedulerAction.SCHEDULE,
        SchedulerAction.RUN,
    )
    assert decisions[1].reasons == (SchedulerReason.REPOSITORY_CONCURRENCY_EXHAUSTED,)


def test_zero_rate_work_can_run_when_rate_budget_is_zero() -> None:
    state = _state(limits=_limits(rate_units=0))
    free = _item("no-api", resources=_resources(rate_units=0))
    charged = _item("needs-api", resources=_resources(rate_units=1))

    decisions = MaintenanceScheduler().plan((charged, free), state).decisions

    assert decisions[0].action is SchedulerAction.DEFER
    assert decisions[0].reasons == (SchedulerReason.RATE_REQUEST_EXCEEDS_LIMIT,)
    assert decisions[1].action is SchedulerAction.RUN


def test_duplicate_or_inconsistent_inputs_are_rejected_fail_closed() -> None:
    scheduler = MaintenanceScheduler()
    item = _item("duplicate")
    with pytest.raises(ValueError, match="duplicate stable IDs"):
        scheduler.plan((item, item), _state())
    with pytest.raises(ValueError, match="already active"):
        scheduler.plan(
            (item,),
            _state(active_runs=(_active("duplicate"),), rate_units_used=1),
        )
    with pytest.raises(TypeError, match="tuple"):
        scheduler.plan([item], _state())  # type: ignore[arg-type]

    over_capacity = (
        _active("one", repository_id="repo/a"),
        _active("two", repository_id="repo/b"),
    )
    with pytest.raises(ValueError, match="global concurrency"):
        _state(
            active_runs=over_capacity,
            limits=_limits(global_concurrency=1),
            rate_units_used=2,
        )
    with pytest.raises(ValueError, match="rate budget"):
        _state(rate_units_used=101)
    with pytest.raises(ValueError, match="active reservations"):
        _state(active_runs=(_active("unaccounted"),), rate_units_used=0)


def test_malformed_serialized_inputs_are_rejected() -> None:
    item = _item("strict")
    unknown = item.to_dict()
    unknown["surprise"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        MaintenanceQueueItem.from_dict(unknown)

    missing_window = item.to_dict()
    missing_window.pop("maintenance_window_open")
    with pytest.raises(ValueError, match="boolean"):
        MaintenanceQueueItem.from_dict(missing_window)
    with pytest.raises(ValueError, match="timezone"):
        replace(item, deadline="2026-08-22T12:00:00")
    with pytest.raises(ValueError, match="between 0 and 100"):
        replace(item, priority=101)
    with pytest.raises(ValueError, match="must be a list"):
        MaintenanceSchedulerState.from_dict({**_state().to_dict(), "active_runs": {}})

"""Focused tests for budgeted proof-preserving patch minimization."""

from __future__ import annotations

from agentdiff.minimize import (
    MinimizationStatus,
    PatchGroup,
    PatchMinimizer,
    ProofCheckStatus,
)


def test_delta_debugging_removes_redundant_groups_and_preserves_order() -> None:
    groups = tuple(PatchGroup(name) for name in ("required", "formatting", "comment", "extra"))
    original = groups

    result = PatchMinimizer(
        lambda candidate: any(group.id == "required" for group in candidate)
    ).minimize(groups)

    assert groups == original
    assert result.status is MinimizationStatus.MINIMIZED
    assert tuple(group.id for group in result.minimized_groups) == ("required",)
    assert tuple(group.id for group in result.removed_groups) == (
        "formatting",
        "comment",
        "extra",
    )
    assert result.minimal_within_strategy is True
    assert result.changed is True


def test_interacting_required_groups_survive_practical_ddmin() -> None:
    groups = tuple(PatchGroup(name) for name in ("implementation", "test", "comment", "style"))

    def prove(candidate: tuple[PatchGroup, ...]) -> dict[str, bool]:
        ids = {group.id for group in candidate}
        return {"proven": {"implementation", "test"} <= ids}

    result = PatchMinimizer(prove).minimize(groups)

    assert tuple(group.id for group in result.kept_groups) == ("implementation", "test")
    assert result.status is MinimizationStatus.MINIMIZED
    assert all(
        attempt.status in {ProofCheckStatus.PROVEN, ProofCheckStatus.NOT_PROVEN}
        for attempt in result.attempts
    )


def test_original_patch_must_be_proven_before_minimization() -> None:
    groups = (PatchGroup("one"), PatchGroup("two"))
    result = PatchMinimizer(lambda _candidate: False).minimize(groups)

    assert result.status is MinimizationStatus.INITIAL_NOT_PROVEN
    assert result.minimized_groups == groups
    assert result.proof_runs == 1
    assert result.combinations == 0
    assert result.changed is False


def test_proof_run_budget_stops_without_claiming_minimality() -> None:
    groups = (PatchGroup("required"), PatchGroup("extra"))
    result = PatchMinimizer(
        lambda candidate: any(group.id == "required" for group in candidate),
        max_proof_runs=1,
    ).minimize(groups)

    assert result.status is MinimizationStatus.BUDGET_EXHAUSTED
    assert result.complete is False
    assert result.minimal_within_strategy is False
    assert result.minimized_groups == groups
    assert result.reasons == ("proof-run budget reached",)


def test_single_redundant_group_can_reduce_to_empty_patch() -> None:
    result = PatchMinimizer(lambda _candidate: True).minimize((PatchGroup("redundant"),))

    assert result.status is MinimizationStatus.MINIMIZED
    assert result.minimized_groups == ()
    assert tuple(group.id for group in result.removed_groups) == ("redundant",)


def test_inconclusive_candidate_does_not_claim_minimality() -> None:
    groups = (PatchGroup("required"), PatchGroup("uncertain"))

    def prove(candidate: tuple[PatchGroup, ...]) -> bool:
        if len(candidate) < len(groups):
            raise TimeoutError("candidate budget")
        return True

    result = PatchMinimizer(prove).minimize(groups)

    assert result.status is MinimizationStatus.INCONCLUSIVE
    assert result.complete is False
    assert result.minimal_within_strategy is False
    assert result.minimized_groups == groups

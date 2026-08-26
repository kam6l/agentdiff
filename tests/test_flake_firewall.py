"""Focused tests for deterministic repeated-sample flake classification."""

from __future__ import annotations

from agentdiff.proof import (
    FlakeCheck,
    FlakeClassification,
    FlakeExecution,
    FlakeFirewall,
    FlakeSampleStatus,
    InfrastructureFailure,
)


def test_repeated_exact_argv_passes_are_stable_proof_eligible() -> None:
    seen: list[tuple[tuple[str, ...], float]] = []

    def runner(command: tuple[str, ...], timeout: float) -> FlakeExecution:
        seen.append((command, timeout))
        return FlakeExecution(0, command=command, output="3 passed")

    check = FlakeCheck("unit", ("pytest", "tests/test_unit.py"), repetitions=3)
    result = FlakeFirewall(runner).assess(check, timeout_seconds=12.0)

    assert result.classification is FlakeClassification.STABLE_PASS
    assert result.pass_count == 3
    assert result.fail_count == 0
    assert result.counts_as_proof is True
    assert result.repair_eligible is False
    assert seen == [(check.command, 12.0)] * 3
    assert len(result.sample_digests) == 3
    assert result.samples[0].output_sha256
    assert "output" not in result.to_dict()["samples"][0]


def test_repeated_failures_are_stable_and_only_state_eligible_for_repair() -> None:
    result = FlakeFirewall(lambda _command, _timeout: 1).assess(
        FlakeCheck("failing", ("pytest", "tests/test_failure.py"))
    )

    assert result.classification is FlakeClassification.STABLE_FAIL
    assert result.fail_count == 3
    assert result.counts_as_proof is False
    assert result.repair_eligible is True
    assert result.may_enter_repair is True
    assert result.quarantine_candidate is None


def test_mixed_pass_and_fail_is_flaky_and_blocked_from_proof_and_repair() -> None:
    outcomes = iter((1, 0, 0))
    result = FlakeFirewall(lambda _command, _timeout: next(outcomes)).assess(
        FlakeCheck("intermittent", ("pytest", "tests/test_intermit.py"))
    )

    assert result.classification is FlakeClassification.FLAKY
    assert result.pass_count == 2
    assert result.fail_count == 1
    assert result.counts_as_proof is False
    assert result.may_enter_repair is False
    assert result.quarantine_candidate is not None
    assert result.quarantine_candidate.automatic_quarantine is False
    assert result.automatic_quarantine is False
    assert result.to_dict()["quarantine_candidate"]["fingerprint"]


def test_infrastructure_failure_is_distinct_and_inconclusive() -> None:
    calls = 0

    def runner(_command: tuple[str, ...], _timeout: float) -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise InfrastructureFailure("runner unavailable")
        return True

    result = FlakeFirewall(runner).assess(FlakeCheck("infra", ("pytest", "tests/test_infra.py")))

    assert result.classification is FlakeClassification.INCONCLUSIVE
    assert result.infrastructure_failure_count == 1
    assert result.samples[1].status is FlakeSampleStatus.INFRASTRUCTURE_FAILURE
    assert result.counts_as_proof is False
    assert result.may_enter_repair is False
    assert result.quarantine_candidate is None


def test_timeout_and_invalid_results_are_inconclusive_not_repair_inputs() -> None:
    timed_out = FlakeFirewall(
        lambda _command, _timeout: {"timed_out": True, "detail": "capacity"}
    ).assess(FlakeCheck("timeout", ("pytest", "tests/test_timeout.py")))
    invalid = FlakeFirewall(
        lambda _command, _timeout: {"valid": False, "detail": "malformed runner data"}
    ).assess(FlakeCheck("invalid", ("pytest", "tests/test_invalid.py")))

    assert timed_out.classification is FlakeClassification.INCONCLUSIVE
    assert timed_out.timeout_count == 3
    assert timed_out.may_enter_repair is False
    assert invalid.classification is FlakeClassification.INCONCLUSIVE
    assert invalid.invalid_count == 3
    assert invalid.counts_as_proof is False


def test_sample_bound_cannot_be_reported_as_stable() -> None:
    result = FlakeFirewall(
        lambda _command, _timeout: True,
        max_samples=3,
    ).assess(FlakeCheck("bounded", ("pytest", "tests/test_bounded.py"), repetitions=5))

    assert len(result.samples) == 3
    assert result.requested_samples == 5
    assert result.complete is False
    assert result.classification is FlakeClassification.INCONCLUSIVE
    assert result.counts_as_proof is False
    assert "flake sample-count budget reached" in result.reasons


def test_declared_output_variance_can_mark_same_exit_status_flaky() -> None:
    outputs = iter(("alpha", "beta", "alpha"))
    command = ("python", "observable.py")
    result = FlakeFirewall(
        lambda _command, _timeout: FlakeExecution(0, command=command, output=next(outputs))
    ).assess(FlakeCheck("observable", command, compare_output=True))

    assert result.classification is FlakeClassification.FLAKY
    assert result.pass_count == 3
    assert len({sample.output_sha256 for sample in result.samples}) == 2
    assert result.may_enter_repair is False
    assert result.quarantine_candidate is not None


def test_mismatched_advertised_command_is_invalid_evidence() -> None:
    result = FlakeFirewall(
        lambda _command, _timeout: FlakeExecution(0, command=("other",)),
    ).assess(FlakeCheck("exact", ("pytest", "tests/test_exact.py")))

    assert result.classification is FlakeClassification.INCONCLUSIVE
    assert result.invalid_count == 3
    assert result.counts_as_proof is False

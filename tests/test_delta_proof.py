"""Focused tests for deterministic causal delta proof."""

from __future__ import annotations

from agentdiff.proof.delta import (
    BehaviorContract,
    BehaviorExecution,
    BehaviorExecutionStatus,
    BehaviorExpectation,
    DeltaProofEngine,
    DeltaProofVerdict,
)


def test_bugfix_requires_same_exact_argv_to_fail_then_pass() -> None:
    seen: list[tuple[str, tuple[str, ...], float]] = []

    def baseline(command: tuple[str, ...], timeout: float) -> bool:
        seen.append(("baseline", command, timeout))
        return False

    def patched(command: tuple[str, ...], timeout: float) -> bool:
        seen.append(("patched", command, timeout))
        return True

    contract = BehaviorContract(
        id="expired-token",
        command=("pytest", "tests/auth.py::test_expired"),
        expectation=BehaviorExpectation.BUGFIX,
    )
    result = DeltaProofEngine(baseline, patched).prove(contract, timeout_seconds=12.0)

    assert result.verdict is DeltaProofVerdict.CAUSAL_DELTA_CONFIRMED
    assert result.causally_proven is True
    assert result.baseline_status is BehaviorExecutionStatus.FAIL
    assert result.patched_status is BehaviorExecutionStatus.PASS
    assert seen == [
        ("baseline", contract.command, 12.0),
        ("patched", contract.command, 12.0),
    ]


def test_feature_is_not_causal_when_behavior_already_passes_on_base() -> None:
    contract = BehaviorContract(
        id="new-export",
        command=("pytest", "tests/test_export.py::test_json"),
        expectation="FEATURE",
    )
    result = DeltaProofEngine(
        lambda _command, _timeout: True,
        lambda _command, _timeout: True,
    ).prove(contract)

    assert result.verdict is DeltaProofVerdict.DELTA_NOT_CONFIRMED
    assert result.causally_proven is False
    assert "baseline was PASS; expected FAIL" in result.reasons


def test_bugfix_is_not_causal_when_patch_still_fails() -> None:
    contract = BehaviorContract(
        id="still-broken",
        command=("pytest", "tests/test_bug.py"),
        expectation="bugfix",
        baseline="fail",
        patched="pass",
    )
    result = DeltaProofEngine(
        lambda _command, _timeout: False,
        lambda _command, _timeout: False,
    ).prove(contract)

    assert result.verdict is DeltaProofVerdict.DELTA_NOT_CONFIRMED
    assert result.causally_proven is False
    assert "patched state was FAIL; expected PASS" in result.reasons


def test_refactor_can_require_stable_observable_equivalence() -> None:
    command = ("python", "contract.py")
    contract = BehaviorContract(
        id="serialization-refactor",
        command=command,
        expectation=BehaviorExpectation.REFACTOR,
        repetitions=2,
        compare_output=True,
    )

    def execution(_command: tuple[str, ...], _timeout: float) -> BehaviorExecution:
        return BehaviorExecution(command=command, returncode=0, output='{"ok":true}')

    result = DeltaProofEngine(execution, execution).prove(contract)

    assert result.verdict is DeltaProofVerdict.BEHAVIOR_EQUIVALENCE_CONFIRMED
    assert result.causally_proven is True
    assert result.to_dict()["baseline_runs"][0]["output_sha256"]
    assert "output" not in result.to_dict()["baseline_runs"][0]


def test_refactor_reports_changed_observable_output_as_regression() -> None:
    command = ("python", "contract.py")
    contract = BehaviorContract(
        id="same-output",
        command=command,
        expectation=BehaviorExpectation.REFACTOR,
        compare_output=True,
    )

    def baseline(_command: tuple[str, ...], _timeout: float) -> BehaviorExecution:
        return BehaviorExecution(command, 0, output="before")

    def patched(_command: tuple[str, ...], _timeout: float) -> BehaviorExecution:
        return BehaviorExecution(command, 0, output="after")

    result = DeltaProofEngine(baseline, patched).prove(contract)

    assert result.verdict is DeltaProofVerdict.REGRESSION_DETECTED
    assert result.reasons == ("refactor changed the declared observable output",)


def test_repetitions_report_flaky_behavior_without_model_judgment() -> None:
    baseline_results = iter((False, True))
    contract = BehaviorContract(
        id="flaky-bugfix",
        command=("pytest", "tests/test_flaky.py"),
        expectation=BehaviorExpectation.BUGFIX,
        repetitions=2,
    )
    result = DeltaProofEngine(
        lambda _command, _timeout: next(baseline_results),
        lambda _command, _timeout: True,
    ).prove(contract)

    assert result.verdict is DeltaProofVerdict.FLAKY
    assert result.flaky is True
    assert result.reasons == ("baseline behavior was not stable across repetitions",)


def test_timeout_and_mismatched_command_are_explicit() -> None:
    contract = BehaviorContract(
        id="bounded",
        command=("pytest", "tests/test_bounded.py"),
        expectation=BehaviorExpectation.BUGFIX,
    )

    def timeout(_command: tuple[str, ...], _seconds: float) -> bool:
        raise TimeoutError("budget reached")

    timed_out = DeltaProofEngine(timeout, lambda _command, _timeout: True).prove(contract)
    assert timed_out.verdict is DeltaProofVerdict.TIMEOUT
    assert timed_out.timed_out is True

    mismatched = DeltaProofEngine(
        lambda _command, _timeout: BehaviorExecution(("other",), 1),
        lambda _command, _timeout: True,
    ).prove(contract)
    assert mismatched.verdict is DeltaProofVerdict.INVALID

    malformed = DeltaProofEngine(
        lambda _command, _timeout: {"command": None, "returncode": "not-an-int"},
        lambda _command, _timeout: True,
    ).prove(contract)
    assert malformed.verdict is DeltaProofVerdict.INVALID

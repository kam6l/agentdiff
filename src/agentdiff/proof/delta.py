"""Deterministic causal checks over independently executed code states.

``DeltaProofEngine`` is deliberately separate from :class:`ProofEngine`.  The
authoritative proof engine still decides whether a sealed patch is safe to
promote; delta proof answers the narrower question of whether one declared
behavior contract changed in the expected direction.

Executors are injected so callers can bind the exact same argv to independently
materialized baseline and patched workspaces.  No shell command is assembled
and no model is asked to interpret the result.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from agentdiff.redaction import redact_argv

BehaviorExecutor = Callable[[tuple[str, ...], float], Any]


class BehaviorExpectation(str, Enum):
    """Supported causal relationships between baseline and patched behavior."""

    BUGFIX = "BUGFIX"
    FEATURE = "FEATURE"
    REFACTOR = "REFACTOR"


class ExpectedBehavior(str, Enum):
    """Expected process-level result for one side of a behavior contract."""

    PASS = "PASS"
    FAIL = "FAIL"


class BehaviorExecutionStatus(str, Enum):
    """Truthful classification of one executor invocation."""

    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    INVALID = "INVALID"


class DeltaProofVerdict(str, Enum):
    """Causal verdicts emitted without interpreting command output with an LLM."""

    CAUSAL_DELTA_CONFIRMED = "CAUSAL_DELTA_CONFIRMED"
    BEHAVIOR_EQUIVALENCE_CONFIRMED = "BEHAVIOR_EQUIVALENCE_CONFIRMED"
    DELTA_NOT_CONFIRMED = "DELTA_NOT_CONFIRMED"
    REGRESSION_DETECTED = "REGRESSION_DETECTED"
    FLAKY = "FLAKY"
    TIMEOUT = "TIMEOUT"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class BehaviorContract:
    """One exact command and its expected baseline-to-patch relationship.

    ``BUGFIX`` and ``FEATURE`` default to ``FAIL -> PASS``. ``REFACTOR``
    defaults to ``PASS -> PASS``.  The explicit ``baseline`` and ``patched``
    fields allow a caller to serialize the complete contract rather than rely
    on those defaults.

    When ``compare_output`` is true, a refactor additionally requires both
    executors to return stable output and for its SHA-256 digest to match.
    Raw output is never included in serialized evidence.
    """

    id: str
    command: tuple[str, ...]
    expectation: BehaviorExpectation
    baseline: ExpectedBehavior | None = None
    patched: ExpectedBehavior | None = None
    repetitions: int = 1
    compare_output: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        expectation = (
            self.expectation
            if isinstance(self.expectation, BehaviorExpectation)
            else BehaviorExpectation(str(self.expectation).upper())
        )
        command = tuple(self.command)
        if not self.id.strip():
            raise ValueError("behavior contract id must not be empty")
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("behavior contract command must be non-empty exact argv")
        if self.repetitions < 1:
            raise ValueError("behavior contract repetitions must be at least 1")
        default_baseline = (
            ExpectedBehavior.PASS
            if expectation is BehaviorExpectation.REFACTOR
            else ExpectedBehavior.FAIL
        )
        baseline_value = self.baseline if self.baseline is not None else default_baseline
        patched_value = self.patched if self.patched is not None else ExpectedBehavior.PASS
        baseline = _coerce_expected_behavior(baseline_value)
        patched = _coerce_expected_behavior(patched_value)
        required_pair = (default_baseline, ExpectedBehavior.PASS)
        if (baseline, patched) != required_pair:
            raise ValueError(
                f"{expectation.value} contracts require "
                f"{required_pair[0].value} -> {required_pair[1].value}"
            )
        if self.compare_output and expectation is not BehaviorExpectation.REFACTOR:
            raise ValueError("output equivalence is only valid for REFACTOR contracts")
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "expectation", expectation)
        object.__setattr__(self, "baseline", baseline)
        object.__setattr__(self, "patched", patched)

    @property
    def contract_id(self) -> str:
        """Compatibility-friendly explicit name for the serialized ``id``."""

        return self.id

    @property
    def argv(self) -> tuple[str, ...]:
        """Return the exact argv supplied to both executors."""

        return self.command

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "command": redact_argv(self.command),
            "expectation": self.expectation.value,
            "baseline": self.baseline.value if self.baseline is not None else None,
            "patched": self.patched.value if self.patched is not None else None,
            "repetitions": self.repetitions,
            "compare_output": self.compare_output,
        }


@dataclass(frozen=True, slots=True)
class BehaviorExecution:
    """Normalized, bounded evidence from one exact-argv execution."""

    command: tuple[str, ...]
    returncode: int | None
    duration_seconds: float = 0.0
    timed_out: bool = False
    output: str | bytes | None = None
    detail: str = ""
    invalid: bool = False

    @property
    def status(self) -> BehaviorExecutionStatus:
        if self.timed_out:
            return BehaviorExecutionStatus.TIMEOUT
        if self.invalid or self.returncode is None:
            return BehaviorExecutionStatus.INVALID
        return (
            BehaviorExecutionStatus.PASS if self.returncode == 0 else BehaviorExecutionStatus.FAIL
        )

    @property
    def output_sha256(self) -> str | None:
        if self.output is None:
            return None
        payload = self.output if isinstance(self.output, bytes) else self.output.encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @property
    def output_bytes(self) -> int:
        if self.output is None:
            return 0
        payload = self.output if isinstance(self.output, bytes) else self.output.encode("utf-8")
        return len(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": redact_argv(self.command),
            "status": self.status.value,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "timed_out": self.timed_out,
            "output_sha256": self.output_sha256,
            "output_bytes": self.output_bytes,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class DeltaProofResult:
    """Evidence and causal verdict for one behavior contract."""

    contract: BehaviorContract
    verdict: DeltaProofVerdict
    baseline_status: BehaviorExecutionStatus
    patched_status: BehaviorExecutionStatus
    baseline_runs: tuple[BehaviorExecution, ...]
    patched_runs: tuple[BehaviorExecution, ...]
    reasons: tuple[str, ...] = ()
    schema_version: int = 1

    @property
    def causally_proven(self) -> bool:
        return self.verdict in {
            DeltaProofVerdict.CAUSAL_DELTA_CONFIRMED,
            DeltaProofVerdict.BEHAVIOR_EQUIVALENCE_CONFIRMED,
        }

    @property
    def flaky(self) -> bool:
        return self.verdict is DeltaProofVerdict.FLAKY

    @property
    def timed_out(self) -> bool:
        return self.verdict is DeltaProofVerdict.TIMEOUT

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract": self.contract.to_dict(),
            "verdict": self.verdict.value,
            "causally_proven": self.causally_proven,
            "baseline_status": self.baseline_status.value,
            "patched_status": self.patched_status.value,
            "baseline_runs": [run.to_dict() for run in self.baseline_runs],
            "patched_runs": [run.to_dict() for run in self.patched_runs],
            "reasons": list(self.reasons),
        }


class DeltaProofEngine:
    """Execute one behavior contract against independent baseline and patch states."""

    def __init__(
        self,
        baseline_executor: BehaviorExecutor,
        patched_executor: BehaviorExecutor,
        *,
        max_repetitions: int = 10,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_repetitions < 1:
            raise ValueError("max_repetitions must be at least 1")
        self.baseline_executor = baseline_executor
        self.patched_executor = patched_executor
        self.max_repetitions = max_repetitions
        self.clock = clock

    def prove(
        self,
        contract: BehaviorContract,
        *,
        timeout_seconds: float = 60.0,
        repetitions: int | None = None,
    ) -> DeltaProofResult:
        """Run exact argv on both states and evaluate only declared expectations."""

        if timeout_seconds <= 0:
            raise ValueError("delta proof timeout must be greater than zero")
        run_count = contract.repetitions if repetitions is None else repetitions
        if run_count < 1:
            raise ValueError("delta proof repetitions must be at least 1")
        if run_count > self.max_repetitions:
            raise ValueError("delta proof repetitions exceed the configured bound")

        baseline_runs = self._execute_many(
            self.baseline_executor,
            contract.command,
            timeout_seconds,
            run_count,
        )
        patched_runs = self._execute_many(
            self.patched_executor,
            contract.command,
            timeout_seconds,
            run_count,
        )
        baseline_status = baseline_runs[0].status
        patched_status = patched_runs[0].status
        reasons: list[str] = []

        all_runs = (*baseline_runs, *patched_runs)
        if any(run.status is BehaviorExecutionStatus.TIMEOUT for run in all_runs):
            reasons.append("at least one behavior-contract execution timed out")
            return self._result(
                contract,
                DeltaProofVerdict.TIMEOUT,
                baseline_runs,
                patched_runs,
                reasons,
            )
        if any(run.status is BehaviorExecutionStatus.INVALID for run in all_runs):
            reasons.append("at least one executor returned invalid or mismatched evidence")
            return self._result(
                contract,
                DeltaProofVerdict.INVALID,
                baseline_runs,
                patched_runs,
                reasons,
            )
        if self._is_flaky(baseline_runs, compare_output=contract.compare_output):
            reasons.append("baseline behavior was not stable across repetitions")
        if self._is_flaky(patched_runs, compare_output=contract.compare_output):
            reasons.append("patched behavior was not stable across repetitions")
        if reasons:
            return self._result(
                contract,
                DeltaProofVerdict.FLAKY,
                baseline_runs,
                patched_runs,
                reasons,
            )

        baseline_expectation = contract.baseline
        patched_expectation = contract.patched
        assert baseline_expectation is not None
        assert patched_expectation is not None
        expected_baseline = BehaviorExecutionStatus(baseline_expectation.value)
        expected_patched = BehaviorExecutionStatus(patched_expectation.value)
        if baseline_status is not expected_baseline:
            reasons.append(
                f"baseline was {baseline_status.value}; expected {expected_baseline.value}"
            )
        if patched_status is not expected_patched:
            reasons.append(
                f"patched state was {patched_status.value}; expected {expected_patched.value}"
            )
        if reasons:
            verdict = (
                DeltaProofVerdict.REGRESSION_DETECTED
                if baseline_status is BehaviorExecutionStatus.PASS
                and patched_status is BehaviorExecutionStatus.FAIL
                else DeltaProofVerdict.DELTA_NOT_CONFIRMED
            )
            return self._result(
                contract,
                verdict,
                baseline_runs,
                patched_runs,
                reasons,
            )

        if contract.compare_output:
            baseline_digest = baseline_runs[0].output_sha256
            patched_digest = patched_runs[0].output_sha256
            if baseline_digest is None or patched_digest is None:
                reasons.append("output comparison requested but an executor supplied no output")
                return self._result(
                    contract,
                    DeltaProofVerdict.INVALID,
                    baseline_runs,
                    patched_runs,
                    reasons,
                )
            if baseline_digest != patched_digest:
                reasons.append("refactor changed the declared observable output")
                return self._result(
                    contract,
                    DeltaProofVerdict.REGRESSION_DETECTED,
                    baseline_runs,
                    patched_runs,
                    reasons,
                )

        verdict = (
            DeltaProofVerdict.BEHAVIOR_EQUIVALENCE_CONFIRMED
            if contract.expectation is BehaviorExpectation.REFACTOR
            else DeltaProofVerdict.CAUSAL_DELTA_CONFIRMED
        )
        return self._result(
            contract,
            verdict,
            baseline_runs,
            patched_runs,
            reasons,
        )

    def run(
        self,
        contract: BehaviorContract,
        *,
        timeout_seconds: float = 60.0,
        repetitions: int | None = None,
    ) -> DeltaProofResult:
        """Alias for :meth:`prove` for orchestration code."""

        return self.prove(
            contract,
            timeout_seconds=timeout_seconds,
            repetitions=repetitions,
        )

    def _execute_many(
        self,
        executor: BehaviorExecutor,
        command: tuple[str, ...],
        timeout_seconds: float,
        repetitions: int,
    ) -> tuple[BehaviorExecution, ...]:
        return tuple(self._execute(executor, command, timeout_seconds) for _ in range(repetitions))

    def _execute(
        self,
        executor: BehaviorExecutor,
        command: tuple[str, ...],
        timeout_seconds: float,
    ) -> BehaviorExecution:
        started = self.clock()
        try:
            raw = executor(command, timeout_seconds)
        except TimeoutError as error:
            return BehaviorExecution(
                command=command,
                returncode=None,
                duration_seconds=max(0.0, self.clock() - started),
                timed_out=True,
                detail=f"executor timeout: {error}",
            )
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return BehaviorExecution(
                command=command,
                returncode=None,
                duration_seconds=max(0.0, self.clock() - started),
                invalid=True,
                detail=f"executor error: {type(error).__name__}: {error}",
            )
        elapsed = max(0.0, self.clock() - started)
        try:
            normalized = self._normalize_execution(raw, command, elapsed)
        except (OverflowError, TypeError, ValueError) as error:
            return BehaviorExecution(
                command=command,
                returncode=None,
                duration_seconds=elapsed,
                invalid=True,
                detail=f"invalid executor result: {type(error).__name__}: {error}",
            )
        if normalized.command != command:
            return BehaviorExecution(
                command=normalized.command,
                returncode=None,
                duration_seconds=elapsed,
                invalid=True,
                detail="executor result command does not match the behavior contract argv",
            )
        effective_duration = max(elapsed, normalized.duration_seconds)
        if effective_duration > timeout_seconds and not normalized.timed_out:
            return BehaviorExecution(
                command=command,
                returncode=None,
                duration_seconds=effective_duration,
                timed_out=True,
                output=normalized.output,
                detail="executor exceeded the declared timeout",
            )
        return normalized

    @staticmethod
    def _normalize_execution(
        raw: Any,
        command: tuple[str, ...],
        elapsed: float,
    ) -> BehaviorExecution:
        if isinstance(raw, BehaviorExecution):
            return BehaviorExecution(
                command=tuple(raw.command),
                returncode=raw.returncode,
                duration_seconds=raw.duration_seconds or elapsed,
                timed_out=raw.timed_out,
                output=raw.output,
                detail=raw.detail,
                invalid=raw.invalid,
            )
        if isinstance(raw, bool):
            return BehaviorExecution(command, 0 if raw else 1, elapsed)
        if isinstance(raw, int):
            return BehaviorExecution(command, raw, elapsed)
        if isinstance(raw, Mapping):
            advertised = raw.get("command", raw.get("argv", command))
            output = raw.get("output", raw.get("observation", raw.get("stdout")))
            if output is not None and not isinstance(output, (str, bytes)):
                return BehaviorExecution(
                    command=tuple(advertised),
                    returncode=None,
                    duration_seconds=elapsed,
                    invalid=True,
                    detail="executor output must be text or bytes",
                )
            return BehaviorExecution(
                command=tuple(advertised),
                returncode=_optional_int(raw.get("returncode")),
                duration_seconds=float(raw.get("duration_seconds", elapsed)),
                timed_out=bool(raw.get("timed_out", False)),
                output=output,
                detail=str(raw.get("detail", "")),
                invalid=bool(raw.get("invalid", False)),
            )

        advertised = getattr(raw, "command", getattr(raw, "argv", command))
        returncode = getattr(raw, "returncode", None)
        timed_out = bool(getattr(raw, "timed_out", False))
        output = getattr(raw, "output", getattr(raw, "stdout", None))
        if output is not None and not isinstance(output, (str, bytes)):
            output = None
        return BehaviorExecution(
            command=tuple(advertised),
            returncode=_optional_int(returncode),
            duration_seconds=float(getattr(raw, "duration_seconds", elapsed)),
            timed_out=timed_out,
            output=output,
            detail=str(getattr(raw, "detail", "")),
            invalid=returncode is None and not timed_out,
        )

    @staticmethod
    def _is_flaky(
        runs: tuple[BehaviorExecution, ...],
        *,
        compare_output: bool,
    ) -> bool:
        if len({run.status for run in runs}) > 1:
            return True
        if not compare_output:
            return False
        return len({run.output_sha256 for run in runs}) > 1

    @staticmethod
    def _result(
        contract: BehaviorContract,
        verdict: DeltaProofVerdict,
        baseline_runs: tuple[BehaviorExecution, ...],
        patched_runs: tuple[BehaviorExecution, ...],
        reasons: list[str],
    ) -> DeltaProofResult:
        return DeltaProofResult(
            contract=contract,
            verdict=verdict,
            baseline_status=baseline_runs[0].status,
            patched_status=patched_runs[0].status,
            baseline_runs=baseline_runs,
            patched_runs=patched_runs,
            reasons=tuple(dict.fromkeys(reasons)),
        )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _coerce_expected_behavior(value: ExpectedBehavior | str) -> ExpectedBehavior:
    if isinstance(value, ExpectedBehavior):
        return value
    return ExpectedBehavior(str(value).upper())


# Short alias for callers that prefer result-oriented naming.
DeltaExecutionResult = BehaviorExecution


__all__ = [
    "BehaviorContract",
    "BehaviorExecution",
    "BehaviorExecutionStatus",
    "BehaviorExpectation",
    "DeltaExecutionResult",
    "DeltaProofEngine",
    "DeltaProofResult",
    "DeltaProofVerdict",
    "ExpectedBehavior",
]

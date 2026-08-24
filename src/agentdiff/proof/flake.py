"""Bounded deterministic flake classification beside authoritative proof.

The firewall samples one exact check repeatedly and records digest-only
evidence.  It does not alter :class:`ProofEngine`, start repair, or quarantine
tests; its result exposes narrow eligibility flags that reject noisy evidence.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from ._flake_models import (
    FlakeCheck,
    FlakeClassification,
    FlakeExecution,
    FlakeFirewallResult,
    FlakeSample,
    FlakeSampleStatus,
    InfrastructureFailure,
    QuarantineCandidate,
    _canonical_sha256,
)

FlakeCheckRunner = Callable[[tuple[str, ...], float], Any]


class FlakeFirewall:
    """Run exact-argv samples within strict count and duration budgets."""

    def __init__(
        self,
        runner: FlakeCheckRunner,
        *,
        max_samples: int = 10,
        max_duration_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(max_samples, bool) or not isinstance(max_samples, int) or max_samples < 2:
            raise ValueError("max_samples must be at least 2")
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than zero")
        self.runner = runner
        self.max_samples = max_samples
        self.max_duration_seconds = max_duration_seconds
        self.clock = clock

    def assess(
        self,
        check: FlakeCheck,
        *,
        timeout_seconds: float = 60.0,
    ) -> FlakeFirewallResult:
        """Sample one check repeatedly without granting proof or repair authority."""

        if timeout_seconds <= 0:
            raise ValueError("flake sample timeout must be greater than zero")
        started = self.clock()
        samples: list[FlakeSample] = []
        reasons: list[str] = []
        planned = min(check.repetitions, self.max_samples)

        if check.repetitions > self.max_samples:
            reasons.append("flake sample-count budget reached")
        for index in range(1, planned + 1):
            elapsed = max(0.0, self.clock() - started)
            if elapsed >= self.max_duration_seconds:
                reasons.append("flake sampling duration budget reached")
                break
            samples.append(
                self._run_sample(
                    check,
                    index,
                    timeout_seconds=min(
                        timeout_seconds,
                        self.max_duration_seconds - elapsed,
                    ),
                )
            )

        complete = len(samples) == check.repetitions
        classification, classification_reasons = _classify(
            tuple(samples),
            complete=complete,
            compare_output=check.compare_output,
        )
        reasons.extend(classification_reasons)
        candidate = (
            _quarantine_candidate(check, tuple(samples))
            if classification is FlakeClassification.FLAKY
            else None
        )
        return FlakeFirewallResult(
            check=check,
            classification=classification,
            samples=tuple(samples),
            requested_samples=check.repetitions,
            complete=complete,
            quarantine_candidate=candidate,
            reasons=tuple(dict.fromkeys(reasons)),
        )

    def run(
        self,
        check: FlakeCheck,
        *,
        timeout_seconds: float = 60.0,
    ) -> FlakeFirewallResult:
        """Alias for :meth:`assess` for orchestration code."""

        return self.assess(check, timeout_seconds=timeout_seconds)

    def _run_sample(
        self,
        check: FlakeCheck,
        index: int,
        *,
        timeout_seconds: float,
    ) -> FlakeSample:
        started = self.clock()
        try:
            raw = self.runner(check.command, timeout_seconds)
        except TimeoutError as error:
            execution = FlakeExecution(
                returncode=None,
                command=check.command,
                timed_out=True,
                detail=f"check timed out: {error}",
            )
        except (InfrastructureFailure, OSError) as error:
            execution = FlakeExecution(
                returncode=None,
                command=check.command,
                infrastructure_failure=True,
                detail=f"infrastructure failure: {type(error).__name__}: {error}",
            )
        except (RuntimeError, TypeError, ValueError) as error:
            execution = FlakeExecution(
                returncode=None,
                command=check.command,
                valid=False,
                detail=f"invalid check execution: {type(error).__name__}: {error}",
            )
        else:
            elapsed = max(0.0, self.clock() - started)
            try:
                execution = _normalize_execution(raw, check.command, elapsed)
            except (OverflowError, TypeError, ValueError) as error:
                execution = FlakeExecution(
                    returncode=None,
                    command=check.command,
                    duration_seconds=elapsed,
                    valid=False,
                    detail=f"invalid check result: {type(error).__name__}: {error}",
                )

        elapsed = max(0.0, self.clock() - started)
        effective_duration = max(elapsed, execution.duration_seconds)
        if execution.command != check.command:
            execution = FlakeExecution(
                returncode=None,
                command=check.command,
                duration_seconds=effective_duration,
                output_sha256=execution.output_sha256,
                output_bytes=execution.output_bytes,
                valid=False,
                detail="check result command does not match configured exact argv",
            )
        elif effective_duration > timeout_seconds and not execution.timed_out:
            execution = FlakeExecution(
                returncode=None,
                command=check.command,
                duration_seconds=effective_duration,
                output_sha256=execution.output_sha256,
                output_bytes=execution.output_bytes,
                timed_out=True,
                detail="check execution exceeded the sample timeout",
            )

        return FlakeSample(
            index=index,
            command=check.command,
            status=execution.status,
            returncode=execution.returncode,
            duration_seconds=effective_duration,
            output_sha256=execution.output_sha256,
            output_bytes=execution.output_bytes or 0,
            detail=execution.detail,
        )


def _normalize_execution(
    raw: Any,
    command: tuple[str, ...],
    elapsed: float,
) -> FlakeExecution:
    if isinstance(raw, FlakeExecution):
        return FlakeExecution(
            returncode=raw.returncode,
            command=raw.command or command,
            duration_seconds=raw.duration_seconds or elapsed,
            output=raw.output,
            output_sha256=raw.output_sha256,
            output_bytes=raw.output_bytes,
            infrastructure_failure=raw.infrastructure_failure,
            timed_out=raw.timed_out,
            valid=raw.valid,
            detail=raw.detail,
        )
    if isinstance(raw, bool):
        return FlakeExecution(0 if raw else 1, command=command, duration_seconds=elapsed)
    if isinstance(raw, int):
        return FlakeExecution(raw, command=command, duration_seconds=elapsed)
    if isinstance(raw, Mapping):
        status = _mapping_status(raw)
        returncode = raw.get("returncode")
        if returncode is None and status is FlakeSampleStatus.PASS:
            returncode = 0
        elif returncode is None and status is FlakeSampleStatus.FAIL:
            returncode = 1
        advertised = raw.get("command", raw.get("argv", command))
        return FlakeExecution(
            returncode=_optional_int(returncode),
            command=tuple(advertised),
            duration_seconds=float(raw.get("duration_seconds", elapsed)),
            output=raw.get("output", raw.get("stdout")),
            output_sha256=raw.get("output_sha256"),
            output_bytes=raw.get("output_bytes"),
            infrastructure_failure=status is FlakeSampleStatus.INFRASTRUCTURE_FAILURE,
            timed_out=status is FlakeSampleStatus.TIMEOUT,
            valid=status is not FlakeSampleStatus.INVALID,
            detail=str(raw.get("detail", "")),
        )

    advertised = getattr(raw, "command", getattr(raw, "argv", command))
    status = _object_status(raw)
    returncode = getattr(raw, "returncode", None)
    if returncode is None and status is FlakeSampleStatus.PASS:
        returncode = 0
    elif returncode is None and status is FlakeSampleStatus.FAIL:
        returncode = 1
    return FlakeExecution(
        returncode=_optional_int(returncode),
        command=tuple(advertised),
        duration_seconds=float(getattr(raw, "duration_seconds", elapsed)),
        output=getattr(raw, "output", getattr(raw, "stdout", None)),
        output_sha256=getattr(raw, "output_sha256", None),
        output_bytes=getattr(raw, "output_bytes", None),
        infrastructure_failure=status is FlakeSampleStatus.INFRASTRUCTURE_FAILURE,
        timed_out=status is FlakeSampleStatus.TIMEOUT,
        valid=status is not FlakeSampleStatus.INVALID,
        detail=str(getattr(raw, "detail", "")),
    )


def _mapping_status(raw: Mapping[Any, Any]) -> FlakeSampleStatus:
    if bool(raw.get("timed_out", False)):
        return FlakeSampleStatus.TIMEOUT
    if bool(raw.get("infrastructure_failure", raw.get("infrastructure_error", False))):
        return FlakeSampleStatus.INFRASTRUCTURE_FAILURE
    if not bool(raw.get("valid", True)):
        return FlakeSampleStatus.INVALID
    if "status" in raw:
        return _coerce_sample_status(raw["status"])
    if "passed" in raw:
        return FlakeSampleStatus.PASS if bool(raw["passed"]) else FlakeSampleStatus.FAIL
    if "returncode" in raw:
        return FlakeSampleStatus.PASS if int(raw["returncode"]) == 0 else FlakeSampleStatus.FAIL
    raise ValueError("mapping has no explicit check status")


def _object_status(raw: Any) -> FlakeSampleStatus:
    if bool(getattr(raw, "timed_out", False)):
        return FlakeSampleStatus.TIMEOUT
    if bool(getattr(raw, "infrastructure_failure", getattr(raw, "infrastructure_error", False))):
        return FlakeSampleStatus.INFRASTRUCTURE_FAILURE
    if not bool(getattr(raw, "valid", True)):
        return FlakeSampleStatus.INVALID
    if hasattr(raw, "status"):
        return _coerce_sample_status(raw.status)
    if hasattr(raw, "passed"):
        return FlakeSampleStatus.PASS if bool(raw.passed) else FlakeSampleStatus.FAIL
    if hasattr(raw, "returncode"):
        return FlakeSampleStatus.PASS if int(raw.returncode) == 0 else FlakeSampleStatus.FAIL
    raise TypeError("unsupported check execution result")


def _coerce_sample_status(value: Any) -> FlakeSampleStatus:
    if isinstance(value, FlakeSampleStatus):
        return value
    return FlakeSampleStatus(str(value).upper())


def _classify(
    samples: tuple[FlakeSample, ...],
    *,
    complete: bool,
    compare_output: bool,
) -> tuple[FlakeClassification, tuple[str, ...]]:
    pass_count = sum(sample.status is FlakeSampleStatus.PASS for sample in samples)
    fail_count = sum(sample.status is FlakeSampleStatus.FAIL for sample in samples)
    inconclusive_count = len(samples) - pass_count - fail_count

    if pass_count and fail_count:
        return (
            FlakeClassification.FLAKY,
            ("repeated samples produced both passing and failing results",),
        )
    if compare_output and samples and not inconclusive_count:
        output_digests = {sample.output_sha256 for sample in samples}
        if None in output_digests:
            return (
                FlakeClassification.INCONCLUSIVE,
                ("output comparison requested but at least one sample supplied no digest",),
            )
        if len(output_digests) > 1:
            return (
                FlakeClassification.FLAKY,
                ("repeated samples produced different declared observable output",),
            )
    if not complete:
        return (
            FlakeClassification.INCONCLUSIVE,
            ("requested repeated sampling did not complete",),
        )
    if inconclusive_count:
        return (
            FlakeClassification.INCONCLUSIVE,
            ("infrastructure, timeout, or invalid samples prevent a stability claim",),
        )
    if samples and pass_count == len(samples):
        return FlakeClassification.STABLE_PASS, ()
    if samples and fail_count == len(samples):
        return FlakeClassification.STABLE_FAIL, ()
    return FlakeClassification.INCONCLUSIVE, ("no conclusive repeated samples were collected",)


def _quarantine_candidate(
    check: FlakeCheck,
    samples: tuple[FlakeSample, ...],
) -> QuarantineCandidate:
    pass_count = sum(sample.status is FlakeSampleStatus.PASS for sample in samples)
    fail_count = sum(sample.status is FlakeSampleStatus.FAIL for sample in samples)
    sample_digests = tuple(sample.digest for sample in samples)
    fingerprint = _canonical_sha256(
        {
            "check_id": check.id,
            "command_digest": check.command_digest,
            "sample_digests": list(sample_digests),
        }
    )
    return QuarantineCandidate(
        check_id=check.id,
        fingerprint=fingerprint,
        pass_count=pass_count,
        fail_count=fail_count,
        sample_digests=sample_digests,
        reason="deterministic repeated sampling observed unstable behavior",
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


FlakeFirewallEngine = FlakeFirewall


__all__ = [
    "FlakeCheck",
    "FlakeClassification",
    "FlakeExecution",
    "FlakeFirewall",
    "FlakeFirewallEngine",
    "FlakeFirewallResult",
    "FlakeSample",
    "FlakeSampleStatus",
    "InfrastructureFailure",
    "QuarantineCandidate",
]

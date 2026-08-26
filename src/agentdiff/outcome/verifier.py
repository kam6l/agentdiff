"""Deterministic, pluggable post-merge outcome verification.

Checks provide explicit results and evidence.  The verifier aggregates those
facts without model judgment and never executes a production rollback.  A
regression can optionally recommend preparing a revert for human review, but
that recommendation is intentionally distinct from applying one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from agentdiff.delivery import SealedDeliveryIdentity

OutcomeCheckRunner = Callable[["PostMergeContext", float], Any]


class OutcomeState(str, Enum):
    """Final post-merge state."""

    HEALTHY = "HEALTHY"
    REGRESSION_DETECTED = "REGRESSION_DETECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class OutcomeCheckStatus(str, Enum):
    """Explicit status supplied by or derived from one check plugin."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class OutcomeEvidence:
    """Bounded reference or digest retained from a post-merge check."""

    source: str
    summary: str = ""
    digest: str = ""
    reference: str = ""
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("outcome evidence source must not be empty")
        for field_name in ("summary", "digest", "reference"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"outcome evidence {field_name} must be text")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "summary": self.summary,
            "digest": self.digest,
            "reference": self.reference,
        }


@dataclass(frozen=True, slots=True)
class PostMergeContext:
    """Exact merged subject against which outcome evidence is collected."""

    merged_commit_sha: str
    delivery_identity: SealedDeliveryIdentity
    pull_request_number: int | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_identity, SealedDeliveryIdentity):
            raise TypeError("delivery_identity must be a SealedDeliveryIdentity")
        if (
            not isinstance(self.merged_commit_sha, str)
            or not self.merged_commit_sha
            or self.merged_commit_sha != self.merged_commit_sha.strip()
        ):
            raise ValueError("merged_commit_sha must be a non-empty exact identity")
        if self.pull_request_number is not None and (
            isinstance(self.pull_request_number, bool)
            or not isinstance(self.pull_request_number, int)
            or self.pull_request_number < 1
        ):
            raise ValueError("pull_request_number must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "merged_commit_sha": self.merged_commit_sha,
            "delivery_identity": self.delivery_identity.to_dict(),
            "pull_request_number": self.pull_request_number,
        }


@dataclass(frozen=True, slots=True)
class OutcomeCheckResult:
    """Normalized result and preserved evidence from one configured check."""

    check_id: str
    kind: str
    status: OutcomeCheckStatus
    evidence: tuple[OutcomeEvidence, ...] = ()
    duration_seconds: float = 0.0
    detail: str = ""
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.check_id, str) or not self.check_id.strip():
            raise ValueError("outcome check id must not be empty")
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("outcome check kind must not be empty")
        status = (
            self.status
            if isinstance(self.status, OutcomeCheckStatus)
            else OutcomeCheckStatus(str(self.status).upper())
        )
        evidence = tuple(self.evidence)
        if any(not isinstance(item, OutcomeEvidence) for item in evidence):
            raise TypeError("outcome check evidence must contain OutcomeEvidence values")
        if self.duration_seconds < 0:
            raise ValueError("outcome check duration must not be negative")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "evidence", evidence)

    @property
    def passed(self) -> bool:
        return self.status is OutcomeCheckStatus.PASS

    @property
    def failed(self) -> bool:
        return self.status is OutcomeCheckStatus.FAIL

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "check_id": self.check_id,
            "kind": self.kind,
            "status": self.status.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "duration_seconds": self.duration_seconds,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class OutcomeCheck:
    """One named post-merge plugin and its deterministic runner."""

    check_id: str
    runner: OutcomeCheckRunner
    kind: str = "custom"

    def __post_init__(self) -> None:
        if not isinstance(self.check_id, str) or not self.check_id.strip():
            raise ValueError("outcome check id must not be empty")
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("outcome check kind must not be empty")
        if not callable(self.runner):
            raise TypeError("outcome check runner must be callable")


@dataclass(frozen=True, slots=True)
class PostMergeOutcome:
    """Aggregated outcome with evidence and deliberately limited authority."""

    context: PostMergeContext
    state: OutcomeState
    checks: tuple[OutcomeCheckResult, ...]
    complete: bool
    reasons: tuple[str, ...] = ()
    prepare_revert: bool = False
    schema_version: int = 1

    @property
    def maintenance_complete(self) -> bool:
        return self.state is OutcomeState.HEALTHY

    @property
    def stop_remaining_campaign(self) -> bool:
        return self.state is OutcomeState.REGRESSION_DETECTED

    @property
    def notify_human(self) -> bool:
        return self.state is not OutcomeState.HEALTHY

    @property
    def automatic_production_rollback(self) -> bool:
        """Outcome verification never authorizes an automatic rollback."""

        return False

    @property
    def recommended_actions(self) -> tuple[str, ...]:
        if self.state is OutcomeState.HEALTHY:
            return ("MAINTENANCE_COMPLETE", "PRESERVE_EVIDENCE")
        if self.state is OutcomeState.REGRESSION_DETECTED:
            actions = ["STOP_REMAINING_CAMPAIGN", "NOTIFY_HUMAN", "PRESERVE_EVIDENCE"]
            if self.prepare_revert:
                actions.append("PREPARE_REVERT_FOR_REVIEW")
            return tuple(actions)
        return ("REQUIRE_HUMAN_REVIEW", "PRESERVE_EVIDENCE")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "context": self.context.to_dict(),
            "state": self.state.value,
            "checks": [check.to_dict() for check in self.checks],
            "complete": self.complete,
            "maintenance_complete": self.maintenance_complete,
            "stop_remaining_campaign": self.stop_remaining_campaign,
            "notify_human": self.notify_human,
            "prepare_revert": self.prepare_revert,
            "automatic_production_rollback": self.automatic_production_rollback,
            "recommended_actions": list(self.recommended_actions),
            "reasons": list(self.reasons),
        }


class PostMergeOutcomeEvaluator:
    """Aggregate already-collected check results without invoking plugins."""

    def evaluate(
        self,
        context: PostMergeContext,
        results: Iterable[OutcomeCheckResult],
        *,
        complete: bool = True,
        reasons: Iterable[str] = (),
        prepare_revert: bool = False,
    ) -> PostMergeOutcome:
        checks = tuple(results)
        if len({check.check_id for check in checks}) != len(checks):
            raise ValueError("outcome check ids must be unique")
        result_reasons = list(reasons)

        if any(check.status is OutcomeCheckStatus.FAIL for check in checks):
            state = OutcomeState.REGRESSION_DETECTED
            result_reasons.append("one or more post-merge checks reported regression")
        elif (
            not checks
            or not complete
            or any(check.status is not OutcomeCheckStatus.PASS for check in checks)
        ):
            state = OutcomeState.INCONCLUSIVE
            result_reasons.append("post-merge evidence is incomplete or unavailable")
        else:
            state = OutcomeState.HEALTHY

        return PostMergeOutcome(
            context=context,
            state=state,
            checks=checks,
            complete=complete,
            reasons=tuple(dict.fromkeys(result_reasons)),
            prepare_revert=prepare_revert and state is OutcomeState.REGRESSION_DETECTED,
        )


class PostMergeVerifier:
    """Run bounded check plugins and aggregate their explicit results."""

    def __init__(
        self,
        checks: Iterable[OutcomeCheck],
        *,
        max_checks: int = 16,
        max_duration_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        configured = tuple(checks)
        if max_checks < 1:
            raise ValueError("max_checks must be at least 1")
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than zero")
        if len({check.check_id for check in configured}) != len(configured):
            raise ValueError("outcome check ids must be unique")
        self.checks = configured
        self.max_checks = max_checks
        self.max_duration_seconds = max_duration_seconds
        self.clock = clock

    def verify(
        self,
        context: PostMergeContext,
        *,
        timeout_seconds: float = 60.0,
        prepare_revert_on_regression: bool = False,
    ) -> PostMergeOutcome:
        """Collect check evidence without triggering deployment or rollback actions."""

        if timeout_seconds <= 0:
            raise ValueError("outcome check timeout must be greater than zero")
        started = self.clock()
        results: list[OutcomeCheckResult] = []
        reasons: list[str] = []
        complete = True

        for index, check in enumerate(self.checks):
            elapsed = max(0.0, self.clock() - started)
            if index >= self.max_checks:
                complete = False
                reasons.append("post-merge check-count budget reached")
                break
            if elapsed >= self.max_duration_seconds:
                complete = False
                reasons.append("post-merge duration budget reached")
                break
            results.append(
                self._run_check(
                    check,
                    context,
                    timeout_seconds=min(
                        timeout_seconds,
                        self.max_duration_seconds - elapsed,
                    ),
                )
            )

        return PostMergeOutcomeEvaluator().evaluate(
            context,
            results,
            complete=complete,
            reasons=reasons,
            prepare_revert=prepare_revert_on_regression,
        )

    def run(
        self,
        context: PostMergeContext,
        *,
        timeout_seconds: float = 60.0,
        prepare_revert_on_regression: bool = False,
    ) -> PostMergeOutcome:
        """Alias for :meth:`verify` for lifecycle orchestration."""

        return self.verify(
            context,
            timeout_seconds=timeout_seconds,
            prepare_revert_on_regression=prepare_revert_on_regression,
        )

    def _run_check(
        self,
        check: OutcomeCheck,
        context: PostMergeContext,
        *,
        timeout_seconds: float,
    ) -> OutcomeCheckResult:
        started = self.clock()
        try:
            raw = check.runner(context, timeout_seconds)
        except TimeoutError as error:
            return OutcomeCheckResult(
                check_id=check.check_id,
                kind=check.kind,
                status=OutcomeCheckStatus.TIMEOUT,
                duration_seconds=max(0.0, self.clock() - started),
                detail=f"post-merge check timed out: {error}",
            )
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return OutcomeCheckResult(
                check_id=check.check_id,
                kind=check.kind,
                status=OutcomeCheckStatus.INVALID,
                duration_seconds=max(0.0, self.clock() - started),
                detail=f"post-merge check failed: {type(error).__name__}: {error}",
            )
        elapsed = max(0.0, self.clock() - started)
        try:
            normalized = _normalize_result(raw, check, elapsed)
        except (OverflowError, TypeError, ValueError) as error:
            return OutcomeCheckResult(
                check_id=check.check_id,
                kind=check.kind,
                status=OutcomeCheckStatus.INVALID,
                duration_seconds=elapsed,
                detail=f"invalid post-merge check result: {error}",
            )
        if normalized.check_id != check.check_id:
            return OutcomeCheckResult(
                check_id=check.check_id,
                kind=check.kind,
                status=OutcomeCheckStatus.INVALID,
                evidence=normalized.evidence,
                duration_seconds=max(elapsed, normalized.duration_seconds),
                detail="post-merge check result id does not match configured check",
            )
        effective_duration = max(elapsed, normalized.duration_seconds)
        if effective_duration > timeout_seconds or normalized.status is OutcomeCheckStatus.TIMEOUT:
            return OutcomeCheckResult(
                check_id=check.check_id,
                kind=check.kind,
                status=OutcomeCheckStatus.TIMEOUT,
                evidence=normalized.evidence,
                duration_seconds=effective_duration,
                detail=normalized.detail or "post-merge check exceeded its timeout",
            )
        return OutcomeCheckResult(
            check_id=check.check_id,
            kind=check.kind,
            status=normalized.status,
            evidence=normalized.evidence,
            duration_seconds=effective_duration,
            detail=normalized.detail,
        )


def _normalize_result(
    raw: Any,
    check: OutcomeCheck,
    elapsed: float,
) -> OutcomeCheckResult:
    if isinstance(raw, OutcomeCheckResult):
        return raw
    if isinstance(raw, bool):
        return OutcomeCheckResult(
            check.check_id,
            check.kind,
            OutcomeCheckStatus.PASS if raw else OutcomeCheckStatus.FAIL,
            duration_seconds=elapsed,
        )
    if isinstance(raw, int):
        return OutcomeCheckResult(
            check.check_id,
            check.kind,
            OutcomeCheckStatus.PASS if raw == 0 else OutcomeCheckStatus.FAIL,
            duration_seconds=elapsed,
        )
    if isinstance(raw, Mapping):
        status = _mapping_status(raw)
        return OutcomeCheckResult(
            check_id=str(raw.get("check_id", check.check_id)),
            kind=str(raw.get("kind", check.kind)),
            status=status,
            evidence=_normalize_evidence(raw.get("evidence"), check.check_id),
            duration_seconds=float(raw.get("duration_seconds", elapsed)),
            detail=str(raw.get("detail", "")),
        )

    if hasattr(raw, "status"):
        status = _coerce_status(raw.status)
    elif hasattr(raw, "passed"):
        status = OutcomeCheckStatus.PASS if bool(raw.passed) else OutcomeCheckStatus.FAIL
    elif hasattr(raw, "healthy"):
        status = OutcomeCheckStatus.PASS if bool(raw.healthy) else OutcomeCheckStatus.FAIL
    elif hasattr(raw, "returncode"):
        status = OutcomeCheckStatus.PASS if int(raw.returncode) == 0 else OutcomeCheckStatus.FAIL
    else:
        raise TypeError("unsupported post-merge check result")
    return OutcomeCheckResult(
        check_id=str(getattr(raw, "check_id", check.check_id)),
        kind=str(getattr(raw, "kind", check.kind)),
        status=status,
        evidence=_normalize_evidence(getattr(raw, "evidence", None), check.check_id),
        duration_seconds=float(getattr(raw, "duration_seconds", elapsed)),
        detail=str(getattr(raw, "detail", "")),
    )


def _mapping_status(raw: Mapping[Any, Any]) -> OutcomeCheckStatus:
    if bool(raw.get("timed_out", False)):
        return OutcomeCheckStatus.TIMEOUT
    if bool(raw.get("unavailable", False)):
        return OutcomeCheckStatus.UNAVAILABLE
    if not bool(raw.get("valid", True)):
        return OutcomeCheckStatus.INVALID
    if "status" in raw:
        return _coerce_status(raw["status"])
    if "passed" in raw:
        return OutcomeCheckStatus.PASS if bool(raw["passed"]) else OutcomeCheckStatus.FAIL
    if "healthy" in raw:
        return OutcomeCheckStatus.PASS if bool(raw["healthy"]) else OutcomeCheckStatus.FAIL
    if "returncode" in raw:
        return OutcomeCheckStatus.PASS if int(raw["returncode"]) == 0 else OutcomeCheckStatus.FAIL
    raise ValueError("mapping has no explicit post-merge check status")


def _coerce_status(value: Any) -> OutcomeCheckStatus:
    if isinstance(value, OutcomeCheckStatus):
        return value
    return OutcomeCheckStatus(str(value).upper())


def _normalize_evidence(raw: Any, default_source: str) -> tuple[OutcomeEvidence, ...]:
    if raw is None:
        return ()
    if isinstance(raw, OutcomeEvidence):
        return (raw,)
    if isinstance(raw, str):
        return (OutcomeEvidence(source=default_source, summary=raw),)
    if isinstance(raw, Mapping):
        return (_evidence_from_mapping(raw, default_source),)
    if isinstance(raw, Iterable):
        items: list[OutcomeEvidence] = []
        for item in raw:
            if isinstance(item, OutcomeEvidence):
                items.append(item)
            elif isinstance(item, str):
                items.append(OutcomeEvidence(source=default_source, summary=item))
            elif isinstance(item, Mapping):
                items.append(_evidence_from_mapping(item, default_source))
            else:
                raise TypeError("unsupported post-merge evidence item")
        return tuple(items)
    raise TypeError("unsupported post-merge evidence")


def _evidence_from_mapping(raw: Mapping[Any, Any], default_source: str) -> OutcomeEvidence:
    return OutcomeEvidence(
        source=str(raw.get("source", default_source)),
        summary=str(raw.get("summary", raw.get("detail", ""))),
        digest=str(raw.get("digest", "")),
        reference=str(raw.get("reference", "")),
    )


# Product-language alias.
OutcomeVerifier = PostMergeVerifier


__all__ = [
    "OutcomeCheck",
    "OutcomeCheckResult",
    "OutcomeCheckStatus",
    "OutcomeEvidence",
    "OutcomeState",
    "OutcomeVerifier",
    "PostMergeContext",
    "PostMergeOutcome",
    "PostMergeOutcomeEvaluator",
    "PostMergeVerifier",
]

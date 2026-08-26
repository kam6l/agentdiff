"""Immutable evidence models for deterministic flake classification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentdiff.redaction import redact_argv


class FlakeClassification(str, Enum):
    """Aggregate stability classification for repeated samples."""

    STABLE_PASS = "STABLE_PASS"
    STABLE_FAIL = "STABLE_FAIL"
    FLAKY = "FLAKY"
    INCONCLUSIVE = "INCONCLUSIVE"


class FlakeSampleStatus(str, Enum):
    """Truthful status of one repeated check invocation."""

    PASS = "PASS"
    FAIL = "FAIL"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    TIMEOUT = "TIMEOUT"
    INVALID = "INVALID"


class InfrastructureFailure(RuntimeError):
    """Raised by a runner when the environment, not the checked code, failed."""


@dataclass(frozen=True, slots=True)
class FlakeCheck:
    """One exact command and its bounded repeated-sampling request."""

    id: str
    command: tuple[str, ...]
    repetitions: int = 3
    compare_output: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        command = tuple(self.command)
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("flake check id must not be empty")
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("flake check command must be non-empty exact argv")
        if (
            isinstance(self.repetitions, bool)
            or not isinstance(self.repetitions, int)
            or self.repetitions < 2
        ):
            raise ValueError("flake check repetitions must be at least 2")
        object.__setattr__(self, "command", command)

    @property
    def command_digest(self) -> str:
        return _canonical_sha256(list(self.command))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "command": redact_argv(self.command),
            "command_digest": self.command_digest,
            "repetitions": self.repetitions,
            "compare_output": self.compare_output,
        }


@dataclass(frozen=True, slots=True)
class FlakeExecution:
    """Runner response; raw output remains in memory and is never serialized."""

    returncode: int | None
    command: tuple[str, ...] | None = None
    duration_seconds: float = 0.0
    output: str | bytes | None = None
    output_sha256: str | None = None
    output_bytes: int | None = None
    infrastructure_failure: bool = False
    timed_out: bool = False
    valid: bool = True
    detail: str = ""

    def __post_init__(self) -> None:
        if self.returncode is not None and (
            isinstance(self.returncode, bool) or not isinstance(self.returncode, int)
        ):
            raise TypeError("flake execution returncode must be an integer or None")
        if self.command is not None:
            command = tuple(self.command)
            if not command or any(not isinstance(part, str) or not part for part in command):
                raise ValueError("flake execution command must be non-empty exact argv")
            object.__setattr__(self, "command", command)
        if self.duration_seconds < 0:
            raise ValueError("flake execution duration must not be negative")
        if self.output is not None and not isinstance(self.output, (str, bytes)):
            raise TypeError("flake execution output must be text or bytes")

        payload = _output_bytes(self.output)
        digest = self.output_sha256
        byte_count = self.output_bytes
        if payload is not None:
            computed_digest = hashlib.sha256(payload).hexdigest()
            if digest is not None and digest != computed_digest:
                raise ValueError("flake execution output digest does not match output")
            if byte_count is not None and byte_count != len(payload):
                raise ValueError("flake execution output byte count does not match output")
            digest = computed_digest
            byte_count = len(payload)
        elif digest is not None and not _is_sha256(digest):
            raise ValueError("flake execution output_sha256 must be a lowercase SHA-256 digest")
        if byte_count is not None and (
            isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0
        ):
            raise ValueError("flake execution output_bytes must be a non-negative integer")
        object.__setattr__(self, "output_sha256", digest)
        object.__setattr__(self, "output_bytes", byte_count or 0)

    @property
    def status(self) -> FlakeSampleStatus:
        if self.timed_out:
            return FlakeSampleStatus.TIMEOUT
        if self.infrastructure_failure:
            return FlakeSampleStatus.INFRASTRUCTURE_FAILURE
        if not self.valid or self.returncode is None:
            return FlakeSampleStatus.INVALID
        return FlakeSampleStatus.PASS if self.returncode == 0 else FlakeSampleStatus.FAIL


@dataclass(frozen=True, slots=True)
class FlakeSample:
    """Digest-only evidence for one invocation."""

    index: int
    command: tuple[str, ...]
    status: FlakeSampleStatus
    returncode: int | None
    duration_seconds: float
    output_sha256: str | None = None
    output_bytes: int = 0
    detail: str = ""
    schema_version: int = 1

    @property
    def digest(self) -> str:
        return _canonical_sha256(
            {
                "index": self.index,
                "command_digest": _canonical_sha256(list(self.command)),
                "status": self.status.value,
                "returncode": self.returncode,
                "output_sha256": self.output_sha256,
                "output_bytes": self.output_bytes,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "index": self.index,
            "command": redact_argv(self.command),
            "status": self.status.value,
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "output_sha256": self.output_sha256,
            "output_bytes": self.output_bytes,
            "detail": self.detail,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class QuarantineCandidate:
    """Review metadata only; this object never quarantines a check."""

    check_id: str
    fingerprint: str
    pass_count: int
    fail_count: int
    sample_digests: tuple[str, ...]
    reason: str
    schema_version: int = 1

    @property
    def automatic_quarantine(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "check_id": self.check_id,
            "fingerprint": self.fingerprint,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "sample_digests": list(self.sample_digests),
            "reason": self.reason,
            "automatic_quarantine": self.automatic_quarantine,
        }


@dataclass(frozen=True, slots=True)
class FlakeFirewallResult:
    """Stability verdict with explicit proof, repair, and quarantine boundaries."""

    check: FlakeCheck
    classification: FlakeClassification
    samples: tuple[FlakeSample, ...]
    requested_samples: int
    complete: bool
    quarantine_candidate: QuarantineCandidate | None = None
    reasons: tuple[str, ...] = ()
    schema_version: int = 1

    @property
    def pass_count(self) -> int:
        return sum(sample.status is FlakeSampleStatus.PASS for sample in self.samples)

    @property
    def fail_count(self) -> int:
        return sum(sample.status is FlakeSampleStatus.FAIL for sample in self.samples)

    @property
    def infrastructure_failure_count(self) -> int:
        return sum(
            sample.status is FlakeSampleStatus.INFRASTRUCTURE_FAILURE for sample in self.samples
        )

    @property
    def timeout_count(self) -> int:
        return sum(sample.status is FlakeSampleStatus.TIMEOUT for sample in self.samples)

    @property
    def invalid_count(self) -> int:
        return sum(sample.status is FlakeSampleStatus.INVALID for sample in self.samples)

    @property
    def inconclusive_sample_count(self) -> int:
        return self.infrastructure_failure_count + self.timeout_count + self.invalid_count

    @property
    def sample_digests(self) -> tuple[str, ...]:
        return tuple(sample.digest for sample in self.samples)

    @property
    def counts_as_proof(self) -> bool:
        return (
            self.classification is FlakeClassification.STABLE_PASS
            and self.complete
            and len(self.samples) == self.requested_samples
            and self.pass_count == self.requested_samples
        )

    @property
    def repair_eligible(self) -> bool:
        return (
            self.classification is FlakeClassification.STABLE_FAIL
            and self.complete
            and len(self.samples) == self.requested_samples
            and self.fail_count == self.requested_samples
        )

    @property
    def may_enter_repair(self) -> bool:
        return self.repair_eligible

    @property
    def automatic_quarantine(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "check": self.check.to_dict(),
            "classification": self.classification.value,
            "samples": [sample.to_dict() for sample in self.samples],
            "requested_samples": self.requested_samples,
            "complete": self.complete,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "infrastructure_failure_count": self.infrastructure_failure_count,
            "timeout_count": self.timeout_count,
            "invalid_count": self.invalid_count,
            "inconclusive_sample_count": self.inconclusive_sample_count,
            "sample_digests": list(self.sample_digests),
            "counts_as_proof": self.counts_as_proof,
            "repair_eligible": self.repair_eligible,
            "may_enter_repair": self.may_enter_repair,
            "quarantine_candidate": (
                self.quarantine_candidate.to_dict()
                if self.quarantine_candidate is not None
                else None
            ),
            "automatic_quarantine": self.automatic_quarantine,
            "reasons": list(self.reasons),
        }


def _output_bytes(output: str | bytes | None) -> bytes | None:
    if output is None:
        return None
    return output if isinstance(output, bytes) else output.encode("utf-8")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "FlakeCheck",
    "FlakeClassification",
    "FlakeExecution",
    "FlakeFirewallResult",
    "FlakeSample",
    "FlakeSampleStatus",
    "InfrastructureFailure",
    "QuarantineCandidate",
]

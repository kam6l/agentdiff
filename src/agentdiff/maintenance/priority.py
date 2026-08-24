"""Deterministic maintenance urgency policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

from ._canonical import (
    clean_bool,
    clean_int_range,
    clean_string_tuple,
    clean_timestamp,
    reject_unknown,
    require_mapping,
)
from .models import MaintenanceSeverity


class PriorityDecision(str, Enum):
    """Deterministic maintenance queue decision."""

    FIX_NOW = "FIX_NOW"
    SCHEDULE = "SCHEDULE"
    REVIEW = "REVIEW"
    IGNORE = "IGNORE"


@dataclass(frozen=True, slots=True)
class PriorityInputs:
    """Policy inputs for one repository exposure."""

    security_severity: MaintenanceSeverity
    repository_criticality: int
    usage_count: int
    blast_radius: int
    version_distance: int
    deterministic_transform: bool
    test_quality: int
    proof_available: bool
    owners: tuple[str, ...]
    maintenance_window_open: bool
    breaking_deadline: str = ""
    evaluated_at: str = ""
    explicit_ignore: bool = False

    def __post_init__(self) -> None:
        try:
            severity = MaintenanceSeverity(self.security_severity)
        except ValueError as error:
            raise ValueError("security_severity is invalid") from error
        object.__setattr__(self, "security_severity", severity)
        object.__setattr__(
            self,
            "repository_criticality",
            clean_int_range(
                self.repository_criticality,
                field="repository_criticality",
                minimum=0,
                maximum=100,
            ),
        )
        object.__setattr__(
            self,
            "usage_count",
            clean_int_range(self.usage_count, field="usage_count", minimum=0),
        )
        object.__setattr__(
            self,
            "blast_radius",
            clean_int_range(
                self.blast_radius,
                field="blast_radius",
                minimum=0,
                maximum=100,
            ),
        )
        object.__setattr__(
            self,
            "version_distance",
            clean_int_range(self.version_distance, field="version_distance", minimum=0),
        )
        object.__setattr__(
            self,
            "deterministic_transform",
            clean_bool(self.deterministic_transform, field="deterministic_transform"),
        )
        object.__setattr__(
            self,
            "test_quality",
            clean_int_range(
                self.test_quality,
                field="test_quality",
                minimum=0,
                maximum=100,
            ),
        )
        object.__setattr__(
            self,
            "proof_available",
            clean_bool(self.proof_available, field="proof_available"),
        )
        object.__setattr__(
            self,
            "owners",
            clean_string_tuple(self.owners, field="owners"),
        )
        object.__setattr__(
            self,
            "maintenance_window_open",
            clean_bool(self.maintenance_window_open, field="maintenance_window_open"),
        )
        object.__setattr__(
            self,
            "breaking_deadline",
            clean_timestamp(
                self.breaking_deadline,
                field="breaking_deadline",
                required=False,
            ),
        )
        object.__setattr__(
            self,
            "evaluated_at",
            clean_timestamp(self.evaluated_at, field="evaluated_at", required=False),
        )
        object.__setattr__(
            self,
            "explicit_ignore",
            clean_bool(self.explicit_ignore, field="explicit_ignore"),
        )
        if bool(self.breaking_deadline) != bool(self.evaluated_at):
            raise ValueError("breaking_deadline and evaluated_at must be provided together")

    def to_dict(self) -> dict[str, Any]:
        return {
            "security_severity": self.security_severity.value,
            "repository_criticality": self.repository_criticality,
            "usage_count": self.usage_count,
            "blast_radius": self.blast_radius,
            "version_distance": self.version_distance,
            "deterministic_transform": self.deterministic_transform,
            "test_quality": self.test_quality,
            "proof_available": self.proof_available,
            "owners": list(self.owners),
            "maintenance_window_open": self.maintenance_window_open,
            "breaking_deadline": self.breaking_deadline,
            "evaluated_at": self.evaluated_at,
            "explicit_ignore": self.explicit_ignore,
        }

    @classmethod
    def from_dict(cls, value: object) -> PriorityInputs:
        data = require_mapping(value, field="PriorityInputs")
        reject_unknown(
            data,
            frozenset(
                {
                    "security_severity",
                    "repository_criticality",
                    "usage_count",
                    "blast_radius",
                    "version_distance",
                    "deterministic_transform",
                    "test_quality",
                    "proof_available",
                    "owners",
                    "maintenance_window_open",
                    "breaking_deadline",
                    "evaluated_at",
                    "explicit_ignore",
                }
            ),
            field="PriorityInputs",
        )
        try:
            severity = MaintenanceSeverity(data.get("security_severity", ""))
        except ValueError as error:
            raise ValueError("security_severity is invalid") from error
        return cls(
            security_severity=severity,
            repository_criticality=data.get("repository_criticality", -1),
            usage_count=data.get("usage_count", -1),
            blast_radius=data.get("blast_radius", -1),
            version_distance=data.get("version_distance", -1),
            deterministic_transform=clean_bool(
                data.get("deterministic_transform"), field="deterministic_transform"
            ),
            test_quality=data.get("test_quality", -1),
            proof_available=clean_bool(data.get("proof_available"), field="proof_available"),
            owners=clean_string_tuple(data.get("owners", []), field="owners"),
            maintenance_window_open=clean_bool(
                data.get("maintenance_window_open"), field="maintenance_window_open"
            ),
            breaking_deadline=data.get("breaking_deadline", ""),
            evaluated_at=data.get("evaluated_at", ""),
            explicit_ignore=clean_bool(data.get("explicit_ignore", False), field="explicit_ignore"),
        )


@dataclass(frozen=True, slots=True)
class PriorityResult:
    """Explainable deterministic priority outcome."""

    decision: PriorityDecision
    score: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "score": self.score,
            "reasons": list(self.reasons),
        }


class PriorityEngine:
    """Apply fixed policy rules; no model participates in the decision."""

    _SEVERITY_POINTS: ClassVar[dict[MaintenanceSeverity, int]] = {
        MaintenanceSeverity.INFO: 0,
        MaintenanceSeverity.LOW: 10,
        MaintenanceSeverity.MODERATE: 25,
        MaintenanceSeverity.HIGH: 45,
        MaintenanceSeverity.CRITICAL: 70,
    }

    def decide(self, inputs: PriorityInputs) -> PriorityResult:
        if not isinstance(inputs, PriorityInputs):
            raise TypeError("inputs must be PriorityInputs")
        if inputs.explicit_ignore:
            return PriorityResult(
                PriorityDecision.IGNORE, 0, ("policy explicitly ignores exposure",)
            )
        if inputs.usage_count == 0:
            return PriorityResult(PriorityDecision.IGNORE, 0, ("repository has no matched usage",))

        deadline_days = self._deadline_days(inputs)
        score = self._score(inputs, deadline_days)
        reasons = [f"security severity is {inputs.security_severity.value}"]
        if deadline_days is not None:
            reasons.append(f"breaking deadline is {deadline_days} day(s) away")
        if inputs.repository_criticality >= 75:
            reasons.append("repository criticality is high")
        if inputs.blast_radius >= 60:
            reasons.append("blast radius is high")

        if inputs.security_severity is MaintenanceSeverity.CRITICAL:
            reasons.append("critical security maintenance cannot wait for a window")
            return PriorityResult(PriorityDecision.FIX_NOW, score, tuple(reasons))
        if deadline_days is not None and deadline_days <= 0:
            reasons.append("breaking deadline has arrived")
            return PriorityResult(PriorityDecision.FIX_NOW, score, tuple(reasons))

        if score >= 70:
            weakness = self._review_reason(inputs)
            if weakness:
                reasons.append(weakness)
                return PriorityResult(PriorityDecision.REVIEW, score, tuple(reasons))
            if not inputs.maintenance_window_open:
                reasons.append("maintenance window is closed")
                return PriorityResult(PriorityDecision.SCHEDULE, score, tuple(reasons))
            reasons.append("urgency and repository exposure exceed the fix-now threshold")
            return PriorityResult(PriorityDecision.FIX_NOW, score, tuple(reasons))

        if score >= 40:
            weakness = self._review_reason(inputs)
            if weakness:
                reasons.append(weakness)
                return PriorityResult(PriorityDecision.REVIEW, score, tuple(reasons))

        window_reason = (
            "maintenance window is open"
            if inputs.maintenance_window_open
            else "maintenance window is closed"
        )
        reasons.append(window_reason)
        return PriorityResult(PriorityDecision.SCHEDULE, score, tuple(reasons))

    def _score(self, inputs: PriorityInputs, deadline_days: int | None) -> int:
        score = self._SEVERITY_POINTS[inputs.security_severity]
        score += inputs.repository_criticality // 5
        score += min(15, inputs.usage_count)
        score += inputs.blast_radius // 10
        score += min(10, inputs.version_distance * 2)
        if deadline_days is not None:
            if deadline_days <= 0:
                score += 30
            elif deadline_days <= 7:
                score += 25
            elif deadline_days <= 30:
                score += 15
            elif deadline_days <= 90:
                score += 5
        return min(100, score)

    @staticmethod
    def _deadline_days(inputs: PriorityInputs) -> int | None:
        if not inputs.breaking_deadline:
            return None
        deadline = datetime.fromisoformat(inputs.breaking_deadline)
        evaluated = datetime.fromisoformat(inputs.evaluated_at)
        return int((deadline - evaluated).total_seconds() // 86_400)

    @staticmethod
    def _review_reason(inputs: PriorityInputs) -> str:
        if not inputs.owners:
            return "affected repository has no assigned owner"
        if inputs.test_quality < 40:
            return "test quality is below the automatic-priority threshold"
        if not inputs.proof_available and not inputs.deterministic_transform:
            return "neither proof nor a deterministic transform is available"
        return ""

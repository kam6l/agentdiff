"""Serializable safety-controller evidence models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ControlLevel(str, Enum):
    """The precise strength of one runtime control or observation."""

    OBSERVED = "OBSERVED"
    INTERCEPTED = "INTERCEPTED"
    BLOCKED = "BLOCKED"
    SANDBOXED = "SANDBOXED"
    RECOVERABLE = "RECOVERABLE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class SafetyEvent:
    """One live observation and any deterministic control decision it caused."""

    sequence: int
    metric: str
    observed: int | float | str
    limit: int | None
    level: ControlLevel
    action: str
    detail: str
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["level"] = self.level.value
        return value


@dataclass(slots=True)
class SafetyReport:
    """Normalized live-control result retained even when execution is terminated."""

    backend: str
    enforcement: dict[str, ControlLevel]
    events: list[SafetyEvent] = field(default_factory=list)
    terminated: bool = False
    termination_reason: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "backend": self.backend,
            "enforcement": {name: level.value for name, level in sorted(self.enforcement.items())},
            "terminated": self.terminated,
            "termination_reason": self.termination_reason,
            "events": [event.to_dict() for event in self.events],
        }

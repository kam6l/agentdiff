"""Serializable transaction and rollback result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RollbackAction:
    """A filesystem recovery action that completed safely."""

    path: str
    action: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RollbackConflict:
    """A mutation AgentDiff refused to alter automatically."""

    path: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RollbackReport:
    """Result of one conservative rollback attempt."""

    run_id: str
    actions: list[RollbackAction] = field(default_factory=list)
    conflicts: list[RollbackConflict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "ok": self.ok,
            "actions": [item.to_dict() for item in self.actions],
            "conflicts": [item.to_dict() for item in self.conflicts],
            "skipped": list(self.skipped),
        }

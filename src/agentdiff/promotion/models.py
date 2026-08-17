"""Structured promotion plan and result evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PromotionAction:
    path: str
    action: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PromotionConflict:
    path: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PromotionPlanEntry:
    path: str
    change_type: str
    decision: str
    disposition: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PromotionPlan:
    run_id: str
    patch_digest: str
    safe_only: bool
    selected_paths: tuple[str, ...]
    entries: tuple[PromotionPlanEntry, ...]
    ready: bool
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "patch_digest": self.patch_digest,
            "safe_only": self.safe_only,
            "selected_paths": list(self.selected_paths),
            "entries": [entry.to_dict() for entry in self.entries],
            "ready": self.ready,
        }


@dataclass(slots=True)
class PromotionReport:
    run_id: str
    status: str
    dry_run: bool
    patch_digest: str
    actions: list[PromotionAction] = field(default_factory=list)
    conflicts: list[PromotionConflict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    schema_version: int = 1

    @property
    def ok(self) -> bool:
        return not self.conflicts and self.status in {"PROMOTED", "DRY_RUN_SAFE"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "status": self.status,
            "ok": self.ok,
            "dry_run": self.dry_run,
            "patch_digest": self.patch_digest,
            "actions": [action.to_dict() for action in self.actions],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
            "skipped": list(self.skipped),
        }

"""Deterministic, explainable scoring of observed runtime side effects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

from agentdiff.policy import PolicyAction


class RiskLevel(str, Enum):
    """Stable user-facing blast-radius categories."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class BlastRadiusWeights:
    """Version-1 additive weights; final scores are capped at 100."""

    review_created: int = 8
    review_modified: int = 4
    review_deleted: int = 12
    denied_mutation: int = 30
    denied_deletion: int = 40
    sensitive_path: int = 35
    dependency_change: int = 8
    mode_change: int = 8
    orphan_process: int = 10
    opened_port: int = 5
    budget_violation: int = 12
    scope_drift: int = 2

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{item.name} must be a non-negative integer")

    @classmethod
    def from_mapping(cls, overrides: Mapping[str, int]) -> "BlastRadiusWeights":
        """Create weights from previously schema-validated overrides."""

        known = {item.name for item in fields(cls)}
        unknown = sorted(set(overrides) - known)
        if unknown:
            raise ValueError(f"unknown blast-radius weight: {unknown[0]}")
        return replace(cls(), **dict(overrides))


@dataclass(frozen=True, slots=True)
class MutationRisk:
    """Policy-enriched evidence for one filesystem mutation."""

    path: str
    change_type: str
    decision: PolicyAction | str
    mode_changed: bool = False

    def __post_init__(self) -> None:
        if self.change_type not in {"created", "modified", "deleted"}:
            raise ValueError("change_type must be created, modified, or deleted")
        if not isinstance(self.decision, PolicyAction):
            object.__setattr__(self, "decision", PolicyAction(self.decision))


@dataclass(frozen=True, slots=True)
class RiskComponent:
    """One additive contribution to a blast-radius result."""

    name: str
    count: int
    weight: int
    points: int
    detail: str


@dataclass(frozen=True, slots=True)
class BlastRadiusResult:
    """Capped score plus uncapped evidence and category counts."""

    score: int
    raw_score: int
    level: RiskLevel
    counts: dict[str, int]
    components: list[RiskComponent]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "raw_score": self.raw_score,
            "level": self.level.value,
            "counts": dict(self.counts),
            "components": [asdict(component) for component in self.components],
        }


_DEPENDENCY_FILES = frozenset(
    {
        "cargo.lock",
        "cargo.toml",
        "composer.json",
        "composer.lock",
        "gemfile",
        "gemfile.lock",
        "go.mod",
        "go.sum",
        "package-lock.json",
        "package.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
        "yarn.lock",
    }
)
_SENSITIVE_PARTS = frozenset({".aws", ".ssh", "credentials", "secrets"})
_SENSITIVE_FILES = frozenset(
    {"authorized_keys", "credentials", "id_dsa", "id_ed25519", "id_rsa", "known_hosts"}
)


def _is_sensitive(path: str) -> bool:
    normalized = PurePosixPath(path.replace("\\", "/"))
    parts = {part.lower() for part in normalized.parts}
    name = normalized.name.lower()
    return (
        name == ".env"
        or name.startswith(".env.")
        or name in _SENSITIVE_FILES
        or name.endswith((".key", ".pem", ".p12", ".pfx"))
        or bool(parts & _SENSITIVE_PARTS)
    )


def _is_dependency(path: str) -> bool:
    return PurePosixPath(path.replace("\\", "/")).name.lower() in _DEPENDENCY_FILES


class BlastRadiusScorer:
    """Compute a local additive score from concrete, policy-enriched evidence."""

    def __init__(self, weights: BlastRadiusWeights | None = None) -> None:
        self.weights = weights or BlastRadiusWeights()

    @staticmethod
    def level_for(score: int) -> RiskLevel:
        bounded = max(0, min(100, score))
        if bounded <= 20:
            return RiskLevel.LOW
        if bounded <= 40:
            return RiskLevel.MODERATE
        if bounded <= 70:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    def score(
        self,
        mutations: Iterable[MutationRisk],
        *,
        orphan_processes: int = 0,
        opened_ports: int = 0,
        budget_violations: int = 0,
    ) -> BlastRadiusResult:
        for name, value in (
            ("orphan_processes", orphan_processes),
            ("opened_ports", opened_ports),
            ("budget_violations", budget_violations),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

        ordered = sorted(mutations, key=lambda item: (item.path, item.change_type))
        counts = {
            "files_changed": len(ordered),
            "files_deleted": sum(item.change_type == "deleted" for item in ordered),
            "unexpected_files": sum(item.decision is not PolicyAction.ALLOW for item in ordered),
            "sensitive_files": sum(_is_sensitive(item.path) for item in ordered),
            "dependency_changes": sum(_is_dependency(item.path) for item in ordered),
            "orphan_processes": orphan_processes,
            "ports_opened": opened_ports,
            "budget_violations": budget_violations,
        }
        components: list[RiskComponent] = []

        def add(name: str, count: int, weight: int, detail: str) -> None:
            if count and weight:
                components.append(
                    RiskComponent(
                        name=name,
                        count=count,
                        weight=weight,
                        points=count * weight,
                        detail=detail,
                    )
                )

        for mutation in ordered:
            if mutation.decision is PolicyAction.REVIEW:
                weight = getattr(self.weights, f"review_{mutation.change_type}")
                add("review_mutation", 1, weight, f"{mutation.change_type}: {mutation.path}")
            elif mutation.decision is PolicyAction.DENY:
                weight = (
                    self.weights.denied_deletion
                    if mutation.change_type == "deleted"
                    else self.weights.denied_mutation
                )
                add("denied_mutation", 1, weight, f"{mutation.change_type}: {mutation.path}")
            if _is_sensitive(mutation.path):
                add("sensitive_path", 1, self.weights.sensitive_path, mutation.path)
            if _is_dependency(mutation.path):
                add("dependency_change", 1, self.weights.dependency_change, mutation.path)
            if mutation.mode_changed:
                add("mode_change", 1, self.weights.mode_change, mutation.path)

        unexpected = counts["unexpected_files"]
        add(
            "scope_drift",
            max(0, unexpected - 5),
            self.weights.scope_drift,
            "unexpected files beyond the first five",
        )
        add(
            "orphan_process",
            orphan_processes,
            self.weights.orphan_process,
            "owned descendants left",
        )
        add("opened_port", opened_ports, self.weights.opened_port, "new listening ports observed")
        add(
            "budget_violation",
            budget_violations,
            self.weights.budget_violation,
            "configured limits exceeded",
        )

        raw_score = sum(component.points for component in components)
        score = min(100, raw_score)
        return BlastRadiusResult(
            score=score,
            raw_score=raw_score,
            level=self.level_for(score),
            counts=counts,
            components=components,
        )

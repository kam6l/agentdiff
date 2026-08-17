"""Typed, JSON-serializable policy schema models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

POLICY_SCHEMA_VERSION = 2
SUPPORTED_POLICY_VERSIONS = frozenset({1, 2})

BLAST_RADIUS_WEIGHT_KEYS = frozenset(
    {
        "review_created",
        "review_modified",
        "review_deleted",
        "denied_mutation",
        "denied_deletion",
        "sensitive_path",
        "dependency_change",
        "mode_change",
        "orphan_process",
        "opened_port",
        "budget_violation",
        "scope_drift",
    }
)


class PolicyAction(str, Enum):
    """A deterministic policy outcome."""

    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


class NetworkMode(str, Enum):
    """Network capabilities honestly supported by the local runtime."""

    OBSERVE = "observe"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class FilesystemPolicy:
    """Ordered filesystem glob rules and the unmatched-path action."""

    allow_write: tuple[str, ...] = ()
    review: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    default: PolicyAction = PolicyAction.REVIEW


@dataclass(frozen=True, slots=True)
class ProcessPolicy:
    """Rules for the root command launched by AgentDiff."""

    allow: tuple[str, ...] = ()
    review: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    default: PolicyAction = PolicyAction.REVIEW


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    """Network handling requested by policy."""

    mode: NetworkMode = NetworkMode.OBSERVE


@dataclass(frozen=True, slots=True)
class LimitsPolicy:
    """Optional non-negative runtime mutation limits."""

    files_changed: int | None = None
    files_deleted: int | None = None
    processes_spawned: int | None = None
    duration_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class RollbackPolicy:
    """Limits for conservative filesystem backups."""

    enabled: bool = True
    max_backup_file_mb: int = 25

    @property
    def backup_max_file_mb(self) -> int:
        """Compatibility alias for the initial unreleased field name."""

        return self.max_backup_file_mb


@dataclass(frozen=True, slots=True)
class ScoringPolicy:
    """Optional deterministic overrides for blast-radius weights."""

    weights: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class ProofPolicy:
    """Deterministic clean-room proof verification configuration."""

    image: str | None = None
    network: bool = False
    setup: tuple[tuple[str, ...], ...] = ()
    build: tuple[tuple[str, ...], ...] = ()
    tests: tuple[tuple[str, ...], ...] = ()
    trusted_digests: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Policy:
    """AgentDiff policy schema versions 1 and 2."""

    version: int = POLICY_SCHEMA_VERSION
    filesystem: FilesystemPolicy = field(default_factory=FilesystemPolicy)
    process: ProcessPolicy = field(default_factory=ProcessPolicy)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    limits: LimitsPolicy = field(default_factory=LimitsPolicy)
    rollback: RollbackPolicy = field(default_factory=RollbackPolicy)
    scoring: ScoringPolicy = field(default_factory=ScoringPolicy)
    proof: ProofPolicy = field(default_factory=ProofPolicy)


PolicyConfig = Policy

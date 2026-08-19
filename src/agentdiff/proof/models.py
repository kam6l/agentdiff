"""Structured clean-room proof evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from agentdiff.redaction import redact_argv


class ProofVerdict(str, Enum):
    PROVEN = "PROVEN"
    NOT_PROVEN = "NOT_PROVEN"


@dataclass(frozen=True, slots=True)
class ProofPhaseResult:
    """One exact-argv verification phase without raw log persistence."""

    phase: str
    command: tuple[str, ...]
    status: str
    returncode: int | None
    duration_seconds: float
    output_sha256: str | None = None
    output_bytes: int = 0
    tests_passed: int | None = None
    tests_total: int | None = None
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["command"] = redact_argv(self.command)
        return value


@dataclass(frozen=True, slots=True)
class ProofResult:
    """Deterministic proof verdict bound to one immutable patch digest."""

    run_id: str
    verdict: ProofVerdict
    promotion: str
    agent_run: str
    policy: str
    immediate_blast_radius: int
    future_blast_radius: int
    clean_environment: str
    hidden_state_dependency: str
    patch_digest: str
    immutable_manifest_sha256: str
    phases: tuple[ProofPhaseResult, ...]
    reasons: tuple[str, ...]
    verification_source: str = "unconfigured"
    verification_digest: str = ""
    trusted_plan: bool = True
    cache_hit: bool = False
    cached_from_run: str = ""
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "verdict": self.verdict.value,
            "promotion": self.promotion,
            "agent_run": self.agent_run,
            "policy": self.policy,
            "immediate_blast_radius": self.immediate_blast_radius,
            "future_blast_radius": self.future_blast_radius,
            "clean_environment": self.clean_environment,
            "hidden_state_dependency": self.hidden_state_dependency,
            "patch_digest": self.patch_digest,
            "immutable_manifest_sha256": self.immutable_manifest_sha256,
            "phases": [phase.to_dict() for phase in self.phases],
            "reasons": list(self.reasons),
            "verification_source": self.verification_source,
            "verification_digest": self.verification_digest,
            "trusted_plan": self.trusted_plan,
            "cache_hit": self.cache_hit,
            "cached_from_run": self.cached_from_run,
        }

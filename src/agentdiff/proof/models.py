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


class ProofStrengthLevel(str, Enum):
    L0_EXECUTION_ONLY = "L0_EXECUTION_ONLY"
    L1_CLEAN_ROOM = "L1_CLEAN_ROOM"
    L2_TRUSTED_COMMAND = "L2_TRUSTED_COMMAND"
    L3_BASELINE_VERIFIER = "L3_BASELINE_VERIFIER"


class ProofStrengthLabel(str, Enum):
    WEAK = "WEAK"
    REVIEW = "REVIEW"
    STRONG = "STRONG"


class VerifierIndependence(str, Enum):
    WEAK = "WEAK"
    REVIEW = "REVIEW"
    STRONG = "STRONG"


def compute_proof_strength(
    *,
    clean_environment: str,
    verification_confirmed: bool,
    baseline_verifier: str = "SKIPPED",
    baseline_available: bool = False,
    verifier_files_changed: int = 0,
) -> tuple[ProofStrengthLevel, ProofStrengthLabel, VerifierIndependence]:
    if clean_environment != "PASS":
        return (
            ProofStrengthLevel.L0_EXECUTION_ONLY,
            ProofStrengthLabel.WEAK,
            VerifierIndependence.WEAK,
        )
    if not verification_confirmed:
        return (
            ProofStrengthLevel.L1_CLEAN_ROOM,
            ProofStrengthLabel.WEAK,
            VerifierIndependence.WEAK,
        )
    if baseline_verifier == "PASS" and baseline_available:
        return (
            ProofStrengthLevel.L3_BASELINE_VERIFIER,
            ProofStrengthLabel.STRONG,
            VerifierIndependence.STRONG,
        )
    return (
        ProofStrengthLevel.L2_TRUSTED_COMMAND,
        ProofStrengthLabel.REVIEW,
        VerifierIndependence.WEAK,
    )


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
    verifier_files_changed: int = 0
    verifier_changes: tuple[str, ...] = ()
    baseline_available: bool = False
    baseline_verifier: str = "SKIPPED"
    patched_tests_total: int | None = None
    baseline_tests_total: int | None = None
    proof_strength: str = ProofStrengthLevel.L0_EXECUTION_ONLY.value
    proof_strength_label: str = ProofStrengthLabel.WEAK.value
    verifier_independence: str = VerifierIndependence.WEAK.value
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
            "verifier_files_changed": self.verifier_files_changed,
            "verifier_changes": list(self.verifier_changes),
            "baseline_available": self.baseline_available,
            "baseline_verifier": self.baseline_verifier,
            "patched_tests_total": self.patched_tests_total,
            "baseline_tests_total": self.baseline_tests_total,
            "proof_strength": self.proof_strength,
            "proof_strength_label": self.proof_strength_label,
            "verifier_independence": self.verifier_independence,
        }


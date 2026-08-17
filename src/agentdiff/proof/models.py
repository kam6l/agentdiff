"""Structured clean-room proof evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from agentdiff.redaction import redact_argv


class ProofVerdict(str, Enum):
    PROVEN = "PROVEN"
    NOT_PROVEN = "NOT_PROVEN"


class ProofStrengthLevel(str, Enum):
    """Deterministic proof-strength metadata (never an LLM decision).

    L0 — EXECUTION_ONLY:     the agent process exited successfully.
    L1 — CLEAN_ROOM:         the patch was reproduced in a fresh environment.
    L2 — TRUSTED_COMMAND:    verification commands came from trusted pre-run
                             evidence, never from the patched state.
    L3 — BASELINE_VERIFIER:  the original trusted tests were run against the
                             patched product code independently of any
                             agent-modified tests.
    L4 — EXTERNAL_VERIFIER:  an independent external CI/signed verifier also
                             passed (reserved; not currently produced).
    """

    L0_EXECUTION_ONLY = "L0"
    L1_CLEAN_ROOM = "L1"
    L2_TRUSTED_COMMAND = "L2"
    L3_BASELINE_VERIFIER = "L3"
    L4_EXTERNAL_VERIFIER = "L4"


class ProofStrengthLabel(str, Enum):
    WEAK = "WEAK"
    REVIEW = "REVIEW"
    STRONG = "STRONG"


class VerifierIndependence(str, Enum):
    """How independent the verification was from agent-modified test code."""

    STRONG = "STRONG"
    REVIEW = "REVIEW"
    WEAK = "WEAK"


def strength_label(level: ProofStrengthLevel) -> ProofStrengthLabel:
    if level in {
        ProofStrengthLevel.L0_EXECUTION_ONLY,
        ProofStrengthLevel.L1_CLEAN_ROOM,
    }:
        return ProofStrengthLabel.WEAK
    if level is ProofStrengthLevel.L2_TRUSTED_COMMAND:
        return ProofStrengthLabel.REVIEW
    return ProofStrengthLabel.STRONG


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
    verification_confirmed: bool = True
    baseline_verifier: str = "SKIPPED"
    baseline_tests_passed: int | None = None
    baseline_tests_total: int | None = None
    patched_tests_passed: int | None = None
    patched_tests_total: int | None = None
    verifier_files_changed: int = 0
    verifier_changes: tuple[str, ...] = ()
    baseline_available: bool = False
    verifier_independence: str = VerifierIndependence.WEAK.value
    proof_strength: str = ProofStrengthLevel.L0_EXECUTION_ONLY.value
    proof_strength_label: str = ProofStrengthLabel.WEAK.value
    schema_version: int = 2

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
            "verification_confirmed": self.verification_confirmed,
            "baseline_verifier": self.baseline_verifier,
            "baseline_tests_passed": self.baseline_tests_passed,
            "baseline_tests_total": self.baseline_tests_total,
            "patched_tests_passed": self.patched_tests_passed,
            "patched_tests_total": self.patched_tests_total,
            "verifier_files_changed": self.verifier_files_changed,
            "verifier_changes": list(self.verifier_changes),
            "baseline_available": self.baseline_available,
            "verifier_independence": self.verifier_independence,
            "proof_strength": self.proof_strength,
            "proof_strength_label": self.proof_strength_label,
        }

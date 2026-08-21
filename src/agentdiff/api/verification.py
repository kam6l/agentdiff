"""API migration adapter for the authoritative :class:`ProofEngine`.

This module does not implement a second verifier. It maps the real proof result
onto API-migration terminology and computes a canonical digest for certificates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from agentdiff.api.models import VerificationLevel
from agentdiff.proof import ProofEngine, ProofResult, ProofVerdict

if TYPE_CHECKING:
    from agentdiff.impact.cache import ProofCache


def canonical_sha256(value: dict[str, Any]) -> str:
    """Hash a JSON-compatible mapping using canonical serialization."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Migration-facing view of one real clean-room proof result."""

    level: VerificationLevel
    passed: bool
    proof: ProofResult
    proof_digest: str
    capsule_id: str
    reasons: tuple[str, ...] = ()

    @property
    def phases(self) -> tuple[Any, ...]:
        return self.proof.phases

    @property
    def summary(self) -> str:
        return f"Proof {self.proof.verdict.value} ({self.level.value})"


class MigrationVerifier:
    """Delegate migration verification to the one authoritative ProofEngine."""

    def __init__(
        self,
        root: str,
        run_id: str,
        *,
        environment_factory: Any | None = None,
        cache: ProofCache | None = None,
        target: str = "full",
    ) -> None:
        self.root = root
        self.run_id = run_id
        self.environment_factory = environment_factory
        self.cache = cache
        self.target = target

    def verify(self, *, timeout_seconds: float = 900.0) -> VerificationResult:
        engine = ProofEngine(
            self.root,
            self.run_id,
            environment_factory=self.environment_factory,
            cache=self.cache,
            target=self.target,
        )
        proof = engine.prove(timeout_seconds=timeout_seconds)
        level = achieved_verification_level(proof)
        return VerificationResult(
            level=level,
            passed=proof.verdict is ProofVerdict.PROVEN,
            proof=proof,
            proof_digest=canonical_sha256(proof.to_dict()),
            capsule_id=proof.run_id,
            reasons=proof.reasons,
        )


def achieved_verification_level(proof: ProofResult) -> VerificationLevel:
    """Map executed proof phases to truthful public verification levels."""

    passed_phases = {phase.phase for phase in proof.phases if phase.passed}
    if "tests" in passed_phases:
        return VerificationLevel.V3
    if "build" in passed_phases or "dependency_setup" in passed_phases:
        return VerificationLevel.V1
    return VerificationLevel.V0

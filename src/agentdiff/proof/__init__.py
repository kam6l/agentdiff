"""Deterministic clean-room proof for sealed AgentDiff patches."""

from .engine import ProofEngine
from .models import (
    ProofPhaseResult,
    ProofResult,
    ProofStrengthLabel,
    ProofStrengthLevel,
    ProofVerdict,
    VerifierIndependence,
    compute_proof_strength,
)
from .verifier_files import (
    VerifierMutationReport,
    analyze_verifier_mutations,
    is_verifier_related,
)

__all__ = [
    "ProofEngine",
    "ProofPhaseResult",
    "ProofResult",
    "ProofStrengthLabel",
    "ProofStrengthLevel",
    "ProofVerdict",
    "VerifierIndependence",
    "VerifierMutationReport",
    "analyze_verifier_mutations",
    "compute_proof_strength",
    "is_verifier_related",
]

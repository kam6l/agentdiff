"""Impact-aware proof planning: run the minimum strong proof for a patch."""

from .cache import ProofCache, ProofCacheEntry, ProofCacheKey
from .impact import ImpactEngine, ProofImpactPlan

__all__ = [
    "ImpactEngine",
    "ProofCache",
    "ProofCacheEntry",
    "ProofCacheKey",
    "ProofImpactPlan",
]

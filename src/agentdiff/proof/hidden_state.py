"""Deterministic hidden-state dependency classification."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ProofPhaseResult


def hidden_state_result(*, original_passed: bool, phases: tuple[ProofPhaseResult, ...]) -> str:
    """Flag possible hidden state when a successful run cannot pass clean replay."""

    if original_passed and phases and any(not phase.passed for phase in phases):
        return "POSSIBLE"
    if phases and all(phase.passed for phase in phases):
        return "NONE_DETECTED"
    return "NOT_ASSESSED"

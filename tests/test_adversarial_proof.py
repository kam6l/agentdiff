"""Focused tests for deterministic adversarial proof."""

from __future__ import annotations

from agentdiff.proof.adversarial import (
    AdversarialProofEngine,
    InvalidMutationError,
    MutationCase,
    MutationVerdict,
    MutationVerification,
)
from agentdiff.proof.models import ProofStrengthLabel


def test_mutation_score_and_survivor_downgrade_are_truthful() -> None:
    cases = tuple(
        MutationCase(id=name, payload=name)
        for name in ("remove-guard", "invert-condition", "wrong-boundary", "always-success")
    )

    result = AdversarialProofEngine(
        lambda case: case.payload,
        lambda mutant, _timeout: mutant == "always-success",
    ).prove(cases)

    assert [outcome.verdict for outcome in result.outcomes] == [
        MutationVerdict.KILLED,
        MutationVerdict.KILLED,
        MutationVerdict.KILLED,
        MutationVerdict.SURVIVED,
    ]
    assert result.killed == 3
    assert result.survived == 1
    assert result.score == 0.75
    assert result.score_label == "3 / 4"
    assert result.score_percent == 75
    assert result.original_strength is ProofStrengthLabel.STRONG
    assert result.strength is ProofStrengthLabel.REVIEW
    assert result.downgraded is True


def test_all_important_mutants_killed_preserves_strength() -> None:
    result = AdversarialProofEngine(
        lambda case: case.id,
        lambda _mutant, _timeout: False,
    ).prove((MutationCase("one"), MutationCase("two")))

    assert result.score == 1.0
    assert result.strength is ProofStrengthLabel.STRONG
    assert result.complete is True
    assert result.reasons == ()


def test_timeout_and_invalid_mutation_are_recorded_not_interpreted() -> None:
    def apply(case: MutationCase) -> str:
        if case.id == "invalid":
            raise InvalidMutationError("hunk no longer applies")
        return case.id

    def verify(mutant: str, _timeout: float) -> bool:
        if mutant == "timeout":
            raise TimeoutError("verification budget")
        return False

    result = AdversarialProofEngine(apply, verify).prove(
        (MutationCase("invalid"), MutationCase("timeout"))
    )

    assert [outcome.verdict for outcome in result.outcomes] == [
        MutationVerdict.INVALID,
        MutationVerdict.TIMEOUT,
    ]
    assert result.decisive == 0
    assert result.score == 0.0
    assert result.strength is ProofStrengthLabel.REVIEW


def test_case_budget_is_bounded_and_reported() -> None:
    result = AdversarialProofEngine(
        lambda case: case.id,
        lambda _mutant, _timeout: False,
        max_cases=1,
    ).prove((MutationCase("one"), MutationCase("two")))

    assert len(result.outcomes) == 1
    assert result.complete is False
    assert result.total_cases == 2
    assert result.strength is ProofStrengthLabel.REVIEW
    assert "mutation case budget reached" in result.reasons


def test_reported_verifier_timeout_is_honored() -> None:
    result = AdversarialProofEngine(
        lambda case: case.id,
        lambda _mutant, _timeout: MutationVerification(
            passed=False,
            duration_seconds=20.0,
        ),
    ).prove((MutationCase("slow"),), timeout_seconds=5.0)

    assert result.outcomes[0].verdict is MutationVerdict.TIMEOUT
    assert result.strength is ProofStrengthLabel.REVIEW

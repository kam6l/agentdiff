"""Bounded deterministic mutation checks for verifier sensitivity.

Adversarial proof never decides whether a mutation is semantically meaningful.
Callers supply an immutable :class:`MutationCase`, a deterministic mutation
applier, and the verifier that already represents the trusted behavior check.
The engine records whether that verifier kills or accidentally accepts each
mutant and truthfully downgrades proof strength when important challenges are
inconclusive or survive.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from .models import ProofStrengthLabel

MutationApplier = Callable[["MutationCase"], Any]
MutationVerifier = Callable[[Any, float], Any]


class MutationVerdict(str, Enum):
    """Outcome of applying one mutation and running its verifier."""

    KILLED = "KILLED"
    SURVIVED = "SURVIVED"
    TIMEOUT = "TIMEOUT"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class MutationCase:
    """One bounded deterministic mutation request.

    ``payload`` is intentionally opaque to the engine.  It may be a hunk ID,
    a structural mutation description, or another immutable value understood
    by the injected mutation applier.
    """

    id: str
    description: str = ""
    payload: Any = None
    important: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("mutation case id must not be empty")

    @property
    def case_id(self) -> str:
        return self.id

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "important": self.important,
        }


@dataclass(frozen=True, slots=True)
class MutationVerification:
    """Normalized verifier response for a mutated candidate."""

    passed: bool
    timed_out: bool = False
    duration_seconds: float = 0.0
    detail: str = ""
    valid: bool = True


@dataclass(frozen=True, slots=True)
class MutationOutcome:
    """Evidence for one adversarial mutation case."""

    case: MutationCase
    verdict: MutationVerdict
    duration_seconds: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.to_dict(),
            "verdict": self.verdict.value,
            "duration_seconds": self.duration_seconds,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AdversarialProofResult:
    """Mutation score plus a deterministic proof-strength recommendation."""

    outcomes: tuple[MutationOutcome, ...]
    score: float
    original_strength: ProofStrengthLabel
    strength: ProofStrengthLabel
    complete: bool
    total_cases: int
    reasons: tuple[str, ...] = ()
    schema_version: int = 1

    @property
    def killed(self) -> int:
        return sum(outcome.verdict is MutationVerdict.KILLED for outcome in self.outcomes)

    @property
    def survived(self) -> int:
        return sum(outcome.verdict is MutationVerdict.SURVIVED for outcome in self.outcomes)

    @property
    def timed_out(self) -> int:
        return sum(outcome.verdict is MutationVerdict.TIMEOUT for outcome in self.outcomes)

    @property
    def invalid(self) -> int:
        return sum(outcome.verdict is MutationVerdict.INVALID for outcome in self.outcomes)

    @property
    def decisive(self) -> int:
        return self.killed + self.survived

    @property
    def score_percent(self) -> int:
        return round(self.score * 100)

    @property
    def score_label(self) -> str:
        return f"{self.killed} / {self.decisive}"

    @property
    def downgraded(self) -> bool:
        return self.strength is not self.original_strength

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
            "score": self.score,
            "score_percent": self.score_percent,
            "score_label": self.score_label,
            "killed": self.killed,
            "survived": self.survived,
            "timed_out": self.timed_out,
            "invalid": self.invalid,
            "complete": self.complete,
            "total_cases": self.total_cases,
            "original_strength": self.original_strength.value,
            "strength": self.strength.value,
            "downgraded": self.downgraded,
            "reasons": list(self.reasons),
        }


class InvalidMutationError(ValueError):
    """Raised by an applier when a mutation cannot be constructed safely."""


class AdversarialProofEngine:
    """Apply and verify a bounded, ordered set of deterministic mutations."""

    def __init__(
        self,
        mutation_applier: MutationApplier,
        verifier: MutationVerifier,
        *,
        max_cases: int = 16,
        max_duration_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_cases < 1:
            raise ValueError("max_cases must be at least 1")
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than zero")
        self.mutation_applier = mutation_applier
        self.verifier = verifier
        self.max_cases = max_cases
        self.max_duration_seconds = max_duration_seconds
        self.clock = clock

    def prove(
        self,
        cases: Iterable[MutationCase],
        *,
        timeout_seconds: float = 60.0,
        starting_strength: ProofStrengthLabel | str = ProofStrengthLabel.STRONG,
    ) -> AdversarialProofResult:
        """Challenge the verifier in input order within strict case/time budgets."""

        if timeout_seconds <= 0:
            raise ValueError("mutation verifier timeout must be greater than zero")
        mutation_cases = tuple(cases)
        if len({case.id for case in mutation_cases}) != len(mutation_cases):
            raise ValueError("mutation case ids must be unique")
        strength = _coerce_strength(starting_strength)
        started = self.clock()
        outcomes: list[MutationOutcome] = []
        reasons: list[str] = []
        complete = True

        for index, case in enumerate(mutation_cases):
            elapsed = max(0.0, self.clock() - started)
            if index >= self.max_cases:
                complete = False
                reasons.append("mutation case budget reached")
                break
            if elapsed >= self.max_duration_seconds:
                complete = False
                reasons.append("adversarial proof duration budget reached")
                break
            outcome = self._run_case(
                case,
                timeout_seconds=min(timeout_seconds, self.max_duration_seconds - elapsed),
            )
            outcomes.append(outcome)

        decisive = sum(
            outcome.verdict in {MutationVerdict.KILLED, MutationVerdict.SURVIVED}
            for outcome in outcomes
        )
        killed = sum(outcome.verdict is MutationVerdict.KILLED for outcome in outcomes)
        score = killed / decisive if decisive else 0.0
        important_concern = any(
            outcome.case.important and outcome.verdict is not MutationVerdict.KILLED
            for outcome in outcomes
        )
        if not mutation_cases:
            reasons.append("no mutation cases were supplied")
            important_concern = True
        if not complete:
            important_concern = True
        if important_concern:
            strength = _downgrade_strength(strength)
            reasons.append("important mutation evidence was survived or inconclusive")

        return AdversarialProofResult(
            outcomes=tuple(outcomes),
            score=score,
            original_strength=_coerce_strength(starting_strength),
            strength=strength,
            complete=complete,
            total_cases=len(mutation_cases),
            reasons=tuple(dict.fromkeys(reasons)),
        )

    def run(
        self,
        cases: Iterable[MutationCase],
        *,
        timeout_seconds: float = 60.0,
        starting_strength: ProofStrengthLabel | str = ProofStrengthLabel.STRONG,
    ) -> AdversarialProofResult:
        """Alias for :meth:`prove` for orchestration code."""

        return self.prove(
            cases,
            timeout_seconds=timeout_seconds,
            starting_strength=starting_strength,
        )

    def _run_case(self, case: MutationCase, *, timeout_seconds: float) -> MutationOutcome:
        started = self.clock()
        try:
            mutant = self.mutation_applier(case)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return MutationOutcome(
                case=case,
                verdict=MutationVerdict.INVALID,
                duration_seconds=max(0.0, self.clock() - started),
                detail=f"mutation application failed: {type(error).__name__}: {error}",
            )
        if mutant is None:
            return MutationOutcome(
                case=case,
                verdict=MutationVerdict.INVALID,
                duration_seconds=max(0.0, self.clock() - started),
                detail="mutation applier returned no candidate",
            )

        elapsed = max(0.0, self.clock() - started)
        remaining = timeout_seconds - elapsed
        if remaining <= 0:
            return MutationOutcome(
                case=case,
                verdict=MutationVerdict.TIMEOUT,
                duration_seconds=elapsed,
                detail="mutation application exhausted the case timeout",
            )
        try:
            raw = self.verifier(mutant, remaining)
        except TimeoutError as error:
            return MutationOutcome(
                case=case,
                verdict=MutationVerdict.TIMEOUT,
                duration_seconds=max(0.0, self.clock() - started),
                detail=f"mutation verifier timed out: {error}",
            )
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            return MutationOutcome(
                case=case,
                verdict=MutationVerdict.INVALID,
                duration_seconds=max(0.0, self.clock() - started),
                detail=f"mutation verifier failed: {type(error).__name__}: {error}",
            )
        duration = max(0.0, self.clock() - started)
        try:
            verification = _normalize_verification(raw, duration)
        except (TypeError, ValueError) as error:
            return MutationOutcome(
                case=case,
                verdict=MutationVerdict.INVALID,
                duration_seconds=duration,
                detail=f"invalid mutation verifier result: {error}",
            )
        effective_duration = max(duration, verification.duration_seconds)
        if effective_duration > timeout_seconds or verification.timed_out:
            return MutationOutcome(
                case=case,
                verdict=MutationVerdict.TIMEOUT,
                duration_seconds=effective_duration,
                detail=verification.detail or "mutation verifier exceeded the case timeout",
            )
        if not verification.valid:
            return MutationOutcome(
                case=case,
                verdict=MutationVerdict.INVALID,
                duration_seconds=effective_duration,
                detail=verification.detail or "mutation verifier returned invalid evidence",
            )
        return MutationOutcome(
            case=case,
            verdict=(MutationVerdict.SURVIVED if verification.passed else MutationVerdict.KILLED),
            duration_seconds=effective_duration,
            detail=verification.detail,
        )


def _normalize_verification(raw: Any, duration_seconds: float) -> MutationVerification:
    if isinstance(raw, MutationVerification):
        return MutationVerification(
            passed=raw.passed,
            timed_out=raw.timed_out,
            duration_seconds=raw.duration_seconds or duration_seconds,
            detail=raw.detail,
            valid=raw.valid,
        )
    if isinstance(raw, bool):
        return MutationVerification(passed=raw, duration_seconds=duration_seconds)
    if isinstance(raw, int):
        return MutationVerification(passed=raw == 0, duration_seconds=duration_seconds)
    if isinstance(raw, Mapping):
        timed_out = bool(raw.get("timed_out", False))
        if "causally_proven" in raw:
            passed = bool(raw["causally_proven"])
        elif "passed" in raw:
            passed = bool(raw["passed"])
        elif "returncode" in raw:
            passed = int(raw["returncode"]) == 0
        elif "verdict" in raw:
            passed = _verdict_is_proven(raw["verdict"])
        elif timed_out or not bool(raw.get("valid", True)):
            passed = False
        else:
            raise ValueError("mapping has no causally_proven, passed, returncode, or verdict field")
        return MutationVerification(
            passed=passed,
            timed_out=timed_out,
            duration_seconds=float(raw.get("duration_seconds", duration_seconds)),
            detail=str(raw.get("detail", "")),
            valid=bool(raw.get("valid", True)),
        )

    if hasattr(raw, "causally_proven"):
        passed = bool(raw.causally_proven)
    elif hasattr(raw, "passed"):
        passed = bool(raw.passed)
    elif hasattr(raw, "verdict"):
        passed = _verdict_is_proven(raw.verdict)
    elif hasattr(raw, "returncode"):
        passed = int(raw.returncode) == 0
    else:
        raise TypeError("unsupported mutation verifier result")
    return MutationVerification(
        passed=passed,
        timed_out=bool(getattr(raw, "timed_out", False)),
        duration_seconds=float(getattr(raw, "duration_seconds", duration_seconds)),
        detail=str(getattr(raw, "detail", "")),
        valid=bool(getattr(raw, "valid", True)),
    )


def _verdict_is_proven(value: Any) -> bool:
    raw = value.value if hasattr(value, "value") else value
    return str(raw).upper() in {
        "PASS",
        "PASSED",
        "PROVEN",
        "CAUSAL_DELTA_CONFIRMED",
        "BEHAVIOR_EQUIVALENCE_CONFIRMED",
    }


def _coerce_strength(value: ProofStrengthLabel | str) -> ProofStrengthLabel:
    if isinstance(value, ProofStrengthLabel):
        return value
    return ProofStrengthLabel(str(value).upper())


def _downgrade_strength(value: ProofStrengthLabel) -> ProofStrengthLabel:
    if value is ProofStrengthLabel.STRONG:
        return ProofStrengthLabel.REVIEW
    return ProofStrengthLabel.WEAK


# Explicit aliases make the public vocabulary easy to discover.
AdversarialVerdict = MutationVerdict
MutationResult = MutationOutcome


__all__ = [
    "AdversarialProofEngine",
    "AdversarialProofResult",
    "AdversarialVerdict",
    "InvalidMutationError",
    "MutationCase",
    "MutationOutcome",
    "MutationResult",
    "MutationVerdict",
    "MutationVerification",
]

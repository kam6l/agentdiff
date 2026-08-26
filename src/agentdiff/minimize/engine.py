"""Budgeted practical delta-debugging for already-proven patch groups."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

ProofCallback = Callable[[tuple[Any, ...]], Any]


class ProofCheckStatus(str, Enum):
    """Normalized response from the injected proof callback."""

    PROVEN = "PROVEN"
    NOT_PROVEN = "NOT_PROVEN"
    TIMEOUT = "TIMEOUT"
    INVALID = "INVALID"


class MinimizationStatus(str, Enum):
    """Final state of one bounded minimization attempt."""

    MINIMIZED = "MINIMIZED"
    UNCHANGED = "UNCHANGED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    INITIAL_NOT_PROVEN = "INITIAL_NOT_PROVEN"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class PatchGroup:
    """Opaque immutable unit that may be removed and independently re-proven.

    The engine never interprets ``payload``. Callers should place immutable
    hunk/change identifiers or immutable patch data in it and reconstruct the
    candidate patch inside the proof callback.
    """

    id: str
    payload: Any = None
    paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("patch group id must not be empty")
        object.__setattr__(self, "paths", tuple(self.paths))

    @property
    def group_id(self) -> str:
        return self.id

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "paths": list(self.paths)}


@dataclass(frozen=True, slots=True)
class ProofAttempt:
    """One unique candidate subset evaluated during minimization."""

    kept_group_ids: tuple[str, ...]
    status: ProofCheckStatus
    duration_seconds: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kept_group_ids": list(self.kept_group_ids),
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class PatchMinimizationResult:
    """Smallest patch subset found within the explicit deterministic budget."""

    status: MinimizationStatus
    original_groups: tuple[Any, ...]
    minimized_groups: tuple[Any, ...]
    removed_groups: tuple[Any, ...]
    attempts: tuple[ProofAttempt, ...]
    proof_runs: int
    combinations: int
    duration_seconds: float
    complete: bool
    reasons: tuple[str, ...] = ()
    schema_version: int = 1

    @property
    def changed(self) -> bool:
        return len(self.minimized_groups) < len(self.original_groups)

    @property
    def minimal_within_strategy(self) -> bool:
        return self.complete and self.status in {
            MinimizationStatus.MINIMIZED,
            MinimizationStatus.UNCHANGED,
        }

    @property
    def kept_groups(self) -> tuple[Any, ...]:
        return self.minimized_groups

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "original_group_ids": [_group_id(group) for group in self.original_groups],
            "minimized_group_ids": [_group_id(group) for group in self.minimized_groups],
            "removed_group_ids": [_group_id(group) for group in self.removed_groups],
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "proof_runs": self.proof_runs,
            "combinations": self.combinations,
            "duration_seconds": self.duration_seconds,
            "complete": self.complete,
            "changed": self.changed,
            "minimal_within_strategy": self.minimal_within_strategy,
            "reasons": list(self.reasons),
        }


class PatchMinimizer:
    """Find a 1-minimal practical patch using bounded ddmin-style removal."""

    def __init__(
        self,
        proof_callback: ProofCallback,
        *,
        max_proof_runs: int = 32,
        max_duration_seconds: float = 900.0,
        max_combinations: int = 64,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_proof_runs < 1:
            raise ValueError("max_proof_runs must be at least 1")
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than zero")
        if max_combinations < 1:
            raise ValueError("max_combinations must be at least 1")
        self.proof_callback = proof_callback
        self.max_proof_runs = max_proof_runs
        self.max_duration_seconds = max_duration_seconds
        self.max_combinations = max_combinations
        self.clock = clock

    def minimize(self, groups: Iterable[Any]) -> PatchMinimizationResult:
        """Minimize an immutable ordered collection without exhaustive search."""

        original = tuple(groups)
        patch_groups = [group for group in original if isinstance(group, PatchGroup)]
        if len({group.id for group in patch_groups}) != len(patch_groups):
            raise ValueError("patch group ids must be unique")

        state = _MinimizationState(
            original=original,
            proof_callback=self.proof_callback,
            max_proof_runs=self.max_proof_runs,
            max_duration_seconds=self.max_duration_seconds,
            max_combinations=self.max_combinations,
            clock=self.clock,
        )
        initial = state.check(tuple(range(len(original))), combination=False)
        if initial is None:
            return state.result(
                tuple(range(len(original))),
                status=MinimizationStatus.BUDGET_EXHAUSTED,
                complete=False,
            )
        if initial is ProofCheckStatus.NOT_PROVEN:
            state.reasons.append("the original patch groups did not pass the proof callback")
            return state.result(
                tuple(range(len(original))),
                status=MinimizationStatus.INITIAL_NOT_PROVEN,
                complete=True,
            )
        if initial is not ProofCheckStatus.PROVEN:
            state.reasons.append("the original patch proof was inconclusive")
            return state.result(
                tuple(range(len(original))),
                status=MinimizationStatus.INCONCLUSIVE,
                complete=False,
            )

        current = tuple(range(len(original)))
        granularity = 2
        exhausted = False

        while len(current) >= 2:
            reduced = False
            for chunk in _partition(current, granularity):
                removed = set(chunk)
                candidate = tuple(index for index in current if index not in removed)
                checked = state.check(candidate, combination=True)
                if checked is None:
                    exhausted = True
                    break
                if checked is ProofCheckStatus.PROVEN:
                    current = candidate
                    granularity = max(2, granularity - 1)
                    reduced = True
                    break
            if exhausted:
                break
            if reduced:
                continue
            if granularity >= len(current):
                break
            granularity = min(len(current), granularity * 2)

        # A deterministic single-group cleanup establishes practical 1-minimality
        # when the budget allows it, including the one-group -> empty case.
        changed = True
        while changed and not exhausted:
            changed = False
            for index in current:
                candidate = tuple(item for item in current if item != index)
                checked = state.check(candidate, combination=True)
                if checked is None:
                    exhausted = True
                    break
                if checked is ProofCheckStatus.PROVEN:
                    current = candidate
                    changed = True
                    break

        if exhausted:
            return state.result(
                current,
                status=MinimizationStatus.BUDGET_EXHAUSTED,
                complete=False,
            )
        if state.inconclusive:
            return state.result(
                current,
                status=MinimizationStatus.INCONCLUSIVE,
                complete=False,
            )
        status = (
            MinimizationStatus.MINIMIZED
            if len(current) < len(original)
            else MinimizationStatus.UNCHANGED
        )
        return state.result(current, status=status, complete=True)

    def run(self, groups: Iterable[Any]) -> PatchMinimizationResult:
        """Alias for :meth:`minimize` for orchestration code."""

        return self.minimize(groups)


@dataclass(slots=True)
class _MinimizationState:
    original: tuple[Any, ...]
    proof_callback: ProofCallback
    max_proof_runs: int
    max_duration_seconds: float
    max_combinations: int
    clock: Callable[[], float]
    started: float = field(init=False)
    proof_runs: int = field(init=False, default=0)
    combinations: int = field(init=False, default=0)
    inconclusive: bool = field(init=False, default=False)
    attempts: list[ProofAttempt] = field(init=False, default_factory=list)
    reasons: list[str] = field(init=False, default_factory=list)
    cache: dict[tuple[int, ...], ProofCheckStatus] = field(
        init=False,
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        self.started = self.clock()

    def check(
        self,
        indices: tuple[int, ...],
        *,
        combination: bool,
    ) -> ProofCheckStatus | None:
        if indices in self.cache:
            return self.cache[indices]
        if self.proof_runs >= self.max_proof_runs:
            self.reasons.append("proof-run budget reached")
            return None
        if combination and self.combinations >= self.max_combinations:
            self.reasons.append("candidate-combination budget reached")
            return None
        elapsed = max(0.0, self.clock() - self.started)
        if elapsed >= self.max_duration_seconds:
            self.reasons.append("minimization duration budget reached")
            return None

        candidate = tuple(self.original[index] for index in indices)
        self.proof_runs += 1
        if combination:
            self.combinations += 1
        started = self.clock()
        detail = ""
        try:
            raw = self.proof_callback(candidate)
            status, detail = _normalize_proof(raw)
        except TimeoutError as error:
            status = ProofCheckStatus.TIMEOUT
            detail = f"proof callback timed out: {error}"
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            status = ProofCheckStatus.INVALID
            detail = f"proof callback failed: {type(error).__name__}: {error}"
        duration = max(0.0, self.clock() - started)
        if max(0.0, self.clock() - self.started) > self.max_duration_seconds:
            status = ProofCheckStatus.TIMEOUT
            detail = "proof callback exceeded the minimization duration budget"
        if status in {ProofCheckStatus.TIMEOUT, ProofCheckStatus.INVALID}:
            self.inconclusive = True
            self.reasons.append("at least one candidate proof was inconclusive")
        self.cache[indices] = status
        self.attempts.append(
            ProofAttempt(
                kept_group_ids=tuple(_group_id(group) for group in candidate),
                status=status,
                duration_seconds=duration,
                detail=detail,
            )
        )
        return status

    def result(
        self,
        current: tuple[int, ...],
        *,
        status: MinimizationStatus,
        complete: bool,
    ) -> PatchMinimizationResult:
        selected = set(current)
        minimized = tuple(self.original[index] for index in current)
        removed = tuple(group for index, group in enumerate(self.original) if index not in selected)
        return PatchMinimizationResult(
            status=status,
            original_groups=self.original,
            minimized_groups=minimized,
            removed_groups=removed,
            attempts=tuple(self.attempts),
            proof_runs=self.proof_runs,
            combinations=self.combinations,
            duration_seconds=max(0.0, self.clock() - self.started),
            complete=complete,
            reasons=tuple(dict.fromkeys(self.reasons)),
        )


def _partition(values: tuple[int, ...], count: int) -> tuple[tuple[int, ...], ...]:
    count = min(max(1, count), len(values))
    quotient, remainder = divmod(len(values), count)
    chunks: list[tuple[int, ...]] = []
    start = 0
    for index in range(count):
        size = quotient + (1 if index < remainder else 0)
        chunks.append(values[start : start + size])
        start += size
    return tuple(chunks)


def _normalize_proof(raw: Any) -> tuple[ProofCheckStatus, str]:
    if isinstance(raw, ProofCheckStatus):
        return raw, ""
    if isinstance(raw, bool):
        return (ProofCheckStatus.PROVEN if raw else ProofCheckStatus.NOT_PROVEN), ""
    if isinstance(raw, int):
        return (ProofCheckStatus.PROVEN if raw == 0 else ProofCheckStatus.NOT_PROVEN), ""
    if isinstance(raw, Mapping):
        if bool(raw.get("timed_out", False)):
            return ProofCheckStatus.TIMEOUT, str(raw.get("detail", ""))
        if not bool(raw.get("valid", True)):
            return ProofCheckStatus.INVALID, str(raw.get("detail", ""))
        if "proven" in raw:
            proven = bool(raw["proven"])
        elif "passed" in raw:
            proven = bool(raw["passed"])
        elif "verdict" in raw:
            proven = _verdict_is_proven(raw["verdict"])
        elif "returncode" in raw:
            proven = int(raw["returncode"]) == 0
        else:
            raise ValueError("mapping has no proven, passed, verdict, or returncode field")
        return (
            ProofCheckStatus.PROVEN if proven else ProofCheckStatus.NOT_PROVEN,
            str(raw.get("detail", "")),
        )

    if hasattr(raw, "valid") and not bool(raw.valid):
        return ProofCheckStatus.INVALID, str(getattr(raw, "detail", ""))
    if hasattr(raw, "causally_proven"):
        proven = bool(raw.causally_proven)
    elif hasattr(raw, "passed"):
        proven = bool(raw.passed)
    elif hasattr(raw, "verdict"):
        proven = _verdict_is_proven(raw.verdict)
    elif hasattr(raw, "returncode"):
        proven = int(raw.returncode) == 0
    else:
        raise TypeError("unsupported proof callback result")
    return (
        ProofCheckStatus.PROVEN if proven else ProofCheckStatus.NOT_PROVEN,
        str(getattr(raw, "detail", "")),
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


def _group_id(group: Any) -> str:
    if isinstance(group, PatchGroup):
        return group.id
    candidate = getattr(group, "id", getattr(group, "group_id", None))
    return str(candidate) if candidate is not None else str(group)


# Product-language aliases.
ProvenPatchMinimizer = PatchMinimizer
PatchMinimizerResult = PatchMinimizationResult


__all__ = [
    "MinimizationStatus",
    "PatchGroup",
    "PatchMinimizationResult",
    "PatchMinimizer",
    "PatchMinimizerResult",
    "ProofAttempt",
    "ProofCheckStatus",
    "ProvenPatchMinimizer",
]

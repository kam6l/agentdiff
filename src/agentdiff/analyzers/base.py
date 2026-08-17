"""Future-risk analyzer contracts and normalized findings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from agentdiff.scoring import RiskLevel


@dataclass(frozen=True, slots=True)
class ChangeView:
    """Bounded text view of one assessed filesystem mutation."""

    path: str
    change_type: str
    before_text: str | None
    after_text: str | None


@dataclass(frozen=True, slots=True)
class FutureRiskFinding:
    """One deferred execution or trusted-system effect."""

    path: str
    risk: RiskLevel
    trigger: str
    reason: str
    evidence: str
    confidence: str
    analyzer: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["risk"] = self.risk.value
        return value


class FutureRiskAnalyzer(Protocol):
    """Small deterministic analyzer plugin."""

    name: str

    def analyze(self, change: ChangeView) -> list[FutureRiskFinding]: ...


def finding(
    change: ChangeView,
    *,
    analyzer: str,
    risk: RiskLevel,
    trigger: str,
    reason: str,
    evidence: str,
    confidence: str = "high",
) -> FutureRiskFinding:
    return FutureRiskFinding(
        path=change.path,
        risk=risk,
        trigger=trigger,
        reason=reason,
        evidence=evidence,
        confidence=confidence,
        analyzer=analyzer,
    )

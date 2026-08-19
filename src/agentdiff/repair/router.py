"""The Human Attention Router.

AgentDiff should interrupt the human only when the trust boundary changes.
This router classifies a transaction/proof outcome deterministically:

- ``AUTO``   normal source change, proof passes
- ``RETRY``  proof fails but the repair stays inside the original scope
- ``HUMAN``  dependency added, CI changed, new scope requested, or high
             future risk

No model is consulted. The router is a pure function of deterministic
evidence (policy decisions, changed paths, risk scores).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentdiff.impact.impact import classify_risk
from agentdiff.policy import PolicyAction
from agentdiff.scoring import RiskLevel


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """One deterministic attention routing decision."""

    kind: str  # AUTO | RETRY | HUMAN
    reason: str
    proof_verdict: str | None = None
    attempt: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "proof_verdict": self.proof_verdict,
            "attempt": self.attempt,
        }


class HumanAttentionRouter:
    """Route a completed run to AUTO delivery, RETRY, or HUMAN review."""

    @staticmethod
    def route(
        *,
        changes: list[Any],
        safety_outcome: PolicyAction | str | None = None,
        future_level: str | None = None,
        proof_verdict: str | None = None,
        attempt: int = 0,
    ) -> RoutingDecision:
        """Classify one run deterministically.

        ``changes`` items must expose ``path`` and ``decision`` attributes
        (``ChangeAssessment`` or equivalent).
        """
        for change in changes:
            decision = getattr(change, "decision", None)
            if decision is None:
                continue
            action = decision.action if hasattr(decision, "action") else decision
            if action in {PolicyAction.DENY, "deny"}:
                return RoutingDecision(
                    "HUMAN",
                    f"protected change detected: {getattr(change, 'path', '?')}",
                    proof_verdict=proof_verdict,
                    attempt=attempt,
                )
            if action in {PolicyAction.REVIEW, "review"}:
                return RoutingDecision(
                    "HUMAN",
                    f"review-required change detected: {getattr(change, 'path', '?')}",
                    proof_verdict=proof_verdict,
                    attempt=attempt,
                )
            if classify_risk(getattr(change, "path", "")) == "full":
                return RoutingDecision(
                    "HUMAN",
                    f"high-risk path changed (dependencies/CI/config/security): "
                    f"{getattr(change, 'path', '?')}",
                    proof_verdict=proof_verdict,
                    attempt=attempt,
                )

        if future_level in {RiskLevel.HIGH.value, RiskLevel.CRITICAL.value, "high", "critical"}:
            return RoutingDecision(
                "HUMAN",
                f"high future blast radius: {future_level}",
                proof_verdict=proof_verdict,
                attempt=attempt,
            )

        if proof_verdict is not None and proof_verdict != "PROVEN":
            return RoutingDecision(
                "RETRY",
                "proof failed but repair stays in scope",
                proof_verdict=proof_verdict,
                attempt=attempt,
            )

        if safety_outcome not in {None, PolicyAction.ALLOW, "allow"}:
            return RoutingDecision(
                "HUMAN",
                f"policy outcome is not ALLOW: {safety_outcome}",
                proof_verdict=proof_verdict,
                attempt=attempt,
            )

        return RoutingDecision("AUTO", "normal source change with passing proof", attempt=attempt)

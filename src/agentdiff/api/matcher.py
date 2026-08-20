"""Rule matching and migration impact scoring for detected API usages."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Sequence

from agentdiff.api.models import (
    APIChange,
    APIUsage,
    ChangeSeverity,
    MatchedChange,
    MigrationImpact,
)
from agentdiff.api.providers import APIProvider, get_all_providers
from agentdiff.impact.impact import ImpactEngine
from agentdiff.scoring.blast_radius import (
    BlastRadiusResult,
    RiskComponent,
    RiskLevel,
)

if TYPE_CHECKING:
    from agentdiff.impact.impact import ProofImpactPlan

# Severity to risk point weighting
_SEVERITY_WEIGHTS: dict[ChangeSeverity, int] = {
    ChangeSeverity.CRITICAL: 35,
    ChangeSeverity.HIGH: 25,
    ChangeSeverity.MODERATE: 15,
    ChangeSeverity.LOW: 5,
    ChangeSeverity.INFO: 0,
}


def _calculate_risk_level(score: int) -> RiskLevel:
    """Map a 0-100 capped score to RiskLevel."""
    if score <= 20:
        return RiskLevel.LOW
    if score <= 50:
        return RiskLevel.MODERATE
    if score <= 75:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


class APIMatcher:
    """Matches detected API usages with known breaking changes and computes migration impact."""

    def __init__(
        self,
        providers: Sequence[APIProvider] | None = None,
        custom_changes: Sequence[APIChange] | None = None,
    ) -> None:
        self.providers: list[APIProvider] = (
            list(providers) if providers is not None else get_all_providers()
        )
        self.changes: list[APIChange] = (
            list(custom_changes) if custom_changes is not None else []
        )
        if not self.changes:
            for p in self.providers:
                self.changes.extend(p.get_known_changes())

    def match_usages(
        self,
        usages: Iterable[APIUsage],
    ) -> list[MatchedChange]:
        """Match a collection of API usages against the change catalog."""
        matched: list[MatchedChange] = []
        for usage in usages:
            provider = next((p for p in self.providers if p.name == usage.provider), None)
            for change in self.changes:
                if change.provider != usage.provider:
                    continue
                is_match = (
                    provider.match_usage(usage, change)
                    if provider is not None
                    else (change.target_symbol in usage.symbol)
                )
                if is_match:
                    points = _SEVERITY_WEIGHTS.get(change.severity, 10)
                    remediation = self._format_remediation(usage, change)
                    matched.append(
                        MatchedChange(
                            usage=usage,
                            change=change,
                            risk_points=points,
                            remediation_advice=remediation,
                        )
                    )
        return matched

    def calculate_impact(
        self,
        usages: Sequence[APIUsage],
        root: str | Path | None = None,
    ) -> MigrationImpact:
        """Analyze detected API usages, match breaking changes, and compute blast radius."""
        matched = self.match_usages(usages)

        affected_files = tuple(
            sorted({m.usage.filepath for m in matched if m.usage.filepath})
        )

        counts: dict[str, int] = {
            "total_usages": len(usages),
            "affected_usages": len(matched),
            "critical_changes": sum(
                1 for m in matched if m.change.severity == ChangeSeverity.CRITICAL
            ),
            "high_changes": sum(
                1 for m in matched if m.change.severity == ChangeSeverity.HIGH
            ),
            "moderate_changes": sum(
                1 for m in matched if m.change.severity == ChangeSeverity.MODERATE
            ),
            "low_changes": sum(
                1
                for m in matched
                if m.change.severity in {ChangeSeverity.LOW, ChangeSeverity.INFO}
            ),
        }

        components: list[RiskComponent] = []
        raw_score = 0

        for sev in (
            ChangeSeverity.CRITICAL,
            ChangeSeverity.HIGH,
            ChangeSeverity.MODERATE,
            ChangeSeverity.LOW,
        ):
            sev_matches = [m for m in matched if m.change.severity == sev]
            if sev_matches:
                weight = _SEVERITY_WEIGHTS[sev]
                count = len(sev_matches)
                pts = count * weight
                raw_score += pts
                components.append(
                    RiskComponent(
                        name=f"api_change_{sev.value}",
                        count=count,
                        weight=weight,
                        points=pts,
                        detail=f"{count} {sev.value}-severity API breaking change(s) detected",
                    )
                )

        capped_score = min(100, raw_score)
        risk_level = _calculate_risk_level(capped_score)

        blast_radius = BlastRadiusResult(
            score=capped_score,
            raw_score=raw_score,
            level=risk_level,
            counts=counts,
            components=components,
        )

        impact_plan: ProofImpactPlan | None = None
        if root is not None and Path(root).is_dir():
            try:
                engine = ImpactEngine(root)
                impact_plan = engine.plan(affected_files)
            except (OSError, RuntimeError, ValueError, KeyError):
                impact_plan = None

        remediations = tuple(
            dict.fromkeys(m.remediation_advice for m in matched if m.remediation_advice)
        )

        return MigrationImpact(
            total_usages=len(usages),
            affected_usages=len(matched),
            affected_files=affected_files,
            matched_changes=tuple(matched),
            blast_radius=blast_radius,
            impact_plan=impact_plan,
            risk_level=risk_level,
            remediations=remediations,
        )

    def _format_remediation(self, usage: APIUsage, change: APIChange) -> str:
        """Format human-actionable migration advice."""
        loc = f"{usage.filepath}:{usage.line_number}" if usage.filepath else "codebase"
        advice = [f"[{change.severity.value.upper()}] {loc} - {change.title}"]
        if change.replacement_symbol:
            advice.append(f"  Migrate to: `{change.replacement_symbol}`")
        if change.replacement_code:
            snippet = "\n    ".join(change.replacement_code.splitlines())
            advice.append(f"  Example:\n    {snippet}")
        if change.migration_guide_url:
            advice.append(f"  Docs: {change.migration_guide_url}")
        return "\n".join(advice)

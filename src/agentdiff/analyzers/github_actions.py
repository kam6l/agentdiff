"""Deferred execution analysis for GitHub Actions workflows."""

from __future__ import annotations

import re

from agentdiff.scoring import RiskLevel

from .base import ChangeView, FutureRiskFinding, finding


class GitHubActionsAnalyzer:
    name = "github_actions"

    def analyze(self, change: ChangeView) -> list[FutureRiskFinding]:
        if not (
            change.path.startswith(".github/workflows/") and change.path.endswith((".yml", ".yaml"))
        ):
            return []
        text = change.after_text or ""
        critical = re.search(
            (
                r"(?mi)^\s*(?:-\s*)?(?:run|pull_request_target)\s*:|"
                r"^\s*permissions\s*:\s*write-all"
            ),
            text,
        )
        risk = RiskLevel.CRITICAL if critical else RiskLevel.HIGH
        reason = (
            "workflow adds or changes an executable command or privileged trigger"
            if critical
            else "workflow definition can execute on a future repository event"
        )
        return [
            finding(
                change,
                analyzer=self.name,
                risk=risk,
                trigger="future GitHub workflow event",
                reason=reason,
                evidence="workflow path changed; executable YAML keys inspected",
            )
        ]

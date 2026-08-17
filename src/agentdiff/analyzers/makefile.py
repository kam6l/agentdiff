"""Deferred execution analysis for Make recipes."""

from __future__ import annotations

import re

from agentdiff.scoring import RiskLevel

from .base import ChangeView, FutureRiskFinding, finding


class MakefileAnalyzer:
    name = "makefile"

    def analyze(self, change: ChangeView) -> list[FutureRiskFinding]:
        if change.path.rsplit("/", 1)[-1].lower() not in {"makefile", "gnumakefile"}:
            return []
        if not re.search(r"(?m)^\t\S", change.after_text or ""):
            return []
        return [
            finding(
                change,
                analyzer=self.name,
                risk=RiskLevel.HIGH,
                trigger="future make target invocation",
                reason="Make recipe commands changed",
                evidence="one or more recipe lines detected",
            )
        ]

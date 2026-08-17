"""Deferred execution analysis for Python build metadata."""

from __future__ import annotations

import re

from agentdiff.scoring import RiskLevel

from .base import ChangeView, FutureRiskFinding, finding


class PythonBuildAnalyzer:
    name = "python_build"

    def analyze(self, change: ChangeView) -> list[FutureRiskFinding]:
        if change.path.rsplit("/", 1)[-1].lower() != "pyproject.toml":
            return []
        before = change.before_text or ""
        after = change.after_text or ""
        keys = (
            "build-backend",
            "[build-system]",
            "[project.scripts]",
            "[project.entry-points",
        )
        touched = [key for key in keys if key in after and after != before]
        if not touched:
            return []
        executable = re.search(r"(?m)^\s*build-backend\s*=|^\s*\[project\.scripts\]", after)
        return [
            finding(
                change,
                analyzer=self.name,
                risk=RiskLevel.HIGH if executable else RiskLevel.MODERATE,
                trigger="Python build, installation, or entry-point invocation",
                reason="Python executable build metadata changed",
                evidence=f"matched metadata section(s): {', '.join(touched)}",
            )
        ]

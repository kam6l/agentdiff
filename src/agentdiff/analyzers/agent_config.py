"""Deferred execution analysis for trusted agent instruction/configuration files."""

from __future__ import annotations

import re

from agentdiff.scoring import RiskLevel

from .base import ChangeView, FutureRiskFinding, finding


class AgentConfigAnalyzer:
    name = "agent_config"

    def analyze(self, change: ChangeView) -> list[FutureRiskFinding]:
        lowered = change.path.lower()
        relevant = (
            lowered in {"agents.md", "claude.md"}
            or lowered.startswith((".codex/", ".claude/", ".githooks/"))
            or lowered in {".gitconfig", ".gitmodules"}
        )
        if not relevant:
            return []
        text = change.after_text or ""
        executable = re.search(
            r"(?i)\b(?:command|shell|execute|permission|allow|hook|tool)\b",
            text,
        )
        return [
            finding(
                change,
                analyzer=self.name,
                risk=RiskLevel.HIGH if executable else RiskLevel.MODERATE,
                trigger="future agent, Git hook, or trusted-tool session",
                reason="trusted instruction or automation configuration changed",
                evidence=(
                    "execution/permission vocabulary detected"
                    if executable
                    else "trusted configuration path changed"
                ),
                confidence="medium",
            )
        ]

"""Deferred execution analysis for container and dev-container definitions."""

from __future__ import annotations

import re

from agentdiff.scoring import RiskLevel

from .base import ChangeView, FutureRiskFinding, finding


class ContainerAnalyzer:
    name = "container"

    def analyze(self, change: ChangeView) -> list[FutureRiskFinding]:
        name = change.path.rsplit("/", 1)[-1].lower()
        relevant = (
            name == "dockerfile"
            or name.startswith("dockerfile.")
            or name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
            or change.path.startswith(".devcontainer/")
        )
        if not relevant:
            return []
        text = change.after_text or ""
        critical = re.search(
            r"(?mi)privileged\s*:\s*true|/var/run/docker\.sock|network_mode\s*:\s*host",
            text,
        )
        executable = re.search(
            r"(?mi)^\s*(?:RUN|CMD|ENTRYPOINT)\b|postCreateCommand|postStartCommand|\bcommand\s*:",
            text,
        )
        risk = (
            RiskLevel.CRITICAL
            if critical
            else (RiskLevel.HIGH if executable else RiskLevel.MODERATE)
        )
        return [
            finding(
                change,
                analyzer=self.name,
                risk=risk,
                trigger="future image build or container/dev-container start",
                reason="container execution or privilege configuration changed",
                evidence="container control keys inspected without persisting command bodies",
            )
        ]

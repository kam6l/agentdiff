"""Deferred execution analysis for JavaScript package scripts."""

from __future__ import annotations

import json

from agentdiff.scoring import RiskLevel

from .base import ChangeView, FutureRiskFinding, finding

_LIFECYCLE = {"preinstall", "install", "postinstall", "prepare", "prepublish"}


class PackageScriptsAnalyzer:
    name = "package_scripts"

    @staticmethod
    def _scripts(text: str | None) -> dict[str, str]:
        if text is None:
            return {}
        try:
            raw = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {}
        scripts = raw.get("scripts", {}) if isinstance(raw, dict) else {}
        if not isinstance(scripts, dict):
            return {}
        return {str(key): str(value) for key, value in scripts.items()}

    def analyze(self, change: ChangeView) -> list[FutureRiskFinding]:
        if change.path.rsplit("/", 1)[-1].lower() != "package.json":
            return []
        before = self._scripts(change.before_text)
        after = self._scripts(change.after_text)
        modified = sorted(key for key, value in after.items() if before.get(key) != value)
        if not modified:
            return []
        lifecycle = sorted(set(modified) & _LIFECYCLE)
        risk = RiskLevel.CRITICAL if lifecycle else RiskLevel.HIGH
        trigger = "npm install" if lifecycle else "npm run / package tooling"
        reason = (
            f"new or changed install lifecycle script(s): {', '.join(lifecycle)}"
            if lifecycle
            else f"new or changed executable package script(s): {', '.join(modified)}"
        )
        return [
            finding(
                change,
                analyzer=self.name,
                risk=risk,
                trigger=trigger,
                reason=reason,
                evidence="script names compared; command bodies are not copied into evidence",
            )
        ]

"""Deferred execution analysis for editor task configuration."""

from __future__ import annotations

import json

from agentdiff.scoring import RiskLevel

from .base import ChangeView, FutureRiskFinding, finding


class EditorTasksAnalyzer:
    name = "editor_tasks"

    def analyze(self, change: ChangeView) -> list[FutureRiskFinding]:
        if change.path != ".vscode/tasks.json":
            return []
        try:
            payload = json.loads(change.after_text or "{}")
        except json.JSONDecodeError:
            payload = {}
        tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
        executable = any(
            isinstance(task, dict) and any(key in task for key in ("command", "args"))
            for task in tasks
        )
        return [
            finding(
                change,
                analyzer=self.name,
                risk=RiskLevel.HIGH if executable else RiskLevel.MODERATE,
                trigger="future editor task invocation",
                reason="VS Code task configuration changed",
                evidence="task command keys detected" if executable else "tasks file changed",
            )
        ]

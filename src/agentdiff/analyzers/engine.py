"""Analyzer registry and deterministic Future Blast Radius scoring."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from agentdiff.pathing import normalize_relative_path
from agentdiff.scoring import RiskLevel

from .agent_config import AgentConfigAnalyzer
from .base import ChangeView, FutureRiskAnalyzer, FutureRiskFinding
from .container import ContainerAnalyzer
from .editor_tasks import EditorTasksAnalyzer
from .github_actions import GitHubActionsAnalyzer
from .makefile import MakefileAnalyzer
from .package_scripts import PackageScriptsAnalyzer
from .python_build import PythonBuildAnalyzer

_RISK_POINTS = {
    RiskLevel.LOW: 20,
    RiskLevel.MODERATE: 40,
    RiskLevel.HIGH: 70,
    RiskLevel.CRITICAL: 90,
}
_MAX_TEXT_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class FutureBlastResult:
    """Separate deferred-execution score; never merged with immediate risk."""

    score: int
    level: RiskLevel
    findings: tuple[FutureRiskFinding, ...]
    analyzers: tuple[str, ...]
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "score": self.score,
            "level": self.level.value,
            "findings": [finding.to_dict() for finding in self.findings],
            "analyzers": list(self.analyzers),
        }


class FutureBlastEngine:
    """Run independent deterministic analyzers over bounded before/after text."""

    def __init__(self, analyzers: Iterable[FutureRiskAnalyzer] | None = None) -> None:
        selected = analyzers or (
            GitHubActionsAnalyzer(),
            PackageScriptsAnalyzer(),
            PythonBuildAnalyzer(),
            ContainerAnalyzer(),
            MakefileAnalyzer(),
            EditorTasksAnalyzer(),
            AgentConfigAnalyzer(),
        )
        self.analyzers = tuple(selected)

    def analyze(
        self,
        changes: Iterable[Any],
        *,
        before_root: str | Path,
        after_root: str | Path,
    ) -> FutureBlastResult:
        before = Path(before_root).resolve(strict=True)
        after = Path(after_root).resolve(strict=True)
        findings: list[FutureRiskFinding] = []
        for change in sorted(changes, key=lambda item: item.path):
            view = ChangeView(
                path=change.path,
                change_type=change.change_type,
                before_text=self._read_text(before, change.path),
                after_text=self._read_text(after, change.path),
            )
            for analyzer in self.analyzers:
                findings.extend(analyzer.analyze(view))
        findings.sort(key=lambda item: (item.path, item.analyzer, item.reason))
        if findings:
            highest = max(_RISK_POINTS[item.risk] for item in findings)
            score = min(100, highest + min(10, max(0, len(findings) - 1) * 2))
        else:
            score = 0
        return FutureBlastResult(
            score=score,
            level=self._level(score),
            findings=tuple(findings),
            analyzers=tuple(analyzer.name for analyzer in self.analyzers),
        )

    @staticmethod
    def _level(score: int) -> RiskLevel:
        if score <= 20:
            return RiskLevel.LOW
        if score <= 40:
            return RiskLevel.MODERATE
        if score <= 70:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    @staticmethod
    def _read_text(root: Path, relative: str) -> str | None:
        normalized = normalize_relative_path(relative)
        path = root.joinpath(*normalized.split("/"))
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > _MAX_TEXT_BYTES:
            return None
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != info.st_dev
                or opened.st_ino != info.st_ino
            ):
                return None
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read(_MAX_TEXT_BYTES + 1)
            if len(payload) > _MAX_TEXT_BYTES:
                return None
            return payload.decode("utf-8", "replace")
        except OSError:
            return None
        finally:
            os.close(descriptor)

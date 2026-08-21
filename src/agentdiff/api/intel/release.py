"""SDK release analyzer: extract API changes from SDK release metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agentdiff.api.models import ChangeSeverity, ChangeType


@dataclass(frozen=True, slots=True)
class SDKReleaseChange:
    """One API change extracted from an SDK release note."""

    version: str
    title: str
    body: str
    change_type: ChangeType
    severity: ChangeSeverity

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "title": self.title,
            "body": self.body,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
        }


class SDKReleaseAnalyzer:
    """Analyze SDK release notes (changelog entries grouped by version)."""

    def __init__(self, provider: str, library: str) -> None:
        self.provider = provider
        self.library = library

    def analyze(self, content: str) -> list[SDKReleaseChange]:
        """Parse release notes into per-version API changes."""
        changes: list[SDKReleaseChange] = []
        current_version = ""

        for line in content.splitlines():
            stripped = line.strip()
            version = self._extract_version(stripped)
            if version:
                current_version = version
                continue
            if current_version and stripped:
                entry = stripped.lstrip("-*+ ").strip()
                lowered = entry.lower()
                if any(
                    marker in lowered
                    for marker in ("breaking", "removed", "deprecated", "migration")
                ):
                    change_type = self._classify(entry)
                    severity = (
                        ChangeSeverity.HIGH
                        if change_type == ChangeType.REMOVAL
                        else ChangeSeverity.MODERATE
                    )
                    changes.append(
                        SDKReleaseChange(
                            version=current_version,
                            title=entry,
                            body="",
                            change_type=change_type,
                            severity=severity,
                        )
                    )
        return changes

    @staticmethod
    def _extract_version(line: str) -> str:
        # Allow markdown heading prefixes: "## 1.0.0", "## [1.0.0](url)", "v1.0.0"
        cleaned = line.lstrip("#").strip()
        cleaned = cleaned.split("]", 1)[-1] if cleaned.startswith("[") else cleaned
        match = re.match(r"^[vV]?(\d+\.\d+\.\d+(?:[-+][\w.-]+)?)", cleaned)
        return match.group(1) if match else ""

    @staticmethod
    def _classify(text: str) -> ChangeType:
        lowered = text.lower()
        if "removed" in lowered or "deleted" in lowered:
            return ChangeType.REMOVAL
        if "deprecated" in lowered:
            return ChangeType.DEPRECATION
        return ChangeType.BEHAVIOR_CHANGE

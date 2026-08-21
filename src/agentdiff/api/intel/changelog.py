"""Changelog parser: extract API changes from markdown changelogs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agentdiff.api.models import ChangeSeverity, ChangeType

_BREAKING_MARKERS = (
    "breaking",
    "removed",
    "migration required",
    "not backwards compatible",
    "major change",
)

_REMOVAL_RE = re.compile(r"\b(removed|deleted|dropped)\b", re.IGNORECASE)
_DEPRECATION_RE = re.compile(r"\b(deprecated|deprecation)\b", re.IGNORECASE)
_RENAME_RE = re.compile(r"\b(renamed|rename)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ChangelogChange:
    """One API-affecting change extracted from a changelog entry."""

    title: str
    body: str
    section: str  # e.g. "Breaking Changes", "Deprecated"
    change_type: ChangeType
    severity: ChangeSeverity
    mentions: tuple[str, ...] = ()  # symbols/words mentioned in the entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "section": self.section,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "mentions": list(self.mentions),
        }


def _classify_type(text: str) -> ChangeType:
    lowered = text.lower()
    if _REMOVAL_RE.search(lowered) or "removed" in lowered:
        return ChangeType.REMOVAL
    if _DEPRECATION_RE.search(lowered):
        return ChangeType.DEPRECATION
    if _RENAME_RE.search(lowered):
        return ChangeType.RENAME
    return ChangeType.BEHAVIOR_CHANGE


def _classify_severity(text: str, section: str) -> ChangeSeverity:
    """Classify severity from the entry text; the section only boosts when the
    entry itself carries no explicit severity signal."""
    lowered = text.lower()
    if any(marker in lowered for marker in _BREAKING_MARKERS):
        return ChangeSeverity.CRITICAL if "removed" in lowered else ChangeSeverity.HIGH
    if "deprecated" in lowered:
        return ChangeSeverity.MODERATE
    # Low-signal entry: let the section heading decide.
    section_lowered = section.lower()
    if any(marker in section_lowered for marker in _BREAKING_MARKERS):
        return ChangeSeverity.HIGH
    return ChangeSeverity.LOW


class ChangelogParser:
    """Parse a markdown changelog into API change candidates."""

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def parse(self, content: str) -> list[ChangelogChange]:
        """Parse changelog markdown and return structured changes."""
        changes: list[ChangelogChange] = []
        sections: list[tuple[str, str]] = []

        # Split into sections (## headings) with their body text
        current_section = "Uncategorized"
        current_body: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("## ") or stripped.startswith("# "):
                if current_body:
                    sections.append((current_section, "\n".join(current_body)))
                current_section = stripped.lstrip("# ").strip()
                current_body = []
            else:
                current_body.append(line)
        if current_body:
            sections.append((current_section, "\n".join(current_body)))

        for section, body in sections:
            for entry in self._split_entries(body):
                title, entry_body = self._entry_parts(entry)
                if not title:
                    continue
                change_type = _classify_type(f"{title} {entry_body}")
                severity = _classify_severity(f"{title} {entry_body}", section)
                mentions = tuple(
                    dict.fromkeys(re.findall(r"[a-zA-Z_][a-zA-Z0-9_.]*", f"{title} {entry_body}"))
                )
                changes.append(
                    ChangelogChange(
                        title=title,
                        body=entry_body,
                        section=section,
                        change_type=change_type,
                        severity=severity,
                        mentions=mentions,
                    )
                )
        return changes

    @staticmethod
    def _split_entries(body: str) -> list[str]:
        """Split a section body into bullet/list entries."""
        entries: list[str] = []
        current: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(("- ", "* ", "+ ")):
                if current:
                    entries.append("\n".join(current))
                current = [stripped[2:].strip()]
            elif stripped:
                current.append(line)
        if current:
            entries.append("\n".join(current))
        return entries

    @staticmethod
    def _entry_parts(entry: str) -> tuple[str, str]:
        lines = entry.splitlines()
        title = lines[0].strip() if lines else ""
        rest = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        return title, rest

"""Provider intelligence engine: turns upstream signals into manifest candidates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentdiff.api.intel.changelog import ChangelogParser
from agentdiff.api.intel.openapi import OpenAPIDiffAnalyzer
from agentdiff.api.intel.release import SDKReleaseAnalyzer
from agentdiff.api.manifest import (
    AffectedSymbols,
    APIChangeManifest,
    ManifestSource,
    MigrationStrategyConfig,
    MigrationStrategyType,
    ReplacementSymbols,
    SourceType,
)
from agentdiff.api.models import ChangeSeverity, ChangeType


@dataclass(frozen=True, slots=True)
class ManifestCandidate:
    """A suggested manifest before validation. AI output — never applied directly."""

    provider: str
    change_id: str
    title: str
    change_type: ChangeType
    severity: ChangeSeverity
    affected_symbols: tuple[str, ...]
    replacement_symbols: tuple[str, ...] = ()
    source_type: SourceType = SourceType.CUSTOM
    source_url: str = ""
    description: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "change_id": self.change_id,
            "title": self.title,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "affected_symbols": list(self.affected_symbols),
            "replacement_symbols": list(self.replacement_symbols),
            "source_type": self.source_type.value,
            "source_url": self.source_url,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class IntelArtifact:
    """What was analyzed and what it produced."""

    kind: str  # "changelog" | "openapi_diff" | "sdk_release" | "ai_suggestion"
    input_path: str
    candidates: tuple[ManifestCandidate, ...]
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "input_path": self.input_path,
            "candidates": [c.to_dict() for c in self.candidates],
            "generated_at": self.generated_at,
        }


class ProviderIntelEngine:
    """Analyze provider signals and produce validated manifest candidates."""

    def __init__(self, provider: str, library: str = "") -> None:
        self.provider = provider
        self.library = library or provider

    # -- per-source analyzers ------------------------------------------------

    def from_changelog(self, path: str | Path) -> IntelArtifact:
        parser = ChangelogParser(self.provider)
        raw = Path(path).read_text(encoding="utf-8")
        entries = parser.parse(raw)
        candidates: list[ManifestCandidate] = []
        for entry in entries:
            if entry.change_type in {ChangeType.REMOVAL, ChangeType.DEPRECATION, ChangeType.RENAME}:
                candidates.append(
                    ManifestCandidate(
                        provider=self.provider,
                        change_id=self._slugify(f"{entry.change_type.value}-{entry.title}"),
                        title=entry.title,
                        change_type=entry.change_type,
                        severity=entry.severity,
                        affected_symbols=self._mentions_to_symbols(entry.mentions),
                        source_type=SourceType.CHANGELOG,
                        source_url="",
                        description=entry.body,
                        confidence=0.7,
                    )
                )
        return IntelArtifact(
            kind="changelog",
            input_path=str(path),
            candidates=tuple(candidates),
            generated_at=self._now(),
        )

    def from_openapi_diff(
        self,
        before: str | Path | dict[str, Any],
        after: str | Path | dict[str, Any],
    ) -> IntelArtifact:
        analyzer = OpenAPIDiffAnalyzer(self.provider)
        changes = analyzer.diff(before, after)
        candidates = [
            ManifestCandidate(
                provider=self.provider,
                change_id=self._slugify(f"{c.change_type.value}-{c.operation_id or c.path}"),
                title=f"{c.method.upper()} {c.path}: {c.detail}",
                change_type=c.change_type,
                severity=c.severity,
                affected_symbols=tuple(x for x in (c.operation_id,) if x),
                source_type=SourceType.OFFICIAL_DOCS,
                source_url="",
                description=c.detail,
                confidence=0.8,
            )
            for c in changes
        ]
        return IntelArtifact(
            kind="openapi_diff",
            input_path="<in-memory diff>" if isinstance(before, dict) else str(before),
            candidates=tuple(candidates),
            generated_at=self._now(),
        )

    def from_sdk_release(self, path: str | Path) -> IntelArtifact:
        analyzer = SDKReleaseAnalyzer(self.provider, self.library)
        content = Path(path).read_text(encoding="utf-8")
        changes = analyzer.analyze(content)
        candidates = [
            ManifestCandidate(
                provider=self.provider,
                change_id=self._slugify(f"{c.change_type.value}-{c.title}"),
                title=c.title,
                change_type=c.change_type,
                severity=c.severity,
                affected_symbols=(),
                source_type=SourceType.SDK_RELEASE,
                source_url="",
                description=c.body,
                confidence=0.6,
            )
            for c in changes
        ]
        return IntelArtifact(
            kind="sdk_release",
            input_path=str(path),
            candidates=tuple(candidates),
            generated_at=self._now(),
        )

    def from_ai_suggestion(
        self,
        suggestion: dict[str, Any],
    ) -> IntelArtifact:
        """Accept an AI-suggested manifest. It is ONLY a candidate: it must be
        deterministically validated before it can drive migrations, and the AI
        never touches code."""
        # Reject incomplete suggestions: an empty candidate is worse than none.
        if not suggestion.get("change_id") or not suggestion.get("affected_symbols"):
            return IntelArtifact(
                kind="ai_suggestion",
                input_path="<ai suggestion>",
                candidates=(),
                generated_at=self._now(),
            )
        try:
            candidate = ManifestCandidate(
                provider=str(suggestion["provider"]),
                change_id=str(suggestion.get("change_id", "")),
                title=str(suggestion.get("title", "")),
                change_type=ChangeType(suggestion.get("change_type", "behavior_change")),
                severity=ChangeSeverity(suggestion.get("severity", "low")),
                affected_symbols=tuple(suggestion.get("affected_symbols", ())),
                replacement_symbols=tuple(suggestion.get("replacement_symbols", ())),
                source_type=SourceType(suggestion.get("source_type", "custom")),
                source_url=str(suggestion.get("source_url", "")),
                description=str(suggestion.get("description", "")),
                confidence=float(suggestion.get("confidence", 0.5)),
            )
        except (KeyError, ValueError, TypeError) as error:
            del error
            return IntelArtifact(
                kind="ai_suggestion",
                input_path="<ai suggestion>",
                candidates=(),
                generated_at=self._now(),
            )
        return IntelArtifact(
            kind="ai_suggestion",
            input_path="<ai suggestion>",
            candidates=(candidate,),
            generated_at=self._now(),
        )

    # -- validation / promotion ---------------------------------------------

    def validate_candidate(self, candidate: ManifestCandidate) -> tuple[bool, list[str]]:
        """Deterministically validate a candidate before it becomes a manifest."""
        errors: list[str] = []
        if not candidate.provider:
            errors.append("provider is required")
        if not candidate.change_id:
            errors.append("change_id is required")
        if not candidate.affected_symbols:
            errors.append("at least one affected symbol is required")
        if not 0.0 <= candidate.confidence <= 1.0:
            errors.append("confidence must be between 0.0 and 1.0")
        return len(errors) == 0, errors

    def candidate_to_manifest(self, candidate: ManifestCandidate) -> APIChangeManifest:
        """Convert a validated candidate into a real manifest."""
        valid, errors = self.validate_candidate(candidate)
        if not valid:
            raise ValueError(f"invalid manifest candidate: {errors}")

        strategy = MigrationStrategyConfig(
            primary=(
                MigrationStrategyType.AST_TRANSFORM
                if candidate.confidence >= 0.7
                else MigrationStrategyType.CODING_AGENT
            ),
            fallback=MigrationStrategyType.MANUAL,
        )
        return APIChangeManifest(
            provider=candidate.provider,
            change_id=candidate.change_id,
            title=candidate.title,
            change_type=candidate.change_type,
            severity=candidate.severity,
            description=candidate.description,
            source=ManifestSource(
                type=candidate.source_type,
                url=candidate.source_url,
                retrieved_at=self._now(),
            ),
            affected=AffectedSymbols(symbols=candidate.affected_symbols),
            replacement=ReplacementSymbols(symbols=candidate.replacement_symbols),
            strategy=strategy,
            confidence=candidate.confidence,
        )

    def save_artifact(self, artifact: IntelArtifact, output_dir: str | Path) -> Path:
        """Persist an analysis artifact as JSON for auditability."""
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        safe_kind = self._slugify(artifact.kind)
        path = output / f"{safe_kind}-{int(datetime.now(timezone.utc).timestamp())}.json"
        path.write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=True) + "\n")
        return path

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
        return slug[:80] or "change"

    @staticmethod
    def _mentions_to_symbols(mentions: tuple[str, ...]) -> tuple[str, ...]:
        # Heuristic: keep likely dotted symbol names, drop common noise words.
        stop = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "for",
            "with",
            "now",
            "new",
            "api",
            "sdk",
            "version",
            "breaking",
            "changes",
            "change",
            "deprecated",
            "removed",
            "release",
            "migration",
            "from",
            "to",
            "will",
            "is",
            "are",
        }
        return tuple(
            dict.fromkeys(m for m in mentions if "." in m or (m not in stop and len(m) > 2))
        )

"""Data models for external API usage detection, change matching, and migration impact."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentdiff.impact.impact import ProofImpactPlan
    from agentdiff.scoring.blast_radius import BlastRadiusResult
from agentdiff.scoring.blast_radius import RiskLevel


class ChangeSeverity(str, Enum):
    """Severity of an API change / deprecation."""

    INFO = "info"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeType(str, Enum):
    """Classification of the API breaking change or migration rule."""

    DEPRECATION = "deprecation"
    REMOVAL = "removal"
    RENAME = "rename"
    SIGNATURE_CHANGE = "signature_change"
    PARAMETER_REMOVAL = "parameter_removal"
    BEHAVIOR_CHANGE = "behavior_change"
    MODEL_DEPRECATION = "model_deprecation"


@dataclass(frozen=True, slots=True)
class APIUsage:
    """Detected external API usage in source code."""

    provider: str  # e.g. "openai", "stripe"
    library: str  # e.g. "openai", "stripe"
    symbol: str  # e.g. "openai.ChatCompletion.create", "stripe.Charge.create"
    call_type: str  # "call", "import", "attribute", "instantiation"
    filepath: str
    line_number: int
    column: int = 0
    arguments: tuple[str, ...] = ()
    keyword_arguments: dict[str, str] = field(default_factory=dict)
    code_snippet: str = ""
    enclosing_scope: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "library": self.library,
            "symbol": self.symbol,
            "call_type": self.call_type,
            "filepath": self.filepath,
            "line_number": self.line_number,
            "column": self.column,
            "arguments": list(self.arguments),
            "keyword_arguments": dict(self.keyword_arguments),
            "code_snippet": self.code_snippet,
            "enclosing_scope": self.enclosing_scope,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> APIUsage:
        return cls(
            provider=str(data["provider"]),
            library=str(data["library"]),
            symbol=str(data["symbol"]),
            call_type=str(data.get("call_type", "call")),
            filepath=str(data["filepath"]),
            line_number=int(data["line_number"]),
            column=int(data.get("column", 0)),
            arguments=tuple(data.get("arguments", ())),
            keyword_arguments=dict(data.get("keyword_arguments", {})),
            code_snippet=str(data.get("code_snippet", "")),
            enclosing_scope=str(data.get("enclosing_scope", "")),
        )


@dataclass(frozen=True, slots=True)
class APIChange:
    """A known API breaking change, deprecation, or migration rule."""

    change_id: str
    provider: str
    title: str
    change_type: ChangeType
    severity: ChangeSeverity
    target_symbol: str
    description: str
    target_symbols: tuple[str, ...] = ()
    target_parameter: str | None = None
    target_model: str | None = None
    breaking_version: str = ""
    migration_guide_url: str = ""
    replacement_symbol: str = ""
    replacement_code: str = ""

    @property
    def applicable_symbols(self) -> tuple[str, ...]:
        return self.target_symbols if self.target_symbols else (self.target_symbol,)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "provider": self.provider,
            "title": self.title,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "target_symbol": self.target_symbol,
            "target_symbols": list(self.target_symbols),
            "target_parameter": self.target_parameter,
            "target_model": self.target_model,
            "breaking_version": self.breaking_version,
            "description": self.description,
            "migration_guide_url": self.migration_guide_url,
            "replacement_symbol": self.replacement_symbol,
            "replacement_code": self.replacement_code,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> APIChange:
        target_symbols_raw = data.get("target_symbols")
        target_symbols = tuple(str(s) for s in target_symbols_raw) if target_symbols_raw else ()
        return cls(
            change_id=str(data["change_id"]),
            provider=str(data["provider"]),
            title=str(data["title"]),
            change_type=ChangeType(data["change_type"]),
            severity=ChangeSeverity(data["severity"]),
            target_symbol=str(data["target_symbol"]),
            description=str(data.get("description", "")),
            target_symbols=target_symbols,
            target_parameter=data.get("target_parameter"),
            target_model=data.get("target_model"),
            breaking_version=str(data.get("breaking_version", "")),
            migration_guide_url=str(data.get("migration_guide_url", "")),
            replacement_symbol=str(data.get("replacement_symbol", "")),
            replacement_code=str(data.get("replacement_code", "")),
        )


@dataclass(frozen=True, slots=True)
class MatchedChange:
    """Pairing of a detected API usage with an applicable APIChange."""

    usage: APIUsage
    change: APIChange
    risk_points: int
    remediation_advice: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "usage": self.usage.to_dict(),
            "change": self.change.to_dict(),
            "risk_points": self.risk_points,
            "remediation_advice": self.remediation_advice,
        }


@dataclass(frozen=True, slots=True)
class MigrationImpact:
    """Comprehensive impact, risk score, and proof requirements for detected API changes."""

    total_usages: int
    affected_usages: int
    affected_files: tuple[str, ...]
    matched_changes: tuple[MatchedChange, ...]
    blast_radius: BlastRadiusResult
    impact_plan: ProofImpactPlan | None = None
    risk_level: RiskLevel = RiskLevel.LOW
    remediations: tuple[str, ...] = ()
    detected_sdk_versions: dict[str, Any] = field(default_factory=dict)
    impact_status: str = "ok"  # "ok", "unknown", "error", "skipped"
    impact_error: str | None = None

    @property
    def has_breaking_changes(self) -> bool:
        return self.affected_usages > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "total_usages": self.total_usages,
            "affected_usages": self.affected_usages,
            "affected_files": list(self.affected_files),
            "matched_changes": [mc.to_dict() for mc in self.matched_changes],
            "blast_radius": self.blast_radius.to_dict(),
            "impact_plan": self.impact_plan.to_dict() if self.impact_plan is not None else None,
            "risk_level": self.risk_level.value,
            "remediations": list(self.remediations),
            "detected_sdk_versions": dict(self.detected_sdk_versions),
            "impact_status": self.impact_status,
            "impact_error": self.impact_error,
        }

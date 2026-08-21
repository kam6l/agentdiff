"""Data models for external API usage detection, change matching, and migration impact."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentdiff.api.manifest import APIChangeManifest
    from agentdiff.impact.impact import ProofImpactPlan
    from agentdiff.scoring.blast_radius import BlastRadiusResult
    from agentdiff.trust.graph import RepoImpactGraph
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

    @property
    def verification_confidence(self) -> str:
        """Return verification confidence level based on test coverage."""
        if self.impact_plan is None:
            return "UNKNOWN"
        if not self.impact_plan.affected_code_has_tests:
            return "LOW"
        if self.impact_plan.level == "full":
            return "HIGH"
        if self.impact_plan.level == "targeted":
            return "MEDIUM"
        return "LOW"

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
            "verification_confidence": self.verification_confidence,
        }


class MigrationConfidence(str, Enum):
    """Confidence level for migration strategy recommendation."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class MigrationStrategy(str, Enum):
    """Recommended migration strategy."""

    AST_TRANSFORM = "ast_transform"
    CODING_AGENT = "coding_agent"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class MigrationAssessment:
    """Assessment of migration feasibility and recommended approach."""

    confidence: MigrationConfidence
    strategy: MigrationStrategy
    score: int  # 0-100
    reasons: tuple[str, ...]
    risk_factors: tuple[str, ...]

    @property
    def can_auto_migrate(self) -> bool:
        return self.confidence in {MigrationConfidence.HIGH, MigrationConfidence.MEDIUM}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "confidence": self.confidence.value,
            "strategy": self.strategy.value,
            "score": self.score,
            "reasons": list(self.reasons),
            "risk_factors": list(self.risk_factors),
            "can_auto_migrate": self.can_auto_migrate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MigrationAssessment":
        return cls(
            confidence=MigrationConfidence(data["confidence"]),
            strategy=MigrationStrategy(data["strategy"]),
            score=int(data["score"]),
            reasons=tuple(data.get("reasons", [])),
            risk_factors=tuple(data.get("risk_factors", [])),
        )


def assess_migration_confidence(
    usages: tuple[APIUsage, ...],
    impact: MigrationImpact,
    graph: "RepoImpactGraph | None" = None,
) -> MigrationAssessment:
    """
    Assess migration confidence and recommend strategy.

    High confidence: direct SDK usage, known symbol, simple change, tests exist
    Low confidence: wrapper functions, dynamic calls, no tests, unknown behavior
    """
    reasons: list[str] = []
    risk_factors: list[str] = []
    score = 50  # base score

    # Factor 1: Direct vs wrapper usage
    direct_usages = sum(
        1 for u in usages if u.call_type == "call" and not u.enclosing_scope.startswith("wrapper")
    )
    wrapper_usages = sum(
        1
        for u in usages
        if "wrapper" in u.enclosing_scope.lower() or "helper" in u.enclosing_scope.lower()
    )
    if wrapper_usages > 0:
        risk_factors.append(f"{wrapper_usages} usage(s) in wrapper/helper functions")
        score -= 15
    if direct_usages > 0:
        reasons.append(f"{direct_usages} direct SDK call(s) detected")
        score += 10

    # Factor 2: Test coverage
    if impact.impact_plan and impact.impact_plan.affected_code_has_tests:
        reasons.append("Affected code has test coverage")
        score += 20
    else:
        risk_factors.append("No test coverage for affected code")
        score -= 20

    # Factor 3: Number of affected files
    num_files = len(impact.affected_files)
    if num_files <= 3:
        reasons.append(f"Only {num_files} file(s) affected")
        score += 10
    elif num_files > 10:
        risk_factors.append(f"{num_files} files affected - large migration surface")
        score -= 15

    # Factor 4: Change complexity
    complex_changes = sum(
        1
        for m in impact.matched_changes
        if m.change.change_type in {ChangeType.SIGNATURE_CHANGE, ChangeType.BEHAVIOR_CHANGE}
    )
    if complex_changes > 0:
        risk_factors.append(f"{complex_changes} complex change(s) (signature/behavior)")
        score -= 15
    else:
        reasons.append("Only simple changes (removal/rename/deprecation)")
        score += 5

    # Factor 5: Dynamic/indirect calls (heuristic)
    dynamic_indicators = sum(
        1 for u in usages if "getattr" in u.code_snippet or ".__getattr__" in u.code_snippet
    )
    if dynamic_indicators > 0:
        risk_factors.append("Possible dynamic call patterns detected")
        score -= 10

    # Factor 6: Blast radius
    if impact.blast_radius.score <= 20:
        reasons.append(f"Low blast radius ({impact.blast_radius.score}/100)")
        score += 10
    elif impact.blast_radius.score > 50:
        risk_factors.append(f"High blast radius ({impact.blast_radius.score}/100)")
        score -= 10

    score = max(0, min(100, score))

    if score >= 70:
        confidence = MigrationConfidence.HIGH
        strategy = MigrationStrategy.AST_TRANSFORM
    elif score >= 40:
        confidence = MigrationConfidence.MEDIUM
        strategy = MigrationStrategy.CODING_AGENT
    else:
        confidence = MigrationConfidence.LOW
        strategy = MigrationStrategy.MANUAL

    return MigrationAssessment(
        confidence=confidence,
        strategy=strategy,
        score=score,
        reasons=tuple(reasons),
        risk_factors=tuple(risk_factors),
    )


# =============================================================================
# Migration Planning Models
# =============================================================================


class MigrationStatus(str, Enum):
    """Status of a migration execution."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class VerificationLevel(str, Enum):
    """Verification level achieved."""

    V0 = "v0"  # Patch generated
    V1 = "v1"  # Syntax/type/build passes
    V2 = "v2"  # Affected tests pass
    V3 = "v3"  # Full repo tests pass
    V4 = "v4"  # API contract/mock tests pass
    V5 = "v5"  # User-defined integration verification passes


@dataclass(frozen=True, slots=True)
class MigrationStep:
    """A single step in a migration plan."""

    step_id: str
    description: str
    transform_id: str | None = None
    filepath: str = ""
    target_symbol: str = ""
    status: MigrationStatus = MigrationStatus.PLANNED

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "transform_id": self.transform_id,
            "filepath": self.filepath,
            "target_symbol": self.target_symbol,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """Complete migration plan for a single API change."""

    provider: str
    change_id: str
    manifest: "APIChangeManifest"  # Forward reference
    affected_usages: tuple[APIUsage, ...]
    affected_files: tuple[str, ...]
    assessment: MigrationAssessment
    steps: tuple[MigrationStep, ...]
    verification_level: VerificationLevel = VerificationLevel.V0
    status: MigrationStatus = MigrationStatus.PLANNED
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "change_id": self.change_id,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "affected_usages": [u.to_dict() for u in self.affected_usages],
            "affected_files": list(self.affected_files),
            "assessment": self.assessment.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "verification_level": self.verification_level.value,
            "status": self.status.value,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Result of executing a migration plan."""

    plan: MigrationPlan
    migration_status: MigrationStatus
    verification_level: VerificationLevel
    proof_verdict: str | None = None
    proof_digest: str | None = None
    capsule_id: str | None = None
    certificate: "MigrationCertificate | None" = None
    errors: tuple[str, ...] = ()
    run_id: str | None = None
    expected_files: tuple[str, ...] = ()
    actual_modified_files: tuple[str, ...] = ()
    unexpected_files: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "migration_status": self.migration_status.value,
            "verification_level": self.verification_level.value,
            "proof_verdict": self.proof_verdict,
            "proof_digest": self.proof_digest,
            "capsule_id": self.capsule_id,
            "certificate": self.certificate.to_dict() if self.certificate else None,
            "errors": list(self.errors),
            "run_id": self.run_id,
            "expected_files": list(self.expected_files),
            "actual_modified_files": list(self.actual_modified_files),
            "unexpected_files": list(self.unexpected_files),
        }


@dataclass(frozen=True, slots=True)
class MigrationCertificate:
    """Integrity-protected statement about one exact repository patch."""

    certificate_id: str
    provider: str
    change_id: str
    verification_level: VerificationLevel
    affected_files: tuple[str, ...]
    blast_radius_score: int
    proof_digest: str
    capsule_id: str
    migration_digest: str
    created_at: str
    verified: bool = False
    schema_version: int = 1
    final_verdict: str = "NOT_PROVEN"
    upstream_source: str = ""
    upstream_source_digest: str = ""
    repository_base_sha: str = ""
    repository_base_digest: str = ""
    sdk_package: str = ""
    sdk_version: str = ""
    affected_symbols: tuple[str, ...] = ()
    affected_usages: int = 0
    expected_files: tuple[str, ...] = ()
    actual_modified_files: tuple[str, ...] = ()
    unexpected_files: tuple[str, ...] = ()
    migration_generator: str = ""
    migration_strategy: str = ""
    policy_result: str = ""
    policy_digest: str = ""
    blast_radius_level: str = ""
    verification_requested: VerificationLevel = VerificationLevel.V0
    build_result: str = "NOT_RUN"
    type_check_result: str = "NOT_RUN"
    affected_test_result: str = "NOT_RUN"
    full_test_result: str = "NOT_RUN"
    integrity_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "certificate_id": self.certificate_id,
            "provider": self.provider,
            "change_id": self.change_id,
            "verification_level": self.verification_level.value,
            "affected_files": list(self.affected_files),
            "blast_radius_score": self.blast_radius_score,
            "proof_digest": self.proof_digest,
            "capsule_id": self.capsule_id,
            "migration_digest": self.migration_digest,
            "created_at": self.created_at,
            "verified": self.verified,
            "final_verdict": self.final_verdict,
            "upstream_source": self.upstream_source,
            "upstream_source_digest": self.upstream_source_digest,
            "repository_base_sha": self.repository_base_sha,
            "repository_base_digest": self.repository_base_digest,
            "sdk_package": self.sdk_package,
            "sdk_version": self.sdk_version,
            "affected_symbols": list(self.affected_symbols),
            "affected_usages": self.affected_usages,
            "expected_files": list(self.expected_files),
            "actual_modified_files": list(self.actual_modified_files),
            "unexpected_files": list(self.unexpected_files),
            "migration_generator": self.migration_generator,
            "migration_strategy": self.migration_strategy,
            "policy_result": self.policy_result,
            "policy_digest": self.policy_digest,
            "blast_radius_level": self.blast_radius_level,
            "verification_requested": self.verification_requested.value,
            "build_result": self.build_result,
            "type_check_result": self.type_check_result,
            "affected_test_result": self.affected_test_result,
            "full_test_result": self.full_test_result,
            "integrity_sha256": self.integrity_sha256,
        }

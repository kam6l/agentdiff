"""Generic immutable maintenance change specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from ._canonical import (
    canonical_sha256,
    clean_bool,
    clean_confidence,
    clean_identifier,
    clean_string_tuple,
    clean_text,
    clean_timestamp,
    reject_unknown,
    require_mapping,
)

if TYPE_CHECKING:
    from agentdiff.api.manifest import APIChangeManifest


class MaintenanceSeverity(str, Enum):
    """Provider-neutral maintenance severity."""

    INFO = "info"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class StrategyDisposition(str, Enum):
    """How a patch-generation strategy may be used."""

    REQUIRED = "required"
    PREFERRED = "preferred"
    FALLBACK = "fallback"
    ALLOWED = "allowed"
    DISABLED = "disabled"


class ProofRequirement(str, Enum):
    """Minimum requested proof strength for a change."""

    NONE = "none"
    BASIC = "basic"
    STRONG = "strong"
    CAUSAL = "causal"
    ADVERSARIAL = "adversarial"


@dataclass(frozen=True, slots=True)
class ChangeSource:
    """Where an upstream maintenance signal came from."""

    type: str
    provider: str = ""
    version: str = ""
    uri: str = ""
    retrieved_at: str = ""
    content_digest: str = ""
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", clean_identifier(self.type, field="source.type"))
        object.__setattr__(
            self,
            "provider",
            clean_text(self.provider, field="source.provider", max_length=128),
        )
        object.__setattr__(
            self,
            "version",
            clean_text(self.version, field="source.version", max_length=256),
        )
        object.__setattr__(self, "uri", clean_text(self.uri, field="source.uri"))
        object.__setattr__(
            self,
            "retrieved_at",
            clean_timestamp(self.retrieved_at, field="source.retrieved_at", required=False),
        )
        object.__setattr__(
            self,
            "content_digest",
            clean_text(self.content_digest, field="source.content_digest", max_length=256),
        )
        object.__setattr__(
            self,
            "provenance",
            clean_string_tuple(self.provenance, field="source.provenance"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "provider": self.provider,
            "version": self.version,
            "uri": self.uri,
            "retrieved_at": self.retrieved_at,
            "content_digest": self.content_digest,
            "provenance": list(self.provenance),
        }

    @classmethod
    def from_dict(cls, value: object) -> ChangeSource:
        data = require_mapping(value, field="source")
        reject_unknown(
            data,
            frozenset(
                {
                    "type",
                    "provider",
                    "version",
                    "uri",
                    "retrieved_at",
                    "content_digest",
                    "provenance",
                }
            ),
            field="source",
        )
        return cls(
            type=data.get("type", ""),
            provider=data.get("provider", ""),
            version=data.get("version", ""),
            uri=data.get("uri", ""),
            retrieved_at=data.get("retrieved_at", ""),
            content_digest=data.get("content_digest", ""),
            provenance=clean_string_tuple(data.get("provenance", []), field="source.provenance"),
        )


@dataclass(frozen=True, slots=True)
class ChangeTargets:
    """Provider-neutral selectors for affected software."""

    symbols: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()
    repositories: tuple[str, ...] = ()
    files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("symbols", "parameters", "models", "packages", "repositories", "files"):
            object.__setattr__(
                self,
                name,
                clean_string_tuple(getattr(self, name), field=f"targets.{name}"),
            )
        if not any(
            (
                self.symbols,
                self.parameters,
                self.models,
                self.packages,
                self.repositories,
                self.files,
            )
        ):
            raise ValueError("targets must contain at least one selector")

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "symbols": list(self.symbols),
            "parameters": list(self.parameters),
            "models": list(self.models),
            "packages": list(self.packages),
            "repositories": list(self.repositories),
            "files": list(self.files),
        }

    @classmethod
    def from_dict(cls, value: object) -> ChangeTargets:
        data = require_mapping(value, field="targets")
        allowed = frozenset(
            {"symbols", "parameters", "models", "packages", "repositories", "files"}
        )
        reject_unknown(data, allowed, field="targets")
        return cls(
            symbols=clean_string_tuple(data.get("symbols", []), field="targets.symbols"),
            parameters=clean_string_tuple(data.get("parameters", []), field="targets.parameters"),
            models=clean_string_tuple(data.get("models", []), field="targets.models"),
            packages=clean_string_tuple(data.get("packages", []), field="targets.packages"),
            repositories=clean_string_tuple(
                data.get("repositories", []), field="targets.repositories"
            ),
            files=clean_string_tuple(data.get("files", []), field="targets.files"),
        )


@dataclass(frozen=True, slots=True)
class ChangeStrategy:
    """Allowed deterministic, agent, and manual generation paths."""

    deterministic: StrategyDisposition = StrategyDisposition.PREFERRED
    agent: StrategyDisposition = StrategyDisposition.FALLBACK
    manual_review: bool = True
    transform_id: str = ""

    def __post_init__(self) -> None:
        try:
            deterministic = StrategyDisposition(self.deterministic)
            agent = StrategyDisposition(self.agent)
        except ValueError as error:
            raise ValueError("strategy disposition is invalid") from error
        object.__setattr__(self, "deterministic", deterministic)
        object.__setattr__(self, "agent", agent)
        object.__setattr__(
            self,
            "manual_review",
            clean_bool(self.manual_review, field="strategy.manual_review"),
        )
        object.__setattr__(
            self,
            "transform_id",
            clean_text(self.transform_id, field="strategy.transform_id", max_length=256),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "deterministic": self.deterministic.value,
            "agent": self.agent.value,
            "manual_review": self.manual_review,
            "transform_id": self.transform_id,
        }

    @classmethod
    def from_dict(cls, value: object) -> ChangeStrategy:
        data = require_mapping(value, field="strategy")
        reject_unknown(
            data,
            frozenset({"deterministic", "agent", "manual_review", "transform_id"}),
            field="strategy",
        )
        try:
            deterministic = StrategyDisposition(data.get("deterministic", "preferred"))
            agent = StrategyDisposition(data.get("agent", "fallback"))
        except ValueError as error:
            raise ValueError("strategy disposition is invalid") from error
        return cls(
            deterministic=deterministic,
            agent=agent,
            manual_review=clean_bool(
                data.get("manual_review", True), field="strategy.manual_review"
            ),
            transform_id=data.get("transform_id", ""),
        )


@dataclass(frozen=True, slots=True)
class ChangeProof:
    """Proof requested before delivery."""

    required: ProofRequirement = ProofRequirement.STRONG
    behavior_contracts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            required = ProofRequirement(self.required)
        except ValueError as error:
            raise ValueError("proof.required is invalid") from error
        object.__setattr__(self, "required", required)
        object.__setattr__(
            self,
            "behavior_contracts",
            clean_string_tuple(self.behavior_contracts, field="proof.behavior_contracts"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required.value,
            "behavior_contracts": list(self.behavior_contracts),
        }

    @classmethod
    def from_dict(cls, value: object) -> ChangeProof:
        data = require_mapping(value, field="proof")
        reject_unknown(
            data,
            frozenset({"required", "behavior_contracts"}),
            field="proof",
        )
        try:
            required = ProofRequirement(data.get("required", "strong"))
        except ValueError as error:
            raise ValueError("proof.required is invalid") from error
        return cls(
            required=required,
            behavior_contracts=clean_string_tuple(
                data.get("behavior_contracts", []), field="proof.behavior_contracts"
            ),
        )


@dataclass(frozen=True, slots=True)
class ChangeDelivery:
    """Authorized delivery behavior; automatic merge is off by default."""

    open_pr: bool = False
    auto_merge: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_pr", clean_bool(self.open_pr, field="delivery.open_pr"))
        object.__setattr__(
            self,
            "auto_merge",
            clean_bool(self.auto_merge, field="delivery.auto_merge"),
        )
        if self.auto_merge and not self.open_pr:
            raise ValueError("delivery.auto_merge requires delivery.open_pr")

    def to_dict(self) -> dict[str, bool]:
        return {"open_pr": self.open_pr, "auto_merge": self.auto_merge}

    @classmethod
    def from_dict(cls, value: object) -> ChangeDelivery:
        data = require_mapping(value, field="delivery")
        reject_unknown(data, frozenset({"open_pr", "auto_merge"}), field="delivery")
        return cls(
            open_pr=clean_bool(data.get("open_pr", False), field="delivery.open_pr"),
            auto_merge=clean_bool(data.get("auto_merge", False), field="delivery.auto_merge"),
        )


@dataclass(frozen=True, slots=True)
class ChangeSpec:
    """A deterministic, provider-neutral request for one maintenance change."""

    kind: str
    external_id: str
    title: str
    source: ChangeSource
    targets: ChangeTargets
    severity: MaintenanceSeverity
    strategy: ChangeStrategy = field(default_factory=ChangeStrategy)
    proof: ChangeProof = field(default_factory=ChangeProof)
    delivery: ChangeDelivery = field(default_factory=ChangeDelivery)
    description: str = ""
    deadline: str = ""
    confidence: float = 1.0
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ChangeSpec schema version")
        object.__setattr__(self, "kind", clean_identifier(self.kind, field="kind"))
        object.__setattr__(
            self,
            "external_id",
            clean_text(self.external_id, field="external_id", required=True, max_length=256),
        )
        object.__setattr__(
            self,
            "title",
            clean_text(self.title, field="title", required=True, max_length=512),
        )
        if not isinstance(self.source, ChangeSource):
            raise ValueError("source must be a ChangeSource")
        if not isinstance(self.targets, ChangeTargets):
            raise ValueError("targets must be ChangeTargets")
        try:
            severity = MaintenanceSeverity(self.severity)
        except ValueError as error:
            raise ValueError("severity is invalid") from error
        object.__setattr__(self, "severity", severity)
        if not isinstance(self.strategy, ChangeStrategy):
            raise ValueError("strategy must be a ChangeStrategy")
        if not isinstance(self.proof, ChangeProof):
            raise ValueError("proof must be a ChangeProof")
        if not isinstance(self.delivery, ChangeDelivery):
            raise ValueError("delivery must be a ChangeDelivery")
        object.__setattr__(
            self,
            "description",
            clean_text(self.description, field="description", max_length=16_384),
        )
        object.__setattr__(
            self,
            "deadline",
            clean_text(self.deadline, field="deadline", max_length=64),
        )
        object.__setattr__(self, "confidence", clean_confidence(self.confidence))

    @property
    def id(self) -> str:
        identity = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "external_id": self.external_id,
            "source": {
                "type": self.source.type,
                "provider": self.source.provider,
                "version": self.source.version,
                "uri": self.source.uri,
            },
            "targets": self.targets.to_dict(),
        }
        return f"change-spec-{canonical_sha256(identity)[:24]}"

    @property
    def digest(self) -> str:
        return canonical_sha256(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "external_id": self.external_id,
            "title": self.title,
            "description": self.description,
            "source": self.source.to_dict(),
            "targets": self.targets.to_dict(),
            "severity": self.severity.value,
            "strategy": self.strategy.to_dict(),
            "proof": self.proof.to_dict(),
            "delivery": self.delivery.to_dict(),
            "deadline": self.deadline,
            "confidence": self.confidence,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "id": self.id, "digest": self.digest}

    @classmethod
    def from_dict(cls, value: object) -> ChangeSpec:
        data = require_mapping(value, field="ChangeSpec")
        reject_unknown(
            data,
            frozenset(
                {
                    "schema_version",
                    "id",
                    "digest",
                    "kind",
                    "external_id",
                    "title",
                    "description",
                    "source",
                    "targets",
                    "severity",
                    "strategy",
                    "proof",
                    "delivery",
                    "deadline",
                    "confidence",
                }
            ),
            field="ChangeSpec",
        )
        version = data.get("schema_version", 0)
        if isinstance(version, bool) or version != 1:
            raise ValueError("unsupported ChangeSpec schema version")
        try:
            severity = MaintenanceSeverity(data.get("severity", ""))
        except ValueError as error:
            raise ValueError("severity is invalid") from error
        spec = cls(
            kind=data.get("kind", ""),
            external_id=data.get("external_id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            source=ChangeSource.from_dict(data.get("source")),
            targets=ChangeTargets.from_dict(data.get("targets")),
            severity=severity,
            strategy=ChangeStrategy.from_dict(data.get("strategy", {})),
            proof=ChangeProof.from_dict(data.get("proof", {})),
            delivery=ChangeDelivery.from_dict(data.get("delivery", {})),
            deadline=data.get("deadline", ""),
            confidence=clean_confidence(data.get("confidence", 1.0)),
            schema_version=1,
        )
        recorded_id = data.get("id")
        if recorded_id is not None and recorded_id != spec.id:
            raise ValueError("ChangeSpec id does not match its canonical identity")
        recorded_digest = data.get("digest")
        if recorded_digest is not None and recorded_digest != spec.digest:
            raise ValueError("ChangeSpec digest does not match its canonical payload")
        return spec

    @classmethod
    def from_api_manifest(
        cls,
        manifest: APIChangeManifest,
        *,
        proof: ChangeProof | None = None,
        delivery: ChangeDelivery | None = None,
    ) -> ChangeSpec:
        """Adapt the existing API manifest without changing its public schema."""

        primary = manifest.strategy.primary.value
        fallback = manifest.strategy.fallback.value if manifest.strategy.fallback else ""
        deterministic = _strategy_disposition(primary, fallback, "ast_transform")
        agent = _strategy_disposition(primary, fallback, "coding_agent")
        provenance = tuple(
            value for value in (manifest.source.url, manifest.migration_guide_url) if value
        )
        source_version = (
            manifest.source.version or manifest.breaking_version or manifest.minimum_sdk_version
        )
        return cls(
            kind="upstream_change",
            external_id=manifest.change_id,
            title=manifest.title,
            description=manifest.description,
            source=ChangeSource(
                type=manifest.source.type.value,
                provider=manifest.provider,
                version=source_version,
                uri=manifest.source.url,
                retrieved_at=manifest.source.retrieved_at,
                provenance=provenance,
            ),
            targets=ChangeTargets(
                symbols=manifest.affected.symbols,
                parameters=manifest.affected.parameters,
                models=manifest.affected.models,
            ),
            severity=MaintenanceSeverity(manifest.severity.value),
            strategy=ChangeStrategy(
                deterministic=deterministic,
                agent=agent,
                manual_review=primary == "manual" or fallback == "manual",
                transform_id=manifest.strategy.transform_id,
            ),
            proof=proof or ChangeProof(),
            delivery=delivery or ChangeDelivery(),
            deadline=manifest.deadline,
            confidence=manifest.confidence,
        )


def _strategy_disposition(
    primary: str,
    fallback: str,
    selected: str,
) -> StrategyDisposition:
    if primary == selected:
        return StrategyDisposition.PREFERRED
    if fallback == selected:
        return StrategyDisposition.FALLBACK
    return StrategyDisposition.DISABLED

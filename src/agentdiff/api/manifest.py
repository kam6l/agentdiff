"""API Change Manifest: machine-readable upstream change definition."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from agentdiff.api.models import ChangeSeverity, ChangeType


class MigrationStrategyType(str, Enum):
    """How the migration should be performed."""

    AST_TRANSFORM = "ast_transform"
    CODING_AGENT = "coding_agent"
    MANUAL = "manual"


class SourceType(str, Enum):
    """Source of the change definition."""

    OFFICIAL_DOCS = "official_docs"
    CHANGELOG = "changelog"
    SDK_RELEASE = "sdk_release"
    GITHUB_RELEASE = "github_release"
    DEPRECATION_ANNOUNCEMENT = "deprecation_announcement"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ManifestSource:
    """Upstream source metadata."""

    type: SourceType
    url: str
    retrieved_at: str = ""
    version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManifestSource":
        return cls(
            type=SourceType(data["type"]),
            url=data["url"],
            retrieved_at=data.get("retrieved_at", ""),
            version=data.get("version", ""),
        )


@dataclass(frozen=True, slots=True)
class AffectedSymbols:
    """Symbols affected by this change."""

    symbols: tuple[str, ...]
    parameters: tuple[str, ...] = ()
    models: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbols": list(self.symbols),
            "parameters": list(self.parameters),
            "models": list(self.models),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AffectedSymbols":
        return cls(
            symbols=tuple(data.get("symbols", [])),
            parameters=tuple(data.get("parameters", [])),
            models=tuple(data.get("models", [])),
        )


@dataclass(frozen=True, slots=True)
class ReplacementSymbols:
    """Replacement symbols for the migration."""

    symbols: tuple[str, ...]
    parameter_mapping: dict[str, str] = field(default_factory=dict)
    code_template: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbols": list(self.symbols),
            "parameter_mapping": dict(self.parameter_mapping),
            "code_template": self.code_template,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReplacementSymbols":
        return cls(
            symbols=tuple(data.get("symbols", [])),
            parameter_mapping=dict(data.get("parameter_mapping", {})),
            code_template=data.get("code_template", ""),
        )


@dataclass(frozen=True, slots=True)
class MigrationStrategyConfig:
    """Migration strategy configuration."""

    primary: MigrationStrategyType
    fallback: MigrationStrategyType | None = None
    transform_id: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary.value,
            "fallback": self.fallback.value if self.fallback else None,
            "transform_id": self.transform_id,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MigrationStrategyConfig":
        return cls(
            primary=MigrationStrategyType(data["primary"]),
            fallback=MigrationStrategyType(data["fallback"]) if data.get("fallback") else None,
            transform_id=data.get("transform_id", ""),
            parameters=dict(data.get("parameters", {})),
        )


@dataclass(frozen=True, slots=True)
class APIChangeManifest:
    """Machine-readable API change definition for migration."""

    provider: str
    change_id: str
    title: str
    change_type: ChangeType
    severity: ChangeSeverity
    description: str
    source: ManifestSource
    affected: AffectedSymbols
    replacement: ReplacementSymbols
    strategy: MigrationStrategyConfig
    confidence: float = 0.8
    deadline: str = ""
    migration_guide_url: str = ""
    breaking_version: str = ""
    minimum_sdk_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "change_id": self.change_id,
            "title": self.title,
            "change_type": self.change_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "source": self.source.to_dict(),
            "affected": self.affected.to_dict(),
            "replacement": self.replacement.to_dict(),
            "strategy": self.strategy.to_dict(),
            "confidence": self.confidence,
            "deadline": self.deadline,
            "migration_guide_url": self.migration_guide_url,
            "breaking_version": self.breaking_version,
            "minimum_sdk_version": self.minimum_sdk_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "APIChangeManifest":
        return cls(
            provider=data["provider"],
            change_id=data["change_id"],
            title=data["title"],
            change_type=ChangeType(data["change_type"]),
            severity=ChangeSeverity(data["severity"]),
            description=data.get("description", ""),
            source=ManifestSource.from_dict(data["source"]),
            affected=AffectedSymbols.from_dict(data["affected"]),
            replacement=ReplacementSymbols.from_dict(data["replacement"]),
            strategy=MigrationStrategyConfig.from_dict(data["strategy"]),
            confidence=float(data.get("confidence", 0.8)),
            deadline=data.get("deadline", ""),
            migration_guide_url=data.get("migration_guide_url", ""),
            breaking_version=data.get("breaking_version", ""),
            minimum_sdk_version=data.get("minimum_sdk_version", ""),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "APIChangeManifest":
        """Load manifest from YAML file."""
        content = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        return cls.from_dict(data)

    @classmethod
    def from_json(cls, path: str | Path) -> "APIChangeManifest":
        """Load manifest from JSON file."""
        content = Path(path).read_text(encoding="utf-8")
        data = json.loads(content)
        return cls.from_dict(data)

    def to_yaml(self, path: str | Path) -> None:
        """Write manifest to YAML file."""

        def _convert_enums(obj: Any) -> Any:
            """Recursively convert Enum values to strings."""
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, dict):
                return {k: _convert_enums(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_convert_enums(v) for v in obj]
            return obj

        data = _convert_enums(self.to_dict())
        Path(path).write_text(
            yaml.dump(data, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )

    def to_json(self, path: str | Path) -> None:
        """Write manifest to JSON file."""
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def validate(self) -> tuple[bool, list[str]]:
        """Validate manifest completeness."""
        errors: list[str] = []

        if not self.provider:
            errors.append("provider is required")
        if not self.change_id:
            errors.append("change_id is required")
        if not self.affected.symbols:
            errors.append("at least one affected symbol is required")
        if not self.replacement.symbols:
            errors.append("at least one replacement symbol is required")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append("confidence must be between 0.0 and 1.0")

        return len(errors) == 0, errors


# Built-in manifest registry
_BUILTIN_MANIFESTS: dict[str, APIChangeManifest] = {}


def register_builtin_manifest(manifest: APIChangeManifest) -> None:
    """Register a built-in manifest."""
    key = f"{manifest.provider}:{manifest.change_id}"
    _BUILTIN_MANIFESTS[key] = manifest


def get_builtin_manifest(provider: str, change_id: str) -> APIChangeManifest | None:
    """Get a built-in manifest by provider and change_id."""
    return _BUILTIN_MANIFESTS.get(f"{provider}:{change_id}")


def list_builtin_manifests() -> list[APIChangeManifest]:
    """List all built-in manifests."""
    return list(_BUILTIN_MANIFESTS.values())


def _register_builtin_manifests() -> None:
    """Register all built-in manifests."""
    # OpenAI: Chat Completions -> Responses API
    register_builtin_manifest(
        APIChangeManifest(
            provider="openai",
            change_id="chat_to_responses",
            title="Migrate from Chat Completions to Responses API",
            change_type=ChangeType.BEHAVIOR_CHANGE,
            severity=ChangeSeverity.MODERATE,
            description=(
                "Chat Completions remains supported. OpenAI recommends Responses for new "
                "projects; this optional migration changes endpoint, response objects, "
                "state, structured output, function calling, and streaming semantics."
            ),
            source=ManifestSource(
                type=SourceType.OFFICIAL_DOCS,
                url="https://developers.openai.com/api/docs/guides/migrate-to-responses",
                version="2026-08-21",
            ),
            affected=AffectedSymbols(
                symbols=("client.chat.completions.create",),
                parameters=(
                    "model",
                    "messages",
                    "temperature",
                    "max_tokens",
                    "max_completion_tokens",
                    "store",
                    "top_p",
                ),
            ),
            replacement=ReplacementSymbols(
                symbols=("client.responses.create",),
                parameter_mapping={
                    "messages": "input",
                    "max_tokens": "max_output_tokens",
                    "max_completion_tokens": "max_output_tokens",
                },
                code_template=(
                    "response = client.responses.create(\n    model={model},\n    input={input},\n)"
                ),
            ),
            strategy=MigrationStrategyConfig(
                primary=MigrationStrategyType.AST_TRANSFORM,
                fallback=MigrationStrategyType.CODING_AGENT,
                transform_id="openai-chat-to-responses",
            ),
            confidence=0.85,
            migration_guide_url=(
                "https://developers.openai.com/api/docs/guides/migrate-to-responses"
            ),
            breaking_version="",
            minimum_sdk_version="1.66.0",
        )
    )

    # OpenAI: Legacy ChatCompletion.create -> Chat Completions
    register_builtin_manifest(
        APIChangeManifest(
            provider="openai",
            change_id="legacy_chat_completion_to_chat_completions",
            title="Migrate from legacy ChatCompletion.create to client.chat.completions.create",
            change_type=ChangeType.REMOVAL,
            severity=ChangeSeverity.CRITICAL,
            description=(
                "The global openai.ChatCompletion.create() was removed in OpenAI v1.0.0+. "
                "Use client.chat.completions.create() instead."
            ),
            source=ManifestSource(
                type=SourceType.SDK_RELEASE,
                url="https://github.com/openai/openai-python/discussions/742",
                version="1.0.0",
            ),
            affected=AffectedSymbols(
                symbols=("openai.ChatCompletion.create",),
                parameters=("model", "messages", "functions", "temperature", "max_tokens"),
            ),
            replacement=ReplacementSymbols(
                symbols=("client.chat.completions.create",),
                parameter_mapping={
                    "functions": "tools",
                },
                code_template=(
                    "client = OpenAI()\n"
                    "response = client.chat.completions.create(\n"
                    "    model={model},\n"
                    "    messages={messages},\n"
                    "    tools={tools},\n"
                    ")"
                ),
            ),
            strategy=MigrationStrategyConfig(
                primary=MigrationStrategyType.AST_TRANSFORM,
                fallback=MigrationStrategyType.CODING_AGENT,
                transform_id="openai-legacy-chat-completion",
            ),
            confidence=0.95,
            migration_guide_url="https://github.com/openai/openai-python/discussions/742",
            breaking_version=">=1.0.0",
            minimum_sdk_version="1.0.0",
        )
    )

    # Stripe: Charges -> PaymentIntents
    register_builtin_manifest(
        APIChangeManifest(
            provider="stripe",
            change_id="charges_to_payment_intents",
            title="Migrate from stripe.Charge.create to stripe.PaymentIntent.create",
            change_type=ChangeType.DEPRECATION,
            severity=ChangeSeverity.HIGH,
            description=(
                "Direct stripe.Charge.create() calls do not support Strong Customer "
                "Authentication (SCA) or 3D Secure 2. "
                "Migrate to stripe.PaymentIntent.create() for SCA compliance."
            ),
            source=ManifestSource(
                type=SourceType.OFFICIAL_DOCS,
                url="https://stripe.com/docs/payments/payment-intents/migration",
                version="2024-01",
            ),
            affected=AffectedSymbols(
                symbols=("stripe.Charge.create", "client.charges.create"),
                parameters=("amount", "currency", "source", "customer", "description"),
            ),
            replacement=ReplacementSymbols(
                symbols=("stripe.PaymentIntent.create",),
                parameter_mapping={
                    "source": "payment_method",
                },
                code_template=(
                    "intent = stripe.PaymentIntent.create(\n"
                    "    amount={amount},\n"
                    "    currency={currency},\n"
                    "    payment_method={payment_method},\n"
                    "    automatic_payment_methods={{'enabled': True}},\n"
                    ")"
                ),
            ),
            strategy=MigrationStrategyConfig(
                primary=MigrationStrategyType.AST_TRANSFORM,
                fallback=MigrationStrategyType.CODING_AGENT,
                transform_id="stripe-charges-to-payment-intents",
            ),
            confidence=0.85,
            migration_guide_url="https://stripe.com/docs/payments/payment-intents/migration",
            breaking_version="",
            minimum_sdk_version="7.0.0",
        )
    )


# Register built-in manifests
_register_builtin_manifests()

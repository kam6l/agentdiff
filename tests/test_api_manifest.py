from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff.api.manifest import (
    AffectedSymbols,
    APIChangeManifest,
    ManifestSource,
    MigrationStrategyConfig,
    MigrationStrategyType,
    ReplacementSymbols,
    SourceType,
    get_builtin_manifest,
    list_builtin_manifests,
)
from agentdiff.api.models import ChangeSeverity, ChangeType


class TestManifestModels:
    """Test manifest data models."""

    def test_manifest_source_serialization(self) -> None:
        source = ManifestSource(
            type=SourceType.OFFICIAL_DOCS,
            url="https://example.com/docs",
            retrieved_at="2025-01-01T00:00:00Z",
            version="1.0",
        )
        data = source.to_dict()
        assert data["type"] == "official_docs"
        assert data["url"] == "https://example.com/docs"
        restored = ManifestSource.from_dict(data)
        assert restored == source

    def test_affected_symbols_serialization(self) -> None:
        affected = AffectedSymbols(
            symbols=("client.chat.completions.create",),
            parameters=("model", "messages"),
            models=("gpt-4o",),
        )
        data = affected.to_dict()
        assert "client.chat.completions.create" in data["symbols"]
        restored = AffectedSymbols.from_dict(data)
        assert restored == affected

    def test_replacement_symbols_serialization(self) -> None:
        replacement = ReplacementSymbols(
            symbols=("client.responses.create",),
            parameter_mapping={"messages": "input"},
            code_template="response = client.responses.create(input={input})",
        )
        data = replacement.to_dict()
        assert data["parameter_mapping"]["messages"] == "input"
        restored = ReplacementSymbols.from_dict(data)
        assert restored == replacement

    def test_migration_strategy_config_serialization(self) -> None:
        strategy = MigrationStrategyConfig(
            primary=MigrationStrategyType.AST_TRANSFORM,
            fallback=MigrationStrategyType.CODING_AGENT,
            transform_id="openai-chat-to-responses",
            parameters={"param1": "value1"},
        )
        data = strategy.to_dict()
        assert data["primary"] == "ast_transform"
        assert data["fallback"] == "coding_agent"
        restored = MigrationStrategyConfig.from_dict(data)
        assert restored == strategy


class TestAPIChangeManifest:
    """Test APIChangeManifest model."""

    def test_minimal_manifest(self) -> None:
        manifest = APIChangeManifest(
            provider="openai",
            change_id="test_change",
            title="Test Change",
            change_type=ChangeType.DEPRECATION,
            severity=ChangeSeverity.HIGH,
            description="Test description",
            source=ManifestSource(type=SourceType.OFFICIAL_DOCS, url="https://example.com"),
            affected=AffectedSymbols(symbols=("old.symbol",)),
            replacement=ReplacementSymbols(symbols=("new.symbol",)),
            strategy=MigrationStrategyConfig(primary=MigrationStrategyType.AST_TRANSFORM),
        )
        assert manifest.provider == "openai"
        assert manifest.change_id == "test_change"
        assert manifest.confidence == 0.8  # default

    def test_manifest_validation_success(self) -> None:
        manifest = APIChangeManifest(
            provider="openai",
            change_id="valid",
            title="Valid",
            change_type=ChangeType.DEPRECATION,
            severity=ChangeSeverity.HIGH,
            description="Test",
            source=ManifestSource(type=SourceType.OFFICIAL_DOCS, url="https://example.com"),
            affected=AffectedSymbols(symbols=("old",)),
            replacement=ReplacementSymbols(symbols=("new",)),
            strategy=MigrationStrategyConfig(primary=MigrationStrategyType.AST_TRANSFORM),
        )
        valid, errors = manifest.validate()
        assert valid
        assert errors == []

    def test_manifest_validation_missing_provider(self) -> None:
        manifest = APIChangeManifest(
            provider="",
            change_id="test",
            title="Test",
            change_type=ChangeType.DEPRECATION,
            severity=ChangeSeverity.HIGH,
            description="Test",
            source=ManifestSource(type=SourceType.OFFICIAL_DOCS, url="https://example.com"),
            affected=AffectedSymbols(symbols=("old",)),
            replacement=ReplacementSymbols(symbols=("new",)),
            strategy=MigrationStrategyConfig(primary=MigrationStrategyType.AST_TRANSFORM),
        )
        valid, errors = manifest.validate()
        assert not valid
        assert any("provider" in e for e in errors)

    def test_manifest_validation_missing_affected(self) -> None:
        manifest = APIChangeManifest(
            provider="openai",
            change_id="test",
            title="Test",
            change_type=ChangeType.DEPRECATION,
            severity=ChangeSeverity.HIGH,
            description="Test",
            source=ManifestSource(type=SourceType.OFFICIAL_DOCS, url="https://example.com"),
            affected=AffectedSymbols(symbols=()),
            replacement=ReplacementSymbols(symbols=("new",)),
            strategy=MigrationStrategyConfig(primary=MigrationStrategyType.AST_TRANSFORM),
        )
        valid, errors = manifest.validate()
        assert not valid
        assert any("affected symbol" in e for e in errors)

    def test_manifest_validation_invalid_confidence(self) -> None:
        manifest = APIChangeManifest(
            provider="openai",
            change_id="test",
            title="Test",
            change_type=ChangeType.DEPRECATION,
            severity=ChangeSeverity.HIGH,
            description="Test",
            source=ManifestSource(type=SourceType.OFFICIAL_DOCS, url="https://example.com"),
            affected=AffectedSymbols(symbols=("old",)),
            replacement=ReplacementSymbols(symbols=("new",)),
            strategy=MigrationStrategyConfig(primary=MigrationStrategyType.AST_TRANSFORM),
            confidence=1.5,
        )
        valid, errors = manifest.validate()
        assert not valid
        assert any("confidence" in e for e in errors)

    def test_manifest_yaml_roundtrip(self, tmp_path: Path) -> None:
        manifest = APIChangeManifest(
            provider="openai",
            change_id="yaml_test",
            title="YAML Test",
            change_type=ChangeType.DEPRECATION,
            severity=ChangeSeverity.HIGH,
            description="Test",
            source=ManifestSource(type=SourceType.OFFICIAL_DOCS, url="https://example.com"),
            affected=AffectedSymbols(symbols=("old.symbol",)),
            replacement=ReplacementSymbols(symbols=("new.symbol",)),
            strategy=MigrationStrategyConfig(primary=MigrationStrategyType.AST_TRANSFORM),
        )
        path = tmp_path / "manifest.yaml"
        manifest.to_yaml(path)
        restored = APIChangeManifest.from_yaml(path)
        assert restored == manifest

    def test_manifest_json_roundtrip(self, tmp_path: Path) -> None:
        manifest = APIChangeManifest(
            provider="stripe",
            change_id="json_test",
            title="JSON Test",
            change_type=ChangeType.REMOVAL,
            severity=ChangeSeverity.CRITICAL,
            description="Test",
            source=ManifestSource(type=SourceType.SDK_RELEASE, url="https://example.com"),
            affected=AffectedSymbols(symbols=("stripe.Charge.create",)),
            replacement=ReplacementSymbols(symbols=("stripe.PaymentIntent.create",)),
            strategy=MigrationStrategyConfig(primary=MigrationStrategyType.AST_TRANSFORM),
        )
        path = tmp_path / "manifest.json"
        manifest.to_json(path)
        restored = APIChangeManifest.from_json(path)
        assert restored == manifest


class TestBuiltinManifests:
    """Test built-in manifest registry."""

    def test_openai_chat_to_responses_exists(self) -> None:
        manifest = get_builtin_manifest("openai", "chat_to_responses")
        assert manifest is not None
        assert manifest.provider == "openai"
        assert manifest.change_id == "chat_to_responses"
        assert manifest.severity == ChangeSeverity.MODERATE
        assert "client.chat.completions.create" in manifest.affected.symbols
        assert "client.responses.create" in manifest.replacement.symbols
        assert manifest.strategy.primary == MigrationStrategyType.AST_TRANSFORM
        assert manifest.confidence == 0.85

    def test_openai_legacy_chat_completion_exists(self) -> None:
        manifest = get_builtin_manifest("openai", "legacy_chat_completion_to_chat_completions")
        assert manifest is not None
        assert manifest.severity == ChangeSeverity.CRITICAL
        assert "openai.ChatCompletion.create" in manifest.affected.symbols
        assert "client.chat.completions.create" in manifest.replacement.symbols
        assert manifest.confidence == 0.95

    def test_stripe_charges_to_payment_intents_exists(self) -> None:
        manifest = get_builtin_manifest("stripe", "charges_to_payment_intents")
        assert manifest is not None
        assert manifest.provider == "stripe"
        assert "stripe.Charge.create" in manifest.affected.symbols
        assert "stripe.PaymentIntent.create" in manifest.replacement.symbols
        assert manifest.confidence == 0.85

    def test_unknown_manifest_returns_none(self) -> None:
        manifest = get_builtin_manifest("unknown", "nonexistent")
        assert manifest is None

    def test_list_builtin_manifests(self) -> None:
        manifests = list_builtin_manifests()
        assert len(manifests) >= 3
        providers = {m.provider for m in manifests}
        assert "openai" in providers
        assert "stripe" in providers

    def test_builtin_manifests_are_valid(self) -> None:
        for manifest in list_builtin_manifests():
            valid, errors = manifest.validate()
            assert valid, (
                f"Built-in manifest {manifest.provider}:{manifest.change_id} invalid: {errors}"
            )


class TestManifestLoading:
    """Test loading manifests from files."""

    def test_load_from_yaml_file(self, tmp_path: Path) -> None:
        yaml_content = """
provider: openai
change_id: custom_change
title: Custom Change
change_type: deprecation
severity: high
description: Custom test change
source:
  type: official_docs
  url: https://example.com
affected:
  symbols:
    - custom.old
replacement:
  symbols:
    - custom.new
strategy:
  primary: ast_transform
"""
        path = tmp_path / "custom.yaml"
        path.write_text(yaml_content.strip(), encoding="utf-8")
        manifest = APIChangeManifest.from_yaml(path)
        assert manifest.provider == "openai"
        assert manifest.change_id == "custom_change"
        assert manifest.affected.symbols == ("custom.old",)

    def test_load_from_json_file(self, tmp_path: Path) -> None:
        json_data = {
            "provider": "stripe",
            "change_id": "custom_stripe",
            "title": "Custom Stripe",
            "change_type": "removal",
            "severity": "critical",
            "description": "Test",
            "source": {"type": "official_docs", "url": "https://example.com"},
            "affected": {"symbols": ["stripe.Old"]},
            "replacement": {"symbols": ["stripe.New"]},
            "strategy": {"primary": "ast_transform"},
        }
        path = tmp_path / "custom.json"
        path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
        manifest = APIChangeManifest.from_json(path)
        assert manifest.provider == "stripe"
        assert manifest.change_id == "custom_stripe"

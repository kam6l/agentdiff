"""Tests for the Provider Plugin System."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff.api.manifest import get_builtin_manifest
from agentdiff.api.plugins import (
    PluginTrust,
    discover_plugins,
    install_plugin,
    list_plugins,
    load_plugin,
)


def _make_plugin(root: Path, name: str = "stripe", *, trust: str = "DATA_ONLY") -> Path:
    plugin_dir = root / name
    manifests = plugin_dir / "manifests"
    transforms = plugin_dir / "transforms"
    tests = plugin_dir / "tests"
    manifests.mkdir(parents=True)
    transforms.mkdir()
    tests.mkdir()

    (plugin_dir / "metadata.yaml").write_text(
        f"name: {name}\nlibrary: {name}\nversion: '1.0.0'\ntrust: {trust}\n",
        encoding="utf-8",
    )

    (manifests / "charges.yaml").write_text(
        """
provider: stripe
change_id: charges_to_payment_methods
title: Migrate charges to payment methods
change_type: deprecation
severity: high
description: Test plugin manifest
source:
  type: official_docs
  url: https://example.com
affected:
  symbols:
    - stripe.Charge.create
replacement:
  symbols:
    - stripe.PaymentMethod.create
strategy:
  primary: ast_transform
""".strip(),
        encoding="utf-8",
    )

    (transforms / "test_transform.py").write_text(
        """
from agentdiff.api.transforms.base import ASTMigrationTransform, register_transform

class TestPluginTransform(ASTMigrationTransform):
    transform_id = "test-plugin-transform"
    provider = "stripe"
    affected_symbols = ("stripe.Charge.create",)

    def can_transform(self, context):
        return context.usage.symbol in self.affected_symbols

    def _create_transformer(self, context):
        import ast
        return ast.NodeTransformer()

register_transform(TestPluginTransform())
""".strip(),
        encoding="utf-8",
    )

    return plugin_dir


class TestPluginDiscovery:
    def test_discover_plugins(self, tmp_path: Path) -> None:
        _make_plugin(tmp_path)
        discovered = discover_plugins(tmp_path)
        assert len(discovered) == 1
        assert discovered[0].name == "stripe"

    def test_discover_empty_when_no_plugins(self, tmp_path: Path) -> None:
        assert discover_plugins(tmp_path / "nonexistent") == []


class TestPluginLoading:
    def test_load_plugin_registers_manifest(self, tmp_path: Path) -> None:
        plugin_dir = _make_plugin(tmp_path)
        plugin = load_plugin(plugin_dir)
        assert plugin.name == "stripe"
        assert plugin.library == "stripe"
        assert len(plugin.manifests) == 1
        assert plugin.manifests[0].change_id == "charges_to_payment_methods"

        # Manifest is registered globally, addressable by provider + change_id.
        registered = get_builtin_manifest("stripe", "charges_to_payment_methods")
        assert registered is not None
        assert registered.provider == "stripe"

    def test_load_plugin_registers_transforms(self, tmp_path: Path) -> None:
        plugin_dir = _make_plugin(tmp_path, trust="TRUSTED_CODE")
        plugin = load_plugin(plugin_dir, allow_code=True)
        assert len(plugin.transforms) == 1
        assert plugin.transforms[0].transform_id == "test-plugin-transform"
        assert plugin.code_loaded is True

    def test_plugin_code_is_not_executed_by_default(self, tmp_path: Path) -> None:
        plugin_dir = _make_plugin(tmp_path, trust="TRUSTED_CODE")

        plugin = load_plugin(plugin_dir)

        assert plugin.trust is PluginTrust.TRUSTED_CODE
        assert plugin.executable_code_present is True
        assert plugin.code_loaded is False
        assert plugin.transforms == ()
        assert plugin.source_digest.startswith("sha256:")

    def test_missing_metadata_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad"
        bad.mkdir()
        with pytest.raises(ValueError):
            load_plugin(bad)


class TestPluginInstall:
    def test_install_and_list(self, tmp_path: Path) -> None:
        source = _make_plugin(tmp_path / "src", name="custom_provider")
        plugins_root = tmp_path / "providers"
        dest = install_plugin("custom_provider", source, plugins_root)
        assert dest.is_dir()
        assert (dest / "metadata.yaml").is_file()

        plugins = list_plugins(plugins_root)
        assert len(plugins) == 1
        assert plugins[0].name == "custom_provider"

    def test_install_conflict(self, tmp_path: Path) -> None:
        source = _make_plugin(tmp_path / "src")
        plugins_root = tmp_path / "providers"
        install_plugin("stripe", source, plugins_root)
        with pytest.raises(FileExistsError):
            install_plugin("stripe", source, plugins_root)

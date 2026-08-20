"""Base class for third-party API provider plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from agentdiff.api.version_detector import SDKVersionInfo, is_version_affected

if TYPE_CHECKING:
    from agentdiff.api.models import APIChange, APIUsage


class APIProvider(ABC):
    """Abstract base provider for detecting API usages and managing change catalogs."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier, e.g. 'openai' or 'stripe'."""
        ...

    @property
    @abstractmethod
    def library(self) -> str:
        """Primary library package name, e.g. 'openai' or 'stripe'."""
        ...

    @property
    @abstractmethod
    def import_names(self) -> frozenset[str]:
        """Root package names associated with this provider."""
        ...

    @abstractmethod
    def get_known_changes(self) -> list[APIChange]:
        """Return the catalog of known breaking changes, deprecations, and migrations."""
        ...

    def is_provider_module(self, module_name: str) -> bool:
        """Check if a module or root import belongs to this provider."""
        root = module_name.split(".")[0]
        return root in self.import_names

    def match_usage(
        self,
        usage: APIUsage,
        change: APIChange,
        installed_sdk: SDKVersionInfo | None = None,
    ) -> bool:
        """Deterministic matching between a detected APIUsage and an APIChange."""
        if usage.provider != change.provider:
            return False

        # 1. Breaking version check
        if change.breaking_version and not is_version_affected(
            installed_sdk, change.breaking_version
        ):
            return False

        # 2. Canonical symbol matching (exact match or applicable symbols)
        applicable = change.applicable_symbols
        if usage.symbol not in applicable and change.target_symbol != usage.symbol:
            return False

        # 3. Parameter matching if target_parameter is specified
        if change.target_parameter:
            has_param = (
                change.target_parameter in usage.keyword_arguments
                or change.target_parameter in usage.arguments
            )
            if not has_param:
                return False

        # 4. Model matching if target_model is specified
        if change.target_model:
            model_arg = usage.keyword_arguments.get("model") or usage.keyword_arguments.get(
                "engine"
            )
            if model_arg is not None:
                clean_model = model_arg.strip("\"'")
                if clean_model != change.target_model:
                    return False
            else:
                clean_args = [a.strip("\"'") for a in usage.arguments]
                if change.target_model not in clean_args:
                    return False

        return True

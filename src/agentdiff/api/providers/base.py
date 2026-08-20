"""Base class for third-party API provider plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

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

    def match_usage(self, usage: APIUsage, change: APIChange) -> bool:
        """Default matching logic between a detected APIUsage and an APIChange."""
        if usage.provider != change.provider:
            return False

        # 1. Symbol matching (exact match, case-insensitive, or variant match)
        target = change.target_symbol
        target_lower = target.lower()
        usage_lower = usage.symbol.lower()

        symbol_matches = (
            usage.symbol == target
            or usage_lower == target_lower
            or usage_lower.endswith(f".{target_lower}")
            or target_lower.endswith(f".{usage_lower}")
            or (target_lower in usage_lower)
            or (
                target_lower.replace("completions", "completion")
                in usage_lower.replace("completions", "completion")
            )
        )
        if not symbol_matches:
            return False

        # 2. Parameter matching if target_parameter is specified
        if change.target_parameter:
            has_param = (
                change.target_parameter in usage.keyword_arguments
                or change.target_parameter in usage.arguments
            )
            if not has_param:
                return False

        # 3. Model matching if target_model is specified
        if change.target_model:
            model_arg = usage.keyword_arguments.get("model") or usage.keyword_arguments.get(
                "engine"
            )
            if not model_arg:
                # Check positional args or snippet
                has_model = (
                    change.target_model in usage.code_snippet
                    or change.target_model in usage.arguments
                )
            else:
                has_model = (
                    change.target_model in model_arg or model_arg == change.target_model
                )
            if not has_model:
                return False

        return True

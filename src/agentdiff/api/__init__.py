"""Self-Maintaining APIs: AST scanning, breaking change matching, and migration impact."""

from agentdiff.api.matcher import APIMatcher
from agentdiff.api.models import (
    APIChange,
    APIUsage,
    ChangeSeverity,
    ChangeType,
    MatchedChange,
    MigrationImpact,
)
from agentdiff.api.providers import (
    APIProvider,
    OpenAIProvider,
    StripeProvider,
    get_all_providers,
    get_provider,
    get_providers_for_selection,
    list_providers,
)
from agentdiff.api.scanner import APIScanner

__all__ = [
    "APIChange",
    "APIMatcher",
    "APIProvider",
    "APIScanner",
    "APIUsage",
    "ChangeSeverity",
    "ChangeType",
    "MatchedChange",
    "MigrationImpact",
    "OpenAIProvider",
    "StripeProvider",
    "get_all_providers",
    "get_provider",
    "get_providers_for_selection",
    "list_providers",
]

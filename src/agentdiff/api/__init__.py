"""Self-Maintaining APIs: AST scanning, breaking change matching, and migration impact."""

from agentdiff.api.matcher import APIMatcher
from agentdiff.api.models import (
    APIChange,
    APIUsage,
    ChangeSeverity,
    ChangeType,
    MatchedChange,
    MigrationAssessment,
    MigrationConfidence,
    MigrationImpact,
    MigrationStrategy,
    assess_migration_confidence,
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
from agentdiff.api.version_detector import (
    SDKVersionInfo,
    detect_installed_sdk_versions,
    is_version_affected,
)

__all__ = [
    "APIChange",
    "APIMatcher",
    "APIProvider",
    "APIScanner",
    "APIUsage",
    "ChangeSeverity",
    "ChangeType",
    "MatchedChange",
    "MigrationAssessment",
    "MigrationConfidence",
    "MigrationImpact",
    "MigrationStrategy",
    "OpenAIProvider",
    "SDKVersionInfo",
    "StripeProvider",
    "assess_migration_confidence",
    "detect_installed_sdk_versions",
    "get_all_providers",
    "get_provider",
    "get_providers_for_selection",
    "is_version_affected",
    "list_providers",
]

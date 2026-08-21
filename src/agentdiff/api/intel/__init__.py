"""Provider Intelligence Layer.

Turns upstream provider signals (changelogs, OpenAPI diffs, SDK releases)
into validated APIChangeManifest candidates. AI-assisted generation is
suggestion-only: the output is a manifest candidate that still requires
deterministic validation before it can drive migrations.
"""

from agentdiff.api.intel.changelog import ChangelogChange, ChangelogParser
from agentdiff.api.intel.engine import (
    IntelArtifact,
    ManifestCandidate,
    ProviderIntelEngine,
)
from agentdiff.api.intel.openapi import OpenAPIBreakingChange, OpenAPIDiffAnalyzer
from agentdiff.api.intel.release import SDKReleaseAnalyzer, SDKReleaseChange

__all__ = [
    "ChangelogChange",
    "ChangelogParser",
    "IntelArtifact",
    "ManifestCandidate",
    "OpenAPIBreakingChange",
    "OpenAPIDiffAnalyzer",
    "ProviderIntelEngine",
    "SDKReleaseAnalyzer",
    "SDKReleaseChange",
]

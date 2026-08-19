"""Repository trust compiler: canonical trust configuration for AgentDiff.

The compiler inspects a repository deterministically (languages, package
managers, tests, builds, CI, CODEOWNERS, monorepo layout, agent configs) and
produces one canonical trust configuration:

- ``agentdiff.yaml``             canonical policy including the proof plan
- ``.agentdiff/trust.lock``      content-addressed trust identity
- ``.agentdiff/repo-graph.json`` dependency/impact graph
- ``.agentdiff/proof-plan.json`` deterministic proof plan
- ``.agentdiff/adapters/*.md``   compiled agent instructions (single source)

Every decision here is deterministic file inspection. No model output is
involved in trust configuration.
"""

from .compiler import TrustCompiler, TrustCompileReport
from .graph import RepoImpactGraph
from .inspect import RepositoryInspection, RepositoryInspector

__all__ = [
    "RepoImpactGraph",
    "RepositoryInspection",
    "RepositoryInspector",
    "TrustCompileReport",
    "TrustCompiler",
]

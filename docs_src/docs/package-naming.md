---
title: Package naming decision
description: August 2026 AgentDiff collision review and release recommendation.
---

# Package naming decision — August 17, 2026

## Evidence

- The exact PyPI endpoint `pypi.org/project/agentdiff/` currently returns 404.
- The active [`agent-diff`](https://pypi.org/project/agent-diff/) package uses the spoken name “Agent Diff,” the `agentdiff.dev` domain, and an overlapping AI-agent isolation/evaluation category.
- A separate Git-native provenance tool is also publicly using AgentDiff branding and an `agentdiff` CLI.

Python package normalization does not make `agentdiff` and `agent-diff` the same index key, so the exact name appears technically available. Technical availability does not resolve user confusion, search collisions, trademark risk, support mistakes, or CLI ambiguity.

## Decision

**Do not publish under `agentdiff` yet.** Do not rename automatically in this implementation PR either.

Before publishing, maintainers should:

1. contact the adjacent projects and perform a trademark/name search;
2. compare alternative names for package, CLI, GitHub, docs, and SEO availability;
3. record a final maintain/rename decision in a dedicated PR;
4. reserve/configure PyPI ownership and Trusted Publisher only after that decision; and
5. set `AGENTDIFF_PUBLISH_APPROVED=true` only when the protected release environment is ready.

The release workflow uses OIDC Trusted Publishing and contains no long-lived PyPI token. With the repository variable unset, it builds and validates distributions but cannot publish.

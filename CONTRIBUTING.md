# Contributing to AgentDiff

AgentDiff welcomes focused fixes, adversarial tests, documentation improvements, and carefully scoped runtime integrations.

## Before you start

- Use an issue for behavior changes, security-boundary changes, or large features.
- Never include credentials, private run capsules, or exploit details in a public issue. Follow [SECURITY.md](SECURITY.md).
- Keep claims precise: observation is not enforcement, and local execution is not sandboxing.

## Development setup

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --locked --all-groups
```

## Change workflow

1. Create a focused branch from `main`.
2. Add a regression test that demonstrates the missing behavior.
3. Implement the smallest complete change.
4. Update `README.md`, `docs_src/`, examples, and security guidance when public behavior changes.
5. Run the local quality gates documented in [the contributor guide](docs_src/contributing.md).
6. Open a pull request that states behavior, trust-boundary impact, limitations, and real verification output.

## Security-sensitive changes

Scanner, policy, persistence, process, redaction, and rollback changes require tests for failure and refusal paths—not only success paths. Recovery must preserve current data when identity or post-run equality is uncertain.

Do not commit generated `site/`, coverage, cache, virtual-environment, distribution, or `.agentdiff/` run artifacts.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

# Contributing

AgentDiff welcomes focused bug fixes, tests, documentation improvements, and carefully scoped integrations.

## Development setup

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --locked --group dev --group docs --group build --extra langchain
```

## Quality gates

Run the same checks expected in CI:

```bash
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src/agentdiff
uv run pytest tests/ --cov=agentdiff --cov-report=term-missing
uv build
uv run twine check dist/*
uv run check-wheel-contents dist/*.whl
uv run mkdocs build --strict
```

Apply formatting with `uv run ruff format src tests`.

## Change workflow

1. Open an issue for behavior changes or large features.
2. Create a focused branch from `main`.
3. Add a regression test that fails for the bug or missing behavior.
4. Implement the smallest complete change.
5. Update source documentation in `docs_src/`.
6. Run all local gates.
7. Open a pull request describing behavior, risks, and verification.

Do not commit generated `site/`, `docs/`, coverage, cache, environment, or distribution artifacts.

## Framework integrations

- Keep optional framework dependencies out of the core install.
- Convert framework events into AgentDiff trajectory calls rather than duplicating evaluation logic.
- Include an integration test that runs with the corresponding extra.
- Document exactly which callback events are supported.
- Do not publish placeholder adapters.

## Documentation

```bash
uv run mkdocs serve
uv run mkdocs build --strict
```

The site is deployed from `docs_src/` by GitHub Actions. Public examples must use `kam6l/agentdiff`, source installation until PyPI exists, and implemented commands only.

## Reporting security issues

Do not post credentials, private trajectories, or environment snapshots in a public issue. Open a minimal issue requesting a private contact path when disclosure needs to remain confidential.

Be respectful, specific, and constructive in issues and reviews.

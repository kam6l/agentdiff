# Contributing

Thanks for contributing to AgentDiff! 

## Development Setup

```bash
git clone https://github.com/muskw/agentdiff
cd agentdiff
uv sync --dev
```

## Running Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=agentdiff --cov-report=html

# Specific test file
uv run pytest tests/test_agentdiff.py -v
```

## Code Style

```bash
# Format
uv run ruff format src tests

# Lint
uv run ruff check src tests

# Type check
uv run mypy src/agentdiff
```

## Pre-commit Hooks

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## Adding a New Feature

1. Create an issue describing the feature
2. Fork and create a feature branch
3. Add tests for new functionality
4. Update documentation in `docs/`
5. Submit PR with description and test results

## Adding a Framework Integration

1. Create `src/agentdiff/integrations/{name}.py` following the `BaseFrameworkAdapter` pattern
2. Register in `src/agentdiff/integrations/__init__.py`
3. Add docs in `docs/integrations/{name}.md`
4. Add integration test in `tests/test_integrations.py`

## Documentation

```bash
# Serve locally
uv run mkdocs serve

# Build
uv run mkdocs build
```

## Release Process

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create release PR
4. On merge: GitHub Actions publishes to PyPI

## Code of Conduct

Be respectful, inclusive, and constructive. See [Code of Conduct](https://github.com/muskw/agentdiff/blob/main/CODE_OF_CONDUCT.md).
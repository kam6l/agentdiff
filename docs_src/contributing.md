# Contributing

AgentDiff welcomes focused bug fixes, adversarial tests, documentation improvements, and carefully scoped integrations.

## Development setup

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --locked --all-groups
```

## Core quality gates

```bash
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src/agentdiff
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/ \
  --cov=agentdiff --cov-report=term-missing
uv run mkdocs build --strict --site-dir /tmp/agentdiff-site
uv build --out-dir /tmp/agentdiff-dist
uv run twine check /tmp/agentdiff-dist/*
uv run check-wheel-contents /tmp/agentdiff-dist/*.whl
```

Apply formatting with `uv run ruff format src tests`. Security and dependency checks configured by the repository should also pass before merge.

## Change workflow

1. Open an issue for behavior changes, new integrations, or trust-boundary changes.
2. Create a focused branch from `main`.
3. Add a regression test that fails for the bug or missing behavior.
4. Implement the smallest complete change.
5. Update README, `docs_src/`, examples, changelog, and security guidance when public behavior changes.
6. Run targeted tests, then all quality gates.
7. Open a pull request describing behavior, risks, limitations, and real verification output.

Do not commit generated `site/`, coverage, cache, environment, distribution, or `.agentdiff/` artifacts.

## Runtime security changes

Changes to scanners, policy, scoring, run storage, process handling, redaction, or rollback must test refusal paths. In particular:

- no code path may follow an untrusted symlink during capture or recovery;
- path normalization must reject absolute and parent-traversal inputs;
- rollback must preserve data when current state diverges from recorded post-state;
- process cleanup must verify PID and creation time;
- persisted evidence must not knowingly contain supplied test credentials; and
- partial observation must not be documented as enforcement or ownership.

Use synthetic values in tests. Never put a real credential in a fixture, command line, run capsule, or issue.

## Integration standards

- Keep optional framework/provider dependencies out of the core install.
- Integrate at a real execution or dispatch seam.
- Reuse policy and evidence models rather than duplicating decisions.
- Resolve unknown mutation semantics to review or deny, not silent allow.
- Include an executable integration test.
- Document bypass paths and what the adapter does not enforce.
- Do not publish placeholder adapters.

The MCP-style hook is transport-neutral; a server-specific integration must prove that all advertised dispatches pass through it.

## Documentation

```bash
uv run mkdocs serve
uv run mkdocs build --strict --site-dir /tmp/agentdiff-site
```

Public examples must use `kam6l/agentdiff`, source installation until a verified package exists, and implemented commands only. Label illustrative output and avoid claims of sandboxing, replay, complete process ownership, port ownership, or unsupported framework adapters.

## Reporting concerns

- Security issues: follow the private-first instructions in [`SECURITY.md`](https://github.com/kam6l/agentdiff/blob/main/SECURITY.md).
- Conduct concerns: follow [`CODE_OF_CONDUCT.md`](https://github.com/kam6l/agentdiff/blob/main/CODE_OF_CONDUCT.md).

Be respectful, specific, and constructive in issues and reviews.

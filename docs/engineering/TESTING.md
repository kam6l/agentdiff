# Testing and release checks

Run the smallest focused test while iterating, then the full applicable gates before handoff.

## Python

```bash
uv run pytest -p no:cacheprovider tests/
uv run ruff format --check src tests examples benchmarks demos
uv run ruff check src tests examples benchmarks demos
uv run mypy src/agentdiff
```

The desktop filesystem sandbox can block loopback sockets and descendant-process observation. A failure caused by that restriction must be rerun with the required local permissions; never change product expectations to make a sandbox-only failure pass.

Real Docker proof is opt-in locally:

```bash
AGENTDIFF_DOCKER_TESTS=1 uv run pytest -p no:cacheprovider tests/test_docker_integration.py -v -rs
```

## Website

```bash
cd website
pnpm peers check
pnpm run check
```

After the production build, verify that `dist/docs/<slug>/index.html`, `dist/404.html`, `.nojekyll`, `sitemap.xml`, local brand assets, and the social card exist. Browser QA must cover keyboard navigation, copy feedback, search, mobile drawer, deep-route refresh, console errors, and horizontal overflow at the widths listed in `DESIGN_SYSTEM.md`.

## Package and security

CI additionally builds and inspects the wheel, smoke-tests the installed CLI, audits locked runtime dependencies, runs Bandit, Dependency Review, CodeQL for Python and JavaScript/TypeScript, the recovery safety benchmark, and real Docker proof.

Changes to security invariants require explicit negative tests. A test that demonstrates only successful execution is insufficient.

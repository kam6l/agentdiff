# Development

## Prerequisites

- Python 3.12–3.14 and `uv` 0.12.5.
- Node 24.19 and pnpm 11.22 for the separate `agentdiff-web` repository.
- Docker for real clean-room proof and custom-generator integration tests.

## Setup

```bash
uv sync --locked --all-groups --extra langchain
```

Use a focused `codex/` branch from current `main`. Preserve unrelated work. Public behavior or trust-boundary changes need tests and matching README, security, website, and status updates.

## Repository conventions

- Python source lives under `src/agentdiff`; keep public exports intentional and package-local for foundations.
- Use immutable dataclasses/enums and canonical JSON-compatible identities for lifecycle evidence.
- Inject clocks, runners, runtime factories, and adapters in tests. Do not add nondeterministic network or process behavior to pure models.
- Commands are argv sequences, never shell strings.
- Reuse existing evidence, policy, proof, and delivery authorities rather than building parallel verdict paths.
- Caches, build artifacts, and `.agentdiff/` evidence are generated and must not be committed.

## Website

```bash
cd agentdiff-web
pnpm dev                 # http://127.0.0.1:5173/agentdiff-web/
pnpm run check           # lint, types, production build, static route preparation
```

`VITE_BASE_PATH` defaults to `/agentdiff-web/` for GitHub Pages. Set it explicitly in CI. The build script writes per-route HTML metadata, a sitemap, and a Pages fallback from the Vite artifact.

## Documentation ownership

This `docs/engineering/` directory is concise repository memory. User-facing documentation lives in the private `agentdiff-web` repository at `src/content/docs.ts`. Keep the two aligned but do not duplicate large manuals here.

# AgentDiff

**Your software changes itself. AgentDiff proves every change before it ships.**

[![CI](https://img.shields.io/github/actions/workflow/status/kam6l/agentdiff/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/kam6l/agentdiff/actions/workflows/ci.yml)
[![Python 3.12–3.14](https://img.shields.io/badge/Python-3.12%E2%80%933.14-171916?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![MIT](https://img.shields.io/badge/license-MIT-78f2c2?style=flat-square)](LICENSE)

[Website](https://kam6l.github.io/agentdiff-web/) · [Documentation](https://kam6l.github.io/agentdiff-web/docs/) · [Getting started](https://kam6l.github.io/agentdiff-web/docs/getting-started) · [Security](SECURITY.md)

AgentDiff is an open-source deterministic trust layer around coding agents and maintenance automation. A built-in recipe, Codex, Claude, Gemini, Copilot, or a custom worker may propose code. AgentDiff independently decides whether the exact patch is authorized, reproducible, sufficiently minimal, and proven.

```text
upstream change → exposure → untrusted patch → policy + proof
                → exact certificate → reviewable PR → outcome evidence
```

The generator is replaceable. The proof authority is not.

![A real AgentDiff rejection certificate: an unauthorized workflow change remains NOT_PROVEN](https://kam6l.github.io/agentdiff-web/product/unsafe-patch-proof.svg)

This image is rendered from the checked-in `demos/openai-failure` artifact. The worker exited successfully; AgentDiff still rejected the patch because it changed `.github/workflows/deploy.yml` outside the authorized scope.

## What ships today

The complete product path is verified Python API migration:

- bounded provider-source discovery and data-only plugin candidates;
- read-only SDK usage scan, change matching, and migration simulation;
- a narrow, fail-closed OpenAI Chat Completions → Responses AST transform;
- private generation, deterministic mutation policy, and impact analysis;
- authoritative Docker-backed clean-room proof;
- integrity-bound migration certificates;
- sealed GitHub PR delivery with no regeneration and no auto-merge; and
- explicit multi-repository Verified Campaigns with independent proof per repository.

This repository also contains tested foundations for generic `ChangeSpec`, the Maintenance Graph, deterministic priority and scheduling, DeltaProof, adversarial proof, flake classification, bounded patch minimization, Proof Lease, PR reconciliation, and post-merge outcome aggregation. They are intentionally labeled **Foundation** until wired into the default operational loop.

See the [implementation status](docs/engineering/IMPLEMENTATION_STATUS.md) for exact boundaries.

## Install

AgentDiff 0.4.x requires Python 3.12–3.14. It is not yet published on PyPI; install the current source revision explicitly:

```bash
uv tool install git+https://github.com/kam6l/agentdiff.git
agentdiff doctor --format summary
```

For development:

```bash
git clone https://github.com/kam6l/agentdiff.git
cd agentdiff
uv sync --locked --all-groups --extra langchain
uv run agentdiff --help
```

Docker is required for the default clean-room proof path and for custom/external generators. Read-only scan and simulation do not require it.

## Start with a read-only assessment

```bash
agentdiff api check --provider openai
agentdiff api simulate --provider openai --change chat_to_responses
```

`simulate` reports exact affected usages and files, generation strategy, required verification level, test/build coverage, policy constraints, and review blockers. It does not create a generation workspace, certificate, branch, commit, or pull request.

When the assessment is reviewable:

```bash
agentdiff api migrate \
  --provider openai \
  --change chat_to_responses
```

The built-in transform automates only direct keyword-based, text-only calls with supported parameters and the known `choices[0].message.content` consumer. Tools/functions, streaming, structured output, `n`, multimodal input, dynamic message builders, wrappers, expanded keyword arguments, and unusual response consumers fail closed as `NEEDS_REVIEW`.

Chat Completions remains supported by OpenAI. AgentDiff treats this as an optional behavior change; it does not invent a provider deadline.

## Independent proof

There is one normal verifier: `agentdiff.proof.ProofEngine`. A migration becomes `PROVEN` only when all configured conditions agree:

1. generation completed in the permitted runtime;
2. actual paths exactly match authorized scope;
3. deterministic mutation policy allows the change;
4. the required proof level was actually achieved;
5. trusted build, type-check, affected-test, and full-test phases pass; and
6. the exact patch, base, plan, environment, and evidence remain integrity-valid.

Anything weaker is `NOT_PROVEN`.

Migration certificates bind source provenance, repository base, expected and actual paths, generator, policy, impact, verification plan/results, patch digest, proof digest, and evidence capsule. Their SHA-256 integrity detects local modification; it is not an authenticated signature.

```bash
agentdiff api certificate verify .agentdiff/certificates/<certificate>.json
```

Verification reports `VALID`, `INVALID`, `STALE`, or `MISMATCH`.

## Use a custom coding agent without trusting it

Custom and external workers are exact-argv specifications. They do not have a host `generate()` path and never fall back to local execution:

```bash
agentdiff api migrate \
  --provider openai \
  --change chat_to_responses \
  --generator command \
  --generator-image your-reviewed-worker@sha256:<digest> \
  --generator-argv your-agent migrate-source
```

The Docker generator runtime uses a private working copy, exact argv, an empty inherited environment, non-root execution, a read-only root filesystem, dropped capabilities, no-new-privileges, no network by default, CPU/memory/PID limits, bounded output, and bounded lifecycle calls. It never mounts the live repository or Docker socket. Docker unavailable, weakened capability evidence, timeout, or output overflow is a refusal.

The private temporary copy is currently bind-mounted into a container, and containers share the host kernel. That is a strong container boundary, not a VM or zero-host-mount claim.

## Deliver the exact proven patch

After a `PROVEN` result, `--open-pr` replays the sealed patch into a temporary Git worktree:

```bash
agentdiff api migrate \
  --provider openai \
  --change chat_to_responses \
  --open-pr \
  --base-branch main
```

Delivery requires a clean tracked worktree, unchanged certified base, `origin`, and authenticated `gh`. It verifies base/result digests, stages only sealed paths, pushes a dedicated branch, and creates a certificate-backed PR body. It never regenerates or auto-merges.

## Coordinate Verified Campaigns

```bash
agentdiff fleet simulate --config demos/fleet/fleet.yaml
agentdiff fleet migrate --config demos/fleet/fleet.yaml
agentdiff fleet verify .agentdiff/campaigns/openai-responses-2026.json
```

Every affected repository runs its own migration and proof. The aggregate binds child certificate, certificate-integrity, patch, and proof digests; it cannot become `PROVEN` unless every affected repository is independently proven.

Campaigns accept explicit local directories. They do not discover an organization, clone URLs, bulk merge, or provide a hosted dashboard.

## General trust commands

| Command | Purpose |
|---|---|
| `agentdiff init` / `bootstrap` | Compile repository trust configuration and proof plans |
| `agentdiff wrap -- <agent>` | Run a worker through the local sidecar pipeline |
| `agentdiff run -- <cmd>` | Record a local command transaction |
| `agentdiff prove <run-id>` | Run clean-room proof for a sealed patch |
| `agentdiff promote <run-id>` | Conflict-check and promote proven evidence |
| `agentdiff repair <run-id>` | Run the bounded general repair loop |
| `agentdiff inspect` / `verify` / `runs` | Inspect and validate evidence capsules |
| `agentdiff rollback <run-id> --safe-only` | Recover eligible regular-file collateral |
| `agentdiff trust` / `impact` / `proof cache-status` | Inspect trust and proof planning |
| `agentdiff workspace status/warm/prune` | Manage immutable warm snapshots |

> [!IMPORTANT]
> `agentdiff run` observes a normal host subprocess. It is not OS isolation, and local filesystem policy is primarily a post-condition check. Use a disposable unprivileged workspace or reviewed external sandbox for untrusted general commands. The API custom-generator path is separate and fails closed to Docker.

## Reproducible demos

```bash
agentdiff api simulate \
  --root demos/openai-success \
  --provider openai \
  --change chat_to_responses
```

- `demos/openai-success`: supported text-only migration and explicit Docker proof commands.
- `demos/openai-failure`: unsafe worker that also edits a deployment workflow; policy rejects it.
- `demos/fleet/fleet.yaml`: one supported, one review-required, and one unaffected repository.

Website proof surfaces are captured from these fixtures and preserve their real simulation or rejection status. They are not fabricated customer results.

## Website and documentation

The canonical warm editorial site and complete docs IA are maintained in the private `agentdiff-web` repository and deploy to GitHub Pages at [kam6l.github.io/agentdiff-web](https://kam6l.github.io/agentdiff-web/).

```bash
cd agentdiff-web
pnpm install --frozen-lockfile
pnpm dev
pnpm run check
```

The production build creates crawlable deep-route HTML, route-specific metadata, sitemap, `.nojekyll`, and a Pages fallback under the `/agentdiff-web/` base path.

## Development checks

```bash
uv run pytest -p no:cacheprovider tests/
uv run ruff format --check src tests examples benchmarks demos
uv run ruff check src tests examples benchmarks demos
uv run mypy src/agentdiff

cd agentdiff-web
pnpm run check
```

The public repository CI adds cross-platform Python coverage, Docker proof, dependency auditing, Bandit, Python CodeQL, package build/smoke testing, and the recovery safety benchmark. The website repository independently validates lint, types, production builds, dependency changes, and JavaScript/TypeScript CodeQL.

Read [AGENTS.md](AGENTS.md) for the repository map, [SECURITY.md](SECURITY.md) for the full threat model, and [CONTRIBUTING.md](CONTRIBUTING.md) before changing trust boundaries. AgentDiff is MIT-licensed pre-release software.

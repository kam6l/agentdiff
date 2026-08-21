# AgentDiff

**Let any coding agent write the patch. Independently prove the exact change before it ships.**

[![CI](https://img.shields.io/github/actions/workflow/status/kam6l/agentdiff/ci.yml?branch=main&style=flat-square&label=CI)](https://github.com/kam6l/agentdiff/actions/workflows/ci.yml)
[![Python 3.12–3.14](https://img.shields.io/badge/Python-3.12%E2%80%933.14-171916?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![MIT](https://img.shields.io/badge/license-MIT-78f2c2?style=flat-square)](LICENSE)

[Website](https://agentdiff.usernameort.chatgpt.site/) · [Documentation](https://agentdiff.usernameort.chatgpt.site/docs) · [Quick start](https://agentdiff.usernameort.chatgpt.site/docs/getting-started) · [Security](SECURITY.md)

AgentDiff is a local, deterministic trust layer for autonomous software changes. Its first complete product path is verified API migration:

```text
provider signal → usage scan → migration plan → untrusted patch
                → policy → impact → clean-room proof → certificate → reviewable PR
```

The generator is replaceable. The trust decision is not delegated to the generator.

> [!IMPORTANT]
> The default `ProofEngine` uses Docker for clean-room verification. The general `agentdiff run` local backend observes a normal host subprocess and is not a security sandbox. Read [SECURITY.md](SECURITY.md) before running untrusted commands.

## Install from source

AgentDiff 0.4.0 requires Python 3.12–3.14. The package is not yet published on PyPI; install the current source revision explicitly.

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

## Verified API migration

Start read-only:

```bash
agentdiff api check --provider openai
agentdiff api simulate --provider openai --change chat_to_responses
```

`simulate` reports affected usages and files, the generation strategy, required verification level, test/build coverage, policy constraints, and review blockers without modifying the repository.

Run the migration only after the simulation is reviewable:

```bash
agentdiff api migrate \
  --provider openai \
  --change chat_to_responses
```

The default OpenAI transform automates only a narrow, text-only shape:

- keyword-only `client.chat.completions.create(...)` calls;
- literal system/user/assistant message dictionaries with text content;
- `model`, `store`, `temperature`, `top_p`, and token-limit parameters; and
- response values consumed as `choices[0].message.content`.

Tools/functions, streaming, structured output, `n`, multimodal content, dynamic message builders, wrappers, expanded keyword arguments, and unusual response consumers fail closed as `NEEDS_REVIEW`. Chat Completions is still supported by OpenAI; this migration is optional and classified as a behavior change.

The generated patch remains in a private workspace and is captured as untrusted evidence. The host source tree is not changed by `api migrate`.

## Verified Campaigns

Coordinate the same provider change across an explicit set of local repositories:

```bash
agentdiff fleet simulate --config fleet.yaml
agentdiff fleet migrate --config fleet.yaml
agentdiff fleet verify .agentdiff/campaigns/openai-responses-2026.json
```

Every affected repository runs through the existing `MigrationEngine` and authoritative `ProofEngine` independently. The campaign report records per-repository `PROVEN`, `NEEDS_REVIEW`, `REJECTED`, `UNAFFECTED`, or `ERROR` outcomes. Its SHA-256 digest binds each child certificate ID, certificate integrity digest, patch digest, and proof digest.

Campaigns accept only explicitly configured local directories. They do not discover repositories, clone URLs, create bulk pull requests, merge changes, or provide a hosted dashboard. A campaign cannot become `PROVEN` unless every affected repository is independently proven.

## Proof and certificates

There is one authoritative verifier: `agentdiff.proof.ProofEngine`. The final migration verdict is `PROVEN` only when all required conditions agree:

- generation completed;
- actual files exactly match the expected scope;
- deterministic mutation policy allows the change;
- the requested proof level was actually achieved;
- build, type-check, affected tests, and full tests satisfy the proof plan; and
- the exact patch and evidence capsule remain integrity-valid.

Anything weaker is `NOT_PROVEN`.

Migration certificates bind the provider source, repository base SHA, expected and actual files, generator, policy, blast radius, verification plan/results, patch digest, proof digest, and evidence capsule. They provide SHA-256 integrity and freshness checks; they are **not cryptographic signatures**.

```bash
agentdiff api certificate verify .agentdiff/certificates/<certificate>.json
```

Verification reports `VALID`, `INVALID`, `STALE`, or `MISMATCH`.

## Verified pull requests

After a `PROVEN` result, `--open-pr` can replay the sealed patch into a temporary Git worktree and open a GitHub pull request:

```bash
agentdiff api migrate \
  --provider openai \
  --change chat_to_responses \
  --open-pr \
  --base-branch main
```

This path requires a clean tracked worktree, an unchanged certified base SHA, an `origin` remote, and an authenticated `gh` CLI. AgentDiff re-verifies every base and result file digest, stages only sealed paths, pushes a dedicated branch, and creates a PR body from the certificate. It never regenerates during delivery and never auto-merges.

## Any coding agent as the worker

The built-in deterministic AST transform is the default. A custom coding-agent command can be used as an untrusted generator:

```bash
agentdiff api migrate \
  --provider openai \
  --change chat_to_responses \
  --generator command \
  --generator-argv your-agent migrate-source
```

The worker receives a private copy of the sealed source snapshot. AgentDiff captures changes only from that copy, but a custom command still runs with the caller's host permissions: this is observation, not an OS sandbox. Use only trusted commands until a sandbox-backed generator runtime is configured. Exact argv, time/output bounds, generated files, and generator identity are recorded. Missing expected edits, extra files, or policy violations force `NOT_PROVEN` even when the raw test command exits successfully.

## Provider intelligence

Create a data-only provider definition and configure official HTTPS sources:

```bash
agentdiff provider init acme
agentdiff provider discover acme
```

Remote fetches are bounded by scheme, redirect count, DNS/IP validation, time, size, and content type. Responses are cached with provenance, validators, and a SHA-256 digest. Provider discovery emits untrusted manifest candidates; it never applies them directly.

Provider plugins default to `DATA_ONLY`. Python transform code is not imported during install or list operations. Executable provider code requires both `TRUSTED_CODE` metadata and explicit caller opt-in.

## Reproducible demos

The repository includes focused OpenAI and campaign fixtures:

```bash
agentdiff api simulate \
  --root demos/openai-success \
  --provider openai \
  --change chat_to_responses
```

- `demos/openai-success` is the supported text-only migration with explicit Docker proof commands.
- `demos/openai-failure` includes a deliberately unsafe worker that also edits a deployment workflow. Policy rejects the unexpected file and the verdict stays `NOT_PROVEN`.
- `demos/fleet/fleet.yaml` combines one supported, one review-required, and one unaffected repository for a read-only Verified Campaigns demo.

## Foundation commands

The same trust infrastructure also supports general coding-agent transactions:

| Command | Purpose |
|---|---|
| `agentdiff init` / `bootstrap` | Compile repository trust configuration and proof plans |
| `agentdiff wrap -- <agent>` | Run an agent through the local sidecar pipeline |
| `agentdiff run -- <cmd>` | Record an explicit local command transaction |
| `agentdiff prove <run-id>` | Run clean-room proof for a sealed patch |
| `agentdiff promote <run-id>` | Conflict-check and promote proven evidence |
| `agentdiff repair <run-id>` | Run the bounded general repair loop |
| `agentdiff inspect` / `verify` / `runs` | Inspect and validate evidence capsules |
| `agentdiff rollback <run-id> --safe-only` | Recover eligible regular-file collateral |
| `agentdiff trust` / `impact` / `proof cache-status` | Inspect trust compilation and proof planning |
| `agentdiff workspace status/warm/prune` | Manage immutable warm workspace snapshots |

The general `repair` loop is implemented, but `api migrate` does not invoke it automatically in 0.4.0. A failed API migration is preserved as evidence and returned for review.

## Available now and coming next

Available now:

- OpenAI Python usage scanning and a fail-closed Chat Completions → Responses transform;
- read-only simulation, private generation, deterministic policy, impact analysis, clean-room proof, integrity certificates, and verified-PR delivery;
- explicit multi-repository Verified Campaigns with integrity-bound child evidence;
- data-only custom providers and bounded official-source discovery;
- general transaction, proof, promotion, repair, recovery, and workspace primitives; and
- Linux/macOS/Windows CI across Python 3.12–3.14, package validation, dependency auditing, Bandit, and CodeQL.

Coming next:

- broader deterministic OpenAI shapes and additional provider migrations;
- automatic API-specific repair-loop integration;
- authenticated certificate signatures and external transparency storage; and
- a maintained hosted isolation backend.

There is no hosted dashboard, telemetry service, or hidden approval system. Evidence stays under the repository's `.agentdiff/` directory unless the user deliberately shares it.

## Development

```bash
uv run pytest -p no:cacheprovider tests/
uv run ruff format --check src tests examples benchmarks demos
uv run ruff check src tests examples benchmarks demos
uv run mypy src/agentdiff
uv build
uv run twine check dist/*
uv run check-wheel-contents dist/*.whl
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and [CHANGELOG.md](CHANGELOG.md). AgentDiff is MIT licensed pre-release software.

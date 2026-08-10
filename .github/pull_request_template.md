## What changed?

<!-- Explain the behavior change and why it is needed. -->

## Capability boundary

<!-- Mark the strongest capability this PR actually provides. Do not use these as synonyms. -->

- [ ] Observation only
- [ ] Pre-dispatch interception
- [ ] Deterministic blocking
- [ ] Sandboxing / isolation
- [ ] Recovery / rollback
- [ ] No runtime-security behavior change

## Verification

- [ ] Added or updated regression tests, including refusal/error paths
- [ ] `uv run ruff format --check src tests examples`
- [ ] `uv run ruff check src tests examples`
- [ ] `uv run mypy src/agentdiff`
- [ ] `PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider tests/`
- [ ] `uv run mkdocs build --strict` when docs changed
- [ ] Package and security gates when dependencies or build metadata changed

## Security and privacy

<!-- Address relevant path/symlink, process identity, redaction, persistence, network, rollback, and platform risks. -->

- [ ] No real credentials or private run artifacts are included
- [ ] Public claims match tested behavior and limitations
- [ ] Destructive behavior fails closed on ambiguity

## Compatibility and follow-up

<!-- Note public API/schema changes, migration, platforms tested, and explicitly deferred work. -->

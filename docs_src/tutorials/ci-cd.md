# CI quality gate

AgentDiff can return a nonzero exit status when a saved run falls below its cleanliness threshold or triggers another evaluation failure.

## GitHub Actions example

Until a package is released, pin installation to a Git commit instead of assuming PyPI availability.

```yaml
name: Agent quality

on:
  pull_request:

jobs:
  evaluate:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Install pinned AgentDiff source
        run: |
          uv venv
          uv pip install "agentdiff @ git+https://github.com/kam6l/agentdiff.git@<commit-sha>"

      - name: Capture baseline
        run: uv run agentdiff snapshot --root "$GITHUB_WORKSPACE" -o before.json

      - name: Run the agent
        run: uv run python scripts/run_agent.py
        # The runner must save trajectory.json.

      - name: Capture final state
        run: uv run agentdiff snapshot --root "$GITHUB_WORKSPACE" -o after.json

      - name: Gate the run
        run: |
          uv run agentdiff eval trajectory.json \
            --pre before.json \
            --post after.json \
            --root "$GITHUB_WORKSPACE" \
            --target src/evaluator.py,tests/test_evaluator.py \
            --threshold 0.80 \
            --format json \
            --fail-on-failure > agentdiff-result.json

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: agentdiff-evaluation
          path: |
            before.json
            after.json
            trajectory.json
            agentdiff-result.json
          if-no-files-found: warn
```

Replace `<commit-sha>` with a reviewed AgentDiff commit. Avoid tracking `main` in a security-sensitive pipeline.

## Evaluating inside this repository

The AgentDiff repository itself uses its lockfile:

```yaml
- uses: astral-sh/setup-uv@v7
- run: uv sync --locked --group dev --group docs --group build
- run: uv run pytest tests/ --cov=agentdiff
- run: uv run ruff check src tests
- run: uv run mypy src/agentdiff
```

## Other CI systems

The quality gate is not GitHub-specific. The portable sequence is:

```bash
agentdiff snapshot --root "$WORKSPACE" -o before.json
python run_agent.py
agentdiff snapshot --root "$WORKSPACE" -o after.json
agentdiff eval trajectory.json \
  --pre before.json --post after.json \
  --root "$WORKSPACE" --target src/expected.py \
  --threshold 0.8 --fail-on-failure
```

## Make runs reproducible

- Start from a clean checkout or disposable workspace.
- Pin the agent, model configuration, and AgentDiff revision.
- Disable process and port capture when unrelated runner services create noise.
- Wait for intended child processes to exit before the final snapshot.
- Keep secrets out of trajectory tool arguments and results.
- Upload raw artifacts when a gate fails.
- Establish thresholds from repeated baseline runs rather than choosing one arbitrarily.

`--format json` writes the same evaluation data used for the exit decision; no separate JUnit or hosted dashboard feature is implied.

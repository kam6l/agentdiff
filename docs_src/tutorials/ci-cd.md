# CI runtime gate

AgentDiff can wrap the same agent command used in CI and return a nonzero status when policy resolves to `deny` or, optionally, `review`.

The local backend is still not a sandbox. Use an ephemeral runner or external sandbox for untrusted code.

## Commit a policy

Store an explicit `agentdiff.yaml` beside the workflow. A CI policy should normally:

- deny credentials, VCS internals, and deployment keys;
- allow only the task's expected output paths;
- review dependency and workflow files;
- bound changed files, deletions, descendants, duration, and backup size; and
- disable machine-wide port observation when it is not a useful signal.

Validate it before running the agent:

```bash
agentdiff policy validate --policy agentdiff.yaml
```

## GitHub Actions example

AgentDiff is not published on PyPI yet. Pin the repository to a reviewed full commit SHA instead of tracking `main`.

```yaml
name: Agent runtime gate

on:
  pull_request:

permissions:
  contents: read

jobs:
  agent-runtime:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Install reviewed AgentDiff source
        env:
          AGENTDIFF_SHA: <full-reviewed-commit-sha>
        run: |
          git clone --filter=blob:none https://github.com/kam6l/agentdiff.git "$RUNNER_TEMP/agentdiff"
          git -C "$RUNNER_TEMP/agentdiff" checkout --detach "$AGENTDIFF_SHA"
          uv venv "$RUNNER_TEMP/agentdiff-venv"
          uv pip install --python "$RUNNER_TEMP/agentdiff-venv/bin/python" "$RUNNER_TEMP/agentdiff"
          echo "AGENTDIFF=$RUNNER_TEMP/agentdiff-venv/bin/agentdiff" >> "$GITHUB_ENV"

      - name: Validate mutation policy
        run: "$AGENTDIFF" policy validate --policy agentdiff.yaml

      - name: Run agent transaction
        id: agentdiff
        shell: bash
        run: |
          set +e
          "$AGENTDIFF" run \
            --root "$GITHUB_WORKSPACE" \
            --policy agentdiff.yaml \
            --task "Apply requested change" \
            --format json \
            --fail-on review \
            -- python3 scripts/run_agent.py > agentdiff-result.json
          status=$?
          set -e
          "$AGENTDIFF" runs --root "$GITHUB_WORKSPACE" --format json > agentdiff-runs.json
          exit "$status"

      - name: Upload redacted summaries
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: agentdiff-runtime-summary
          path: |
            agentdiff-result.json
            agentdiff-runs.json
          if-no-files-found: warn
          retention-days: 7
```

For a security-sensitive repository, replace action tags with organization-reviewed full action commit SHAs. The AgentDiff repository itself pins workflow actions.

## Exit behavior

`agentdiff run` supports:

```bash
--fail-on never   # report only
--fail-on deny    # default; fail denied process/path decisions
--fail-on review  # fail review or deny
```

Child failures and launch errors are also nonzero. See the [CLI reference](../cli.md#exit-status) for exact statuses.

A denied filesystem decision is a post-condition finding in local mode: the write may already have occurred. On an ephemeral CI runner, fail the job and discard the workspace. Do not describe the gate as syscall blocking.

## Artifacts and secrets

Run capsules can contain paths, task text, executable metadata, platform details, fingerprints, policy decisions, and redacted event fields. Redaction is defense in depth, not proof that all domain-specific secrets are absent.

- Upload summary JSON only unless the full capsule is required.
- Review artifacts before broadening access or retention.
- Never upload before-state backups from a private workspace by default.
- Use synthetic credentials in tests.
- Keep `.agentdiff/` out of caches and source-control commits.

## Legacy evaluator gate

Existing users can continue to capture `before.json` and `after.json`, save a trajectory, then invoke `agentdiff eval --fail-on-failure`. That path gates the legacy cleanliness metric; it does not apply runtime policy or prepare rollback.

## Reproducibility

- Start from a clean checkout or disposable workspace.
- Pin AgentDiff, the agent, model configuration, tools, and dependencies.
- Keep policy and collector settings identical between variants.
- Run stochastic agents repeatedly and report distributions.
- Pair mutation safety with task-correctness tests.
- Treat process and port observations as noisy on shared runners.

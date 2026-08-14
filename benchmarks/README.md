# AgentDiff local recovery regression suite

`benchmarks/safetybench.py` is a deterministic adversarial regression suite for the local runtime boundary. It is not an industry benchmark, an LLM-quality leaderboard, or a performance claim.

It exercises five cases in temporary workspaces:

1. an allowed write remains allowed with zero blast radius;
2. a denied file creation is detected and selectively recovered;
3. a legitimate post-run edit becomes a rollback conflict and is preserved;
4. a directory symlink is recorded without traversing its target; and
5. a denied executable is not launched.

Run it with:

```bash
uv run python3 benchmarks/safetybench.py --output /tmp/agentdiff-recovery-regression.json
```

The process exits nonzero if any assertion fails. Durations are diagnostic only and have no pass threshold because shared CI runners are noisy. The regular pytest suite remains the detailed regression source.

# Local SafetyBench

AgentDiff includes a deterministic adversarial smoke benchmark for its local runtime boundary. It is not an LLM-quality leaderboard, performance guarantee, or proof of sandbox isolation.

## Cases

The harness creates a fresh temporary workspace for each case and asserts that:

1. an allowed write remains allowed with zero blast radius;
2. a denied file creation is detected and selectively recovered;
3. a legitimate edit made after the run becomes a rollback conflict and is preserved;
4. a directory symlink is recorded without traversing its target; and
5. a denied executable is not launched.

## Run it

```bash
uv run python3 benchmarks/safetybench.py \
  --output /tmp/agentdiff-safetybench.json
```

The process exits nonzero if any case fails. JSON includes each result and elapsed milliseconds. Durations are diagnostic only: there is no timing threshold because local and shared CI environments vary.

The pytest suite contains the detailed unit and integration regressions. SafetyBench exists to exercise the five security invariants together through public APIs and to produce a compact CI artifact.

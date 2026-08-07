# Regression testing agent runs

AgentDiff does not ship a benchmark runner. It supplies run-level state and trajectory metrics that you can collect inside your own repeatable harness.

## What to compare

Useful regression signals include:

- task tests or an external outcome score
- cleanliness score
- unintended mutation count
- critical and warning side effects
- tool success rate
- loop and redundant-call counts
- token use and duration as supporting diagnostics

AgentDiff is not primarily a speed benchmark. A fast run with collateral mutations is still a poor run.

## Minimal harness

```python
import json
from pathlib import Path

from agentdiff import AgentDiffConfig, AgentDiffSession


def evaluate_variant(name, run_agent, workspace):
    config = AgentDiffConfig(
        root=str(workspace),
        target_paths=["src/target.py"],
        capture_processes=False,
        capture_ports=False,
    )

    with AgentDiffSession(f"Regression: {name}", config) as session:
        run_agent(session)

    result = session.evaluate()
    return {
        "variant": name,
        "passed": result.passed,
        "cleanliness": result.metrics.cleanliness_score,
        "unintended_mutations": result.metrics.unintended_mutations,
        "efficiency": result.metrics.efficiency_score,
        "tool_success_rate": result.metrics.success_rate,
        "side_effects": [effect.to_dict() for effect in result.side_effects],
    }


rows = []
for name, agent in variants.items():
    reset_fixture(Path("/tmp/agent-benchmark"))
    rows.append(evaluate_variant(name, agent, Path("/tmp/agent-benchmark")))

Path("agent-regressions.json").write_text(json.dumps(rows, indent=2))
```

Your `run_agent(session)` function should call `session.record(...)` at its tool-execution seam.

## Fair comparisons

1. Restore the same fixture before every run.
2. Run variants in isolated directories or containers.
3. Use the same declared target set.
4. Keep collector settings identical.
5. Repeat stochastic agents and report distributions, not only the best run.
6. Pair AgentDiff metrics with task correctness.
7. Preserve raw trajectories and state diffs for failures.

## CI regression policy

A practical policy might fail when:

- task tests fail;
- cleanliness falls below a historical floor;
- unintended mutations increase;
- a new critical side effect appears; or
- loop counts exceed a known baseline.

Do not compare token counts across providers without accounting for tokenizer and usage-reporting differences. Process and port measurements can also vary on shared runners, so disable those collectors when they are not part of the behavior under test.

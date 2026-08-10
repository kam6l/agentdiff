# Cleanliness score

!!! note "Legacy evaluator metric"
    Cleanliness belongs to the original snapshot/trajectory evaluator. New runtime transactions use deterministic [policy decisions](policy.md) and [blast-radius scoring](blast-radius.md). The two scores have different scales and meanings.

Cleanliness measures whether an agent stayed inside its declared evaluator target set.

$$\text{cleanliness} = \frac{\text{intended mutations}}{\text{all observed mutations}}$$

Every filesystem, fingerprinted environment, PID-set, and listening-port-set diff counts as one mutation. A run with no observed mutations receives `1.0`. If targets were not explicitly supplied, observed mutations are treated as unintended. Process and port entries are snapshot differences, not causal ownership evidence.

## Example

An agent was asked to modify `src/evaluator.py`:

```text
M  src/evaluator.py   intended
+  debug.log          unintended
~  AGENT_MODE         unintended
```

The cleanliness score is `1 / 3 = 0.333`.

This score is intentionally narrow: it measures mutation focus, not answer correctness. Pair it with task tests or another outcome evaluator.

## Declare intended targets

The framework-neutral API resolves relative targets against `root`:

```python
from agentdiff import AgentDiffConfig

config = AgentDiffConfig(
    root="/workspace",
    target_paths=["src/evaluator.py", "tests/test_evaluator.py"],
)
```

For direct evaluator usage, pass the paths exactly as they appear in snapshot diffs:

```python
evaluator.set_target_mutations([
    "/workspace/src/evaluator.py",
    "/workspace/tests/test_evaluator.py",
])
```

For the CLI:

```bash
agentdiff eval trajectory.json \
  --pre before.json --post after.json \
  --root /workspace \
  --target src/evaluator.py,tests/test_evaluator.py \
  --threshold 0.8 \
  --fail-on-failure
```

## Interpreting the result

There are no built-in letter grades. Choose a threshold based on the risk of the task and establish a baseline before gating:

- `1.0`: every observed mutation was declared
- `0.8`: four of five mutations were declared
- `0.5`: half the mutations were collateral
- `0.0`: mutations occurred, but none matched a declared target

The complete result also includes trajectory efficiency, tool success rate, mutation counts, and classified side effects.

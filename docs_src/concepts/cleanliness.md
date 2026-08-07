# Cleanliness Score

The **Cleanliness Score** is AgentDiff's core metric — a single number that quantifies how surgically precise an agent was.

## Formula

$$\text{Cleanliness} = \frac{\text{Target Mutations}}{\text{Total Mutations}}$$

Where:
- **Target Mutations** = Changes to files/dirs/paths explicitly listed in `target_paths`
- **Total Mutations** = All filesystem changes (create + modify + delete) + environment changes + process spawns + port opens

## Interpretation

| Score | Grade | Meaning |
|-------|-------|---------|
| 1.00 | A+ | Perfect — only touched exactly what was intended |
| 0.90–0.99 | A | Excellent — minimal collateral damage |
| 0.70–0.89 | B | Good — some noise but mostly on target |
| 0.50–0.69 | C | Mediocre — significant side effects |
| 0.30–0.49 | D | Poor — more damage than progress |
| < 0.30 | F | Destructive — agent is a liability |

## Example

```
Target paths: ["/repo/src/calculator.py"]

Agent run:
  ✅ Modified /repo/src/calculator.py (target)
  ⚠️ Modified /repo/src/utils.py (not target)
  ⚠️ Created /repo/debug.log (not target)
  ⚠️ Deleted /repo/config.bak (not target)

Target Mutations: 1
Total Mutations: 4
Cleanliness: 0.25 (25%) — Grade F
```

## Why This Matters

Traditional metrics (pass/fail, test coverage) miss this entirely. An agent that "passes" but leaves 47 temp files, modifies 3 config files, and spawns 12 orphan processes is **not production-ready** — even if the tests pass.

Cleanliness Score makes this visible, measurable, and actionable.

## Configuration

Set your quality gate in `agentdiff.yaml`:

```yaml
cleanliness_threshold: 0.8  # Fail CI below this
```

Or via CLI:
```bash
agentdiff eval --trajectory run.json --fail-below 0.85
```

## Related

- [Side Effects](side-effects.md) — How individual mutations are classified
- [Trajectory Tracking](trajectory.md) — Step-level attribution
- [CI/CD Integration](../tutorials/ci-cd.md) — Using cleanliness as a gate
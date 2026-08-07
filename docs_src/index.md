# AgentDiff

**Full-state trajectory evaluation for AI agents**

---

## The Problem

Traditional benchmarks tell you **whether** an agent succeeded:

```
✅ PASS  — Tests pass
```

AgentDiff tells you **how** it succeeded — and what it broke along the way:

```
Cleanliness Score: 33%  ❌
Side Effects:
  ⚠️ WARNING: Modified /etc/config.yaml (outside target scope)
  ⚠️ WARNING: Created /tmp/debug_47.log (unexpected file)
  ℹ️ INFO: Spawned 3 background processes
```

---

## Core Metric: Cleanliness Score

$$\text{Cleanliness} = \frac{\text{Target Mutations}}{\text{Total Mutations}}$$

- **1.0** = Surgical precision — only touched intended files
- **0.5** = Half the changes were collateral damage
- **0.0** = Pure chaos — nothing intentional achieved

---

## What It Tracks

| Layer | Captured |
|-------|----------|
| **Filesystem** | Every file create/modify/delete with SHA256 content hashes |
| **Environment** | Env vars, working directory, umask |
| **Processes** | PIDs, command lines, parent/child relationships |
| **Network** | Open ports, connections, bound interfaces |
| **Trajectory** | Step-by-step tool calls, inputs, outputs, durations, LLM tokens |

---

## Quick Example

```python
from agentdiff import AgentDiffSession

with AgentDiffSession(
    paths=["/repo"],
    target_paths=["/repo/calculator.py"]
) as session:
    agent.run("Fix the add() function")

report = session.evaluate()

print(f"Cleanliness: {report.cleanliness_score:.1%}")
# Cleanliness: 33.3%

for effect in report.side_effects:
    print(f"  {effect.severity}: {effect.description}")
```

---

## Who Uses AgentDiff

- **Agent Framework Builders** — Benchmark implementations objectively
- **Researchers** — Publish reproducible trajectory analyses
- **Enterprise Teams** — Gate deployments: "Cleanliness > 0.85 or no deploy"
- **Open Source Maintainers** — Detect scope creep in contributor agents

---

## Get Started

```bash
pip install agentdiff
agentdiff init
```

→ [Quickstart Guide](quickstart.md) | [CLI Reference](cli.md) | [Python API](api.md)
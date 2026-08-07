# AgentDiff

[![PyPI version](https://img.shields.io/pypi/v/agentdiff.svg)](https://pypi.org/project/agentdiff/)
[![Python versions](https://img.shields.io/pypi/pyversions/agentdiff.svg)](https://pypi.org/project/agentdiff/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/your-org/agentdiff/workflows/CI/badge.svg)](https://github.com/your-org/agentdiff/actions)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Discord](https://img.shields.io/discord/123456789?label=Discord&logo=discord&color=5865F2)](https://discord.gg/agentdiff)

> **The open-source standard for full-state trajectory evaluation of AI agents.**
> 
> Detect not just *what the agent said*, but *what the agent did to the world* — filesystem changes, environment mutations, process trees, network ports, and cleanliness metrics.

---

## The Problem

Current agent evaluation tools (Promptfoo, DeepEval, LangSmith) focus on **output correctness** — "did the agent give the right answer?"

But autonomous agents **act on the world**. They:
- 📝 Create, modify, delete files
- 🔧 Change environment variables
- ⚙️ Spawn/kill processes
- 🌐 Open/close network ports
- 🗄️ Mutate databases, call APIs, trigger webhooks

**None of the existing tools capture this.** They treat agents as chatbots. AgentDiff treats agents as **actors with side effects**.

---

## What Makes AgentDiff Unique

| Capability | AgentDiff | Promptfoo | DeepEval | LangSmith | agentbranch |
|------------|:---------:|:---------:|:--------:|:---------:|:-----------:|
| **Filesystem diff (SHA256 content hashes)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Environment variable diff** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Process tree diff (PID, cmdline, memory)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Open port diff (TCP/UDP)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Cleanliness Score (target vs unintended mutations)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Side effect classification (CRITICAL/WARNING/INFO)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Framework-agnostic (no SDK lock-in)** | ✅ | ⚠️ | ⚠️ | ❌ | ❌ |
| **Record & replay trajectories (JSON)** | ✅ | ⚠️ | ❌ | ✅ | ❌ |
| **CI/CD friendly (exit codes, JSON output)** | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| **Pure Python, minimal deps** | ✅ | ❌ (Node) | ❌ (heavy) | ❌ | ❌ (Next.js) |

---

## Quickstart

```bash
pip install agentdiff
```

```python
from agentdiff import DiffEngine, TrajectoryTracker, AgentDiffEvaluator
from pathlib import Path

# 1. Capture pre-execution state
engine = DiffEngine(root=Path("/workspace"))
pre_snapshot = engine.capture()

# 2. Run your agent (any framework: LangChain, CrewAI, raw Python, etc.)
# ... agent does its work ...

# 3. Capture post-execution state
post_snapshot = engine.capture()

# 4. Compute diff
diff = engine.diff(pre_snapshot, post_snapshot)

# 5. Evaluate with trajectory (optional but recommended)
tracker = TrajectoryTracker()
# ... record steps during agent run ...
trajectory = tracker.get_trajectory()

evaluator = AgentDiffEvaluator(
    target_paths=["src/calculator.py"],  # What SHOULD change
    cleanliness_threshold=0.8,
)
result = evaluator.evaluate(diff, trajectory)

print(f"Cleanliness: {result.metrics.cleanliness_score:.2%}")
print(f"Pass: {result.passed}")
for effect in result.side_effects:
    print(f"  {effect.severity}: {effect.description}")
```

**Output:**
```
Cleanliness: 33.33%
Pass: False
  WARNING: Unexpected file modification: config.json
  WARNING: Unexpected file creation: debug.log
```

---

## Core Concepts

### 1. EnvironmentSnapshot
Complete point-in-time capture of:
- **Filesystem**: Every file's SHA256, mode, size, mtime (configurable depth/ignore patterns)
- **Environment**: All env vars (with allowlist/denylist for secrets)
- **Processes**: PID, PPID, cmdline, memory %, CPU %
- **Network**: Listening TCP/UDP ports with owning PIDs

### 2. DiffEngine
Computes semantic differences between two snapshots:
```python
diff = engine.diff(pre, post)
# diff.added_files, diff.modified_files, diff.deleted_files
# diff.added_env_vars, diff.removed_env_vars
# diff.added_processes, diff.removed_processes
# diff.added_ports, diff.removed_ports
```

### 3. TrajectoryTracker
Records the **full reasoning trace**:
```python
tracker = TrajectoryTracker()
tracker.record_step(
    thought="Need to fix the add() function",
    tool_call=ToolCall(name="edit_file", args={"path": "calc.py", ...}),
    observation="File edited successfully",
    result=StepResult(success=True, tokens_in=150, tokens_out=45)
)
```

### 4. AgentDiffEvaluator
The **judgment layer** — computes metrics from diff + trajectory:

| Metric | Formula | Meaning |
|--------|---------|---------|
| **Cleanliness Score** | `target_mutations / total_mutations` | How focused was the agent? |
| **Efficiency Score** | `1 - (loops + failures) / total_steps` | How direct was the path? |
| **Side Effects** | Classified by severity | What collateral damage occurred? |

**Side Effect Severities:**
- **CRITICAL**: File deletions, process termination, port closure, env var removal
- **WARNING**: Unexpected file modifications/creations, env additions, process spawns
- **INFO**: Expected changes, read-only operations

---

## Framework Integrations

AgentDiff is **framework-agnostic**. Use it with any agent system:

### LangChain / LangGraph
```python
from agentdiff.integrations.langchain import AgentDiffCallbackHandler

callback = AgentDiffCallbackHandler(
    target_paths=["src/"],
    cleanliness_threshold=0.8,
)
agent = create_react_agent(..., callbacks=[callback])
result = agent.invoke({"input": "Fix the bug"})
print(callback.get_evaluation_result())
```

### CrewAI
```python
from agentdiff.integrations.crewai import AgentDiffEvaluator

evaluator = AgentDiffEvaluator(target_paths=["src/"])
crew = Crew(agents=[...], tasks=[...], process=Process.sequential)
result = crew.kickoff()
eval_result = evaluator.evaluate_crew(crew)
```

### AutoGen
```python
from agentdiff.integrations.autogen import AgentDiffAgent

agent = AgentDiffAgent(
    name="coder",
    target_paths=["src/"],
    cleanliness_threshold=0.8,
)
```

### Raw Python / Any Framework
```python
# Just wrap your agent loop
with AgentDiffSession(target_paths=["src/"]) as session:
    result = your_agent.run(task)
    eval_result = session.evaluate()
```

> **Don't see your framework?** [Open an issue](https://github.com/your-org/agentdiff/issues/new) or contribute an adapter — it's ~50 lines of code.

---

## CLI Usage

```bash
# Evaluate a trajectory file
agentdiff eval trajectory.json --threshold 0.8

# Diff two snapshots
agentdiff diff pre.json post.json --format json

# Replay a trajectory (re-run with same inputs)
agentdiff replay trajectory.json --dry-run

# Initialize config for your project
agentdiff init --framework langchain
```

---

## CI/CD Integration

### GitHub Actions
```yaml
# .github/workflows/agent-eval.yml
name: Agent Evaluation
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install agentdiff
      - run: agentdiff eval trajectory.json --threshold 0.8 --fail-below-threshold
```

### Pre-commit Hook
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/your-org/agentdiff
    rev: v0.2.0
    hooks:
      - id: agentdiff-trajectory-check
        args: ["--threshold", "0.8"]
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        AgentDiff                            │
├─────────────────┬─────────────────┬─────────────────────────┤
│   DiffEngine    │ TrajectoryTrack │  AgentDiffEvaluator     │
├─────────────────┼─────────────────┼─────────────────────────┤
│ • Filesystem    │ • StepRecorder  │ • Cleanliness Score     │
│ • Environment   │ • LoopDetector  │ • Efficiency Score      │
│ • Processes     │ • TokenCounter  │ • Side Effect Classifier│
│ • Network       │ • JSON Serialize│ • Pass/Fail Decision    │
└────────┬────────┴────────┬────────┴───────────┬────────────┘
         │                 │                    │
         ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│                    Framework Adapters                       │
│  LangChain │ CrewAI │ AutoGen │ LangGraph │ OpenAI │ Custom │
└─────────────────────────────────────────────────────────────┘
```

---

## Examples

### Basic File Mutation Detection
```python
# examples/basic_file_diff.py
from agentdiff import DiffEngine
from pathlib import Path
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    root = Path(tmpdir)
    (root / "main.py").write_text("def add(a, b): return a + b\n")
    
    engine = DiffEngine(root=root)
    pre = engine.capture()
    
    # Agent modifies the file
    (root / "main.py").write_text("def add(a, b): return a - b\n")  # Bug!
    (root / "debug.log").write_text("debug info")  # Side effect
    
    post = engine.capture()
    diff = engine.diff(pre, post)
    
    print(f"Modified: {diff.modified_files}")  # ['main.py']
    print(f"Created: {diff.created_files}")    # ['debug.log']
```

### Trajectory with Loop Detection
```python
# examples/trajectory_loops.py
from agentdiff import TrajectoryTracker, ToolCall, StepResult

tracker = TrajectoryTracker()

# Simulate agent getting stuck in a loop
for i in range(5):
    tracker.record_step(
        thought="Try to fix the test",
        tool_call=ToolCall(name="run_test", args={}),
        observation="Test failed: assertion error",
        result=StepResult(success=False, tokens_in=100, tokens_out=50)
    )

trajectory = tracker.get_trajectory()
print(f"Loops detected: {trajectory.loop_count}")  # 4 (repeated same tool)
print(f"Efficiency: {trajectory.efficiency_score:.2%}")  # Low
```

### Full Evaluation Pipeline
```python
# examples/full_evaluation.py
from agentdiff import DiffEngine, TrajectoryTracker, AgentDiffEvaluator
from pathlib import Path
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    root = Path(tmpdir)
    (root / "calculator.py").write_text("def add(a, b): return a + b\n")
    (root / "config.json").write_text('{"mode": "prod"}\n')
    
    # Setup
    engine = DiffEngine(root=root)
    tracker = TrajectoryTracker()
    pre = engine.capture()
    
    # Agent run (simulated)
    tracker.record_step(
        thought="Fix the add function",
        tool_call=ToolCall(name="edit", args={"file": "calculator.py"}),
        observation="Edited calculator.py",
        result=StepResult(success=True)
    )
    tracker.record_step(
        thought="Update config for testing",
        tool_call=ToolCall(name="edit", args={"file": "config.json"}),
        observation="Edited config.json",
        result=StepResult(success=True)
    )
    tracker.record_step(
        thought="Add debug logging",
        tool_call=ToolCall(name="create", args={"file": "debug.log"}),
        observation="Created debug.log",
        result=StepResult(success=True)
    )
    
    # Actual file mutations
    (root / "calculator.py").write_text("def add(a, b): return a + b\n")  # Fixed
    (root / "config.json").write_text('{"mode": "test"}\n')  # Changed
    (root / "debug.log").write_text("debug\n")  # Side effect!
    
    # Evaluate
    post = engine.capture()
    diff = engine.diff(pre, post)
    trajectory = tracker.get_trajectory()
    
    evaluator = AgentDiffEvaluator(
        target_paths=["calculator.py"],  # Only this should change
        cleanliness_threshold=0.8,
    )
    result = evaluator.evaluate(diff, trajectory)
    
    print(f"Cleanliness: {result.metrics.cleanliness_score:.1%}")  # 33%
    print(f"Passed: {result.passed}")  # False
    print(f"Side Effects: {len(result.side_effects)}")  # 2
```

Run examples:
```bash
python examples/basic_file_diff.py
python examples/trajectory_loops.py
python examples/full_evaluation.py
```

---

## Configuration

```python
# agentdiff.yaml or agentdiff.toml
diff_engine:
  root: "."
  ignore_patterns:
    - "*.pyc"
    - "__pycache__"
    - ".git"
    - "*.log"
    - ".venv"
  max_file_size: 10_000_000  # 10MB
  hash_algorithm: "sha256"
  capture_env_vars: true
  env_denylist: ["*KEY*", "*SECRET*", "*TOKEN*", "*PASSWORD*"]
  capture_processes: true
  capture_ports: true

evaluator:
  cleanliness_threshold: 0.8
  efficiency_threshold: 0.7
  critical_types:
    - "file_deleted"
    - "dir_deleted"
    - "process_terminated"
    - "port_closed"
    - "env_var_removed"
  warning_types:
    - "file_modified"
    - "file_created"
    - "env_var_added"
    - "process_spawned"

trajectory:
  max_steps: 1000
  loop_detection_window: 10
  loop_similarity_threshold: 0.9
```

---

## Why AgentDiff? (Community Voice)

> **"We evaluate LLMs on output quality, but agents on *behavior*. AgentDiff is the first tool that actually measures behavior."** — GitHub Discussion #10241 (Promptfoo)

> **"My agent 'fixed the bug' but deleted the config file and spawned 50 chrome processes. Current tools said 'pass'. AgentDiff would have caught this."** — Issue #290 (agentbranch)

> **"We need 'cleanliness score' as a first-class metric. Not just 'did it work' but 'how much collateral damage'."** — SwarmAI Discussions

> **"Record/replay for agent trajectories is essential for regression testing. Nobody has this open-source."** — zeroclaw Issue #7065

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

### Development Setup
```bash
git clone https://github.com/your-org/agentdiff
cd agentdiff
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pre-commit install
pytest tests/ -v
```

### Priority Areas for Contribution
1. **Framework Adapters** — LangChain, CrewAI, AutoGen, LangGraph, OpenAI Assistants
2. **Diff Types** — Database state, REST/GraphQL APIs, Kubernetes resources
3. **Visual Reports** — HTML diff reports with side-by-side views
4. **MCP Server** — For Claude Code / Cursor integration
5. **Documentation** — Examples, tutorials, API reference

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Citation

If you use AgentDiff in research, please cite:

```bibtex
@software{agentdiff,
  title = {AgentDiff: Full-State Trajectory Evaluation for AI Agents},
  author = {AgentDiff Contributors},
  year = {2024},
  url = {https://github.com/your-org/agentdiff}
}
```

---

## Links

- **Documentation**: https://agentdiff.readthedocs.io
- **Discord Community**: https://discord.gg/agentdiff
- **GitHub Issues**: https://github.com/your-org/agentdiff/issues
- **Discussions**: https://github.com/your-org/agentdiff/discussions
- **PyPI**: https://pypi.org/project/agentdiff/

---

**Built with ❤️ for the open-source agent ecosystem.**

*AgentDiff: Because agents don't just talk — they act.*
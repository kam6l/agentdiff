# Python API

AgentDiff exposes two related surfaces:

- the runtime transaction API for policy, evidence, scoring, inspection, and recovery; and
- the original snapshot/trajectory evaluator API.

## Runtime transaction

```python
from agentdiff.policy import load_policy_file
from agentdiff.transaction import AgentRunTransaction

policy = load_policy_file("agentdiff.yaml")
result = AgentRunTransaction(
    root=".",
    policy=policy,
    task="Fix the parser",
).run(["python3", "agent.py"], timeout_seconds=300)

print(result.run_id)
print(result.status)
print(result.safety_outcome.value)
for change in result.changes:
    print(change.path, change.decision.action.value, change.decision.rule)
```

The runner invokes an argument vector with `shell=False`. Its local backend is not a sandbox.

To delegate execution to a preinstalled Anthropic Sandbox Runtime:

```python
from agentdiff.runtime import SandboxRuntime

runtime = SandboxRuntime(
    root=".",
    settings="/absolute/path/to/srt-settings.json",
)
result = AgentRunTransaction(
    root=".",
    policy=policy,
    runtime=runtime,
).run(["python3", "agent.py"])
```

The external runtime owns enforcement. AgentDiff preserves transaction evidence but does not validate the effectiveness of SRT settings.

::: agentdiff.runtime.SandboxRuntime
    options:
      show_root_heading: true
      members:
        - run
        - cleanup

### Transaction runner

::: agentdiff.transaction.AgentRunTransaction
    options:
      show_root_heading: true
      members:
        - run

::: agentdiff.transaction.TransactionResult
    options:
      show_root_heading: true
      members:
        - to_dict
        - recommended_exit_code

### Inspection and recovery

```python
from agentdiff.transaction import RollbackEngine, RunInspector, RunStore

inspection = RunInspector(".", result.run_id)
print(inspection.inspect())

integrity = RunStore.open(".", result.run_id).verify_integrity()
print(integrity.ok)

report = RollbackEngine.open(".", result.run_id).rollback(safe_only=True)
print(report.to_dict())
```

::: agentdiff.transaction.RunInspector
    options:
      show_root_heading: true
      members:
        - inspect
        - summary
        - cleanup

::: agentdiff.transaction.RunStore
    options:
      show_root_heading: true
      members:
        - open
        - verify_integrity

::: agentdiff.transaction.list_runs

::: agentdiff.transaction.RollbackEngine
    options:
      show_root_heading: true
      members:
        - open
        - rollback

## Policy

```python
from agentdiff.policy import PolicyEngine, load_policy

policy = load_policy(
    {
        "version": 1,
        "filesystem": {
            "allow_write": ["src/**"],
            "deny": [".env"],
            "default": "review",
        },
    }
)
decision = PolicyEngine(policy).decide_path(".env")
print(decision.to_dict())
```

::: agentdiff.policy.PolicyEngine
    options:
      show_root_heading: true
      members:
        - decide_path
        - decide_command
        - evaluate_limits

## Blast-radius scoring

::: agentdiff.scoring.BlastRadiusScorer
    options:
      show_root_heading: true
      members:
        - score

::: agentdiff.scoring.BlastRadiusResult
    options:
      show_root_heading: true
      members:
        - to_dict

## MCP-style dispatch hook

::: agentdiff.integrations.mcp_policy.MCPPolicyHook
    options:
      show_root_heading: true
      members:
        - evaluate
        - authorize

This hook does not implement MCP transport. The caller must invoke it at the dispatch boundary.

## Framework-neutral legacy session

```python
from agentdiff import AgentDiffConfig, AgentDiffSession

config = AgentDiffConfig(
    root=".",
    target_paths=["src/evaluator.py"],
    cleanliness_threshold=0.8,
)

with AgentDiffSession("Fix the evaluator", config) as run:
    your_agent()
    run.record(
        thought="Applied the focused patch",
        tool_name="edit_file",
        tool_args={"path": "src/evaluator.py"},
        observation="File updated",
    )

result = run.evaluate()
print(result.metrics.cleanliness_score)
print(result.passed)
```

Relative targets are resolved against `config.root`. Call `evaluate()` after work finishes; leaving the context does not auto-publish a report.

## Explicit legacy components

::: agentdiff.diff_engine.DiffEngine
    options:
      show_root_heading: true
      members:
        - snapshot
        - diff

::: agentdiff.trajectory.TrajectoryTracker
    options:
      show_root_heading: true
      members:
        - start_step
        - record_tool_call
        - record_llm_usage
        - track_tool
        - end_step
        - finish
        - save

::: agentdiff.evaluator.AgentDiffEvaluator
    options:
      show_root_heading: true
      members:
        - set_target_mutations
        - evaluate
        - evaluate_from_snapshots

::: agentdiff.evaluator.EvaluationResult
    options:
      show_root_heading: true
      members:
        - to_dict
        - to_json
        - print_summary

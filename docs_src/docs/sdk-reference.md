---
title: Python API
description: Implemented Python interfaces for AgentDiff 0.1.0.
---

# Python API

This page lists the implemented `0.1.0` interfaces. The transaction API is **Beta**; the MCP hook and evaluator integrations are **Experimental**.

## Run a transaction

```python
import sys
from pathlib import Path

from agentdiff import AgentRunTransaction, load_policy_file

root = Path("/workspace/project")
policy = load_policy_file(root / "agentdiff.yaml")
result = AgentRunTransaction(
    root=root,
    policy=policy,
    task="Fix authentication",
).run([sys.executable, "agent_task.py"], timeout_seconds=300)

print(result.run_id, result.status)
print(result.blast_radius.score, result.blast_radius.level.value)
for change in result.changes:
    print(change.path, change.change_type, change.decision.action.value, change.reversible)
```

`TransactionResult.to_dict()` returns the schema-versioned JSON shape used by `agentdiff run --format json`. `recommended_exit_code("never" | "review" | "deny")` applies the CLI exit policy.

## Inspect and recover

```python
from agentdiff import RollbackEngine, RunInspector

summary = RunInspector(root, result.run_id).summary()
report = RollbackEngine.open(root, result.run_id).rollback(safe_only=True)

print(summary.safety_outcome)
print(report.ok, report.actions, report.conflicts)
```

Recovery requires exactly one of `safe_only=True` or `all_changes=True`. An optional `paths=[...]` list narrows the selected relative paths.

## Load and explain policy

```python
from agentdiff import PolicyEngine, load_policy

policy = load_policy(
    {
        "version": 1,
        "filesystem": {
            "allow_write": ["src/**", "tests/**"],
            "deny": [".env", ".env.*", ".git/**"],
            "default": "review",
        },
        "process": {"allow": ["python*"], "default": "review"},
    }
)
decision = PolicyEngine(policy).decide_path(".env")
print(decision.action.value, decision.rule, decision.reason)
```

Use `load_policy_file(path)` for YAML or JSON-compatible YAML files. Unknown keys and unsupported values raise `PolicyValidationError`.

## Score evidence

```python
from agentdiff import BlastRadiusScorer, MutationRisk, PolicyAction

score = BlastRadiusScorer().score(
    [MutationRisk(".env", "created", PolicyAction.DENY)]
)
print(score.score, score.level.value, score.components)
```

## Pre-dispatch tool policy

`MCPPolicyHook` is transport-neutral. It does not run an MCP client, server, or proxy.

```python
from agentdiff import MCPPolicyHook

hook = MCPPolicyHook(policy)
decision = hook.authorize("filesystem.write_file", {"path": "src/app.py"})
```

`authorize()` raises `ToolCallBlockedError` for `deny` and, by default, `review`. Pass `allow_review=True` only when the caller has an explicit review workflow.

## Public modules

| Module | Implemented surface |
|---|---|
| `agentdiff.transaction` | Transactions, assessments, capsules, inspection, integrity, rollback |
| `agentdiff.policy` | Version-1 schema, strict loaders, deterministic decisions |
| `agentdiff.scoring` | Weights, mutation risks, components, risk levels |
| `agentdiff.state` | Secure manifests and deterministic filesystem diffs |
| `agentdiff.runtime` | Local observer and optional external `SandboxRuntime` adapter |
| `agentdiff.cortex` | Experimental evidence memory, skill-card generation, provider routing, and remediation advice |
| `agentdiff.integrations` | MCP hook plus legacy evaluator session helpers |

There is no `AgentDiffRuntime`, async runtime, HTTP server, `serve` command, or `__version_info__` attribute in `0.1.0`.

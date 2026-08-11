# Python API

Programmatic access to AgentDiff's runtime, policy, and scoring engines.

## Installation

```bash
pip install agentdiff
```

---

## Core Classes

### `AgentDiffRuntime`

Main entry point for running transactions.

```python
from agentdiff import AgentDiffRuntime
from agentdiff.policy import Policy

# Load policy
policy = Policy.from_file("agentdiff-policy.yaml")

# Create runtime
runtime = AgentDiffRuntime(policy=policy, root="/workspace")

# Run a transaction
result = runtime.run(
    argv=["python3", "agent.py"],
    task_description="Fix the parser",
    timeout=300
)

# Access results
print(f"Run ID: {result.run_id}")
print(f"Status: {result.status}")  # PASS | REVIEW | DENY
print(f"Blast radius: {result.blast_radius.score}/100")
print(f"Level: {result.blast_radius.level}")  # LOW | MODERATE | HIGH | CRITICAL

# Inspect mutations
for mutation in result.mutations:
    print(f"  {mutation.change_type} {mutation.path} → {mutation.decision}")

# Rollback
runtime.rollback(result.run_id, safe_only=True)
```

### `Policy`

Load, validate, and evaluate policies.

```python
from agentdiff.policy import Policy, PolicyAction

# From file
policy = Policy.from_file("agentdiff-policy.yaml")

# From dict
policy = Policy({
    "schema_version": 1,
    "filesystem": {
        "allow_write": ["src/**"],
        "deny": [".env*"],
        "default": "review"
    }
})

# Evaluate a single path
decision = policy.decide_path("src/main.py")
print(decision.action)        # PolicyAction.ALLOW
print(decision.rule)          # "filesystem.allow_write[0]"
print(decision.pattern)       # "src/**"

# Validate
policy.validate()  # Raises PolicyValidationError if invalid
```

### `BlastRadiusScorer`

Compute blast radius from mutations.

```python
from agentdiff.scoring import BlastRadiusScorer, BlastRadiusWeights, MutationRisk
from agentdiff.policy import PolicyAction

# Custom weights
weights = BlastRadiusWeights(
    denied_mutation=50,
    sensitive_path=40,
)

scorer = BlastRadiusScorer(weights=weights)

# Create mutation risks from policy decisions
mutations = [
    MutationRisk(
        path="src/main.py",
        change_type="modified",
        decision=PolicyAction.ALLOW,
    ),
    MutationRisk(
        path=".env",
        change_type="created",
        decision=PolicyAction.DENY,
    ),
]

# Score
result = scorer.score(
    mutations,
    orphan_processes=1,
    opened_ports=0,
    budget_violations=0
)

print(f"Score: {result.score}/100")
print(f"Level: {result.level}")  # RiskLevel.LOW | MODERATE | HIGH | CRITICAL
print(f"Components: {result.components}")
```

### `ManifestScanner`

Capture filesystem snapshots.

```python
from agentdiff.state import ManifestScanner, FileRecord

scanner = ManifestScanner(
    root="/workspace",
    ignores=[".git", "node_modules", "__pycache__"],
    follow_symlinks=False,
)

# Capture snapshot
snapshot = scanner.scan()

# Access files
for record in snapshot.files:
    print(f"{record.path} {record.sha256[:8]} {record.size} bytes")

# Save/load
snapshot.to_file("manifest.json")
loaded = ManifestScanner.from_file("manifest.json")
```

### `DiffEngine`

Compute deterministic diffs between snapshots.

```python
from agentdiff.state import DiffEngine, DiffEntry, DiffType

diff_engine = DiffEngine()

diff = diff_engine.diff(pre_snapshot, post_snapshot)

for entry in diff.entries:
    print(f"{entry.type.value} {entry.path}")

# Summary
print(f"Created: {len(diff.created)}")
print(f"Modified: {len(diff.modified)}")
print(f"Deleted: {len(diff.deleted)}")
```

---

## Result Objects

### `TransactionResult`

```python
@dataclass
class TransactionResult:
    run_id: str
    task_description: str
    argv: list[str]
    status: TransactionStatus  # PASS | REVIEW | DENY
    blast_radius: BlastRadiusResult
    mutations: list[MutationRecord]
    processes: list[OwnedProcess]
    ports: PortDiff
    start_time: float
    end_time: float
    capsule_path: Path
```

### `MutationRecord`

```python
@dataclass
class MutationRecord:
    path: str
    change_type: str  # created | modified | deleted | replaced | permissions
    decision: PolicyAction
    rule: str
    pattern: str
    pre_hash: str | None
    post_hash: str | None
    pre_mode: int | None
    post_mode: int | None
```

### `BlastRadiusResult`

```python
@dataclass
class BlastRadiusResult:
    score: int              # 0-100 (capped)
    raw_score: int          # uncapped
    level: RiskLevel        # LOW | MODERATE | HIGH | CRITICAL
    counts: dict[str, int]  # files_changed, sensitive_files, etc.
    components: list[RiskComponent]  # per-evidence breakdown
```

### `RiskComponent`

```python
@dataclass
class RiskComponent:
    name: str               # e.g., "denied_mutation"
    count: int
    weight: int
    points: int             # count × weight
    detail: str             # human-readable
```

---

## Recovery API

```python
from agentdiff.recovery import RecoveryEngine, RecoveryOptions

recovery = RecoveryEngine(capsule_path=Path(".agentdiff/runs/a1b2c3d4"))

# Safe rollback
result = recovery.rollback(RecoveryOptions(
    safe_only=True,
    decisions={"deny", "review"},
    dry_run=False,
))

print(f"Reverted: {result.reverted}")
print(f"Preserved (conflicts): {result.conflicts}")
print(f"Preserved (allowed): {result.allowed}")

# Selective restore
recovery.restore_file("src/main.py")
```

---

## Integrations

### Anthropic Sandbox Runtime

```python
from agentdiff.integrations import SandboxRuntimeAdapter

adapter = SandboxRuntimeAdapter(
    executable="srt",
    settings="sandbox-settings.json",
)

result = adapter.run(
    argv=["python3", "agent.py"],
    task_description="Fix parser in sandbox",
)
```

### MCP Policy Hook

```python
from agentdiff.integrations import MCPolicyHook

hook = MCPolicyHook(policy=policy)

# Called by MCP server on each tool call
decision = hook.evaluate_tool_call(
    tool_name="write_file",
    arguments={"path": ".env", "content": "SECRET=123"},
)

if decision.action == PolicyAction.DENY:
    raise PermissionError(f"Blocked by policy: {decision.reason}")
```

---

## Error Handling

```python
from agentdiff.exceptions import (
    AgentDiffError,
    PolicyValidationError,
    ManifestScanError,
    RecoveryError,
    BlastRadiusThresholdExceeded,
)

try:
    result = runtime.run(argv=["python3", "agent.py"], task="Fix parser")
except BlastRadiusThresholdExceeded as e:
    print(f"Blast radius {e.score} exceeded threshold {e.threshold}")
except RecoveryError as e:
    print(f"Rollback failed: {e.reason}")
```

---

## Async Support

All core operations have async variants:

```python
import asyncio
from agentdiff import AsyncAgentDiffRuntime

async def main():
    runtime = AsyncAgentDiffRuntime(policy=policy)
    result = await runtime.run(
        argv=["python3", "agent.py"],
        task_description="Async fix",
    )
    await runtime.rollback(result.run_id, safe_only=True)

asyncio.run(main())
```

---

## Type Stubs

Full type annotations included. Use with mypy/pyright:

```bash
mypy --strict your_script.py  # Passes
```

---

## Next Steps

- [CLI Reference](cli.md) — Command-line interface
- [Runtime Model](concepts/runtime.md) — Underlying model
- [Mutation Policy](concepts/policy.md) — Policy configuration
- [Integrations](integrations/sandbox-runtime.md) — Sandbox adapter
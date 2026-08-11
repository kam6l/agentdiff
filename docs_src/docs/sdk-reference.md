# SDK Reference

Complete SDK reference for AgentDiff.

## `agentdiff.runtime`

### `AgentDiffRuntime`

```python
class AgentDiffRuntime:
    def __init__(
        self,
        policy: Policy,
        root: str | Path = ".",
        observe_processes: bool = True,
        observe_ports: bool = True,
        backup_enabled: bool = True,
    ) -> None: ...

    def run(
        self,
        argv: list[str],
        task_description: str,
        timeout: float = 300,
        dry_run: bool = False,
    ) -> TransactionResult: ...

    def rollback(
        self,
        run_id: str,
        safe_only: bool = True,
        decisions: set[PolicyAction] | None = None,
        paths: list[str] | None = None,
        dry_run: bool = False,
    ) -> RollbackResult: ...

    def inspect(self, run_id: str) -> RunCapsule: ...

    def list_runs(self, limit: int = 20, since: datetime | None = None) -> list[RunSummary]: ...
```

### `TransactionResult`

```python
@dataclass(frozen=True, slots=True)
class TransactionResult:
    run_id: str
    task_description: str
    argv: list[str]
    status: TransactionStatus
    blast_radius: BlastRadiusResult
    mutations: tuple[MutationRecord, ...]
    processes: tuple[OwnedProcess, ...]
    ports: PortDiff
    start_time: float
    end_time: float
    capsule_path: Path
```

### `TransactionStatus`

```python
class TransactionStatus(str, Enum):
    PASS = "pass"
    REVIEW = "review"
    DENY = "deny"
```

---

## `agentdiff.policy`

### `Policy`

```python
class Policy:
    def __init__(self, data: dict) -> None: ...

    @classmethod
    def from_file(cls, path: str | Path) -> "Policy": ...

    @classmethod
    def from_dict(cls, data: dict) -> "Policy": ...

    def decide_path(self, path: str, *, phase: str = "post_run") -> PolicyDecision: ...

    def decide_tool_call(self, tool: str, arguments: dict) -> PolicyDecision: ...

    def validate(self) -> None: ...

    def to_dict(self) -> dict: ...

    def to_yaml(self) -> str: ...
```

### `PolicyDecision`

```python
@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: PolicyAction
    subject: str
    rule: str
    pattern: str | None
    reason: str
    policy_version: int
    phase: str
```

### `PolicyAction`

```python
class PolicyAction(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"
```

---

## `agentdiff.scoring`

### `BlastRadiusScorer`

```python
class BlastRadiusScorer:
    def __init__(self, weights: BlastRadiusWeights | None = None) -> None: ...

    def score(
        self,
        mutations: Iterable[MutationRisk],
        *,
        orphan_processes: int = 0,
        opened_ports: int = 0,
        budget_violations: int = 0,
    ) -> BlastRadiusResult: ...

    @staticmethod
    def level_for(score: int) -> RiskLevel: ...
```

### `BlastRadiusWeights`

```python
@dataclass(frozen=True, slots=True)
class BlastRadiusWeights:
    review_created: int = 8
    review_modified: int = 4
    review_deleted: int = 12
    denied_mutation: int = 30
    denied_deletion: int = 40
    sensitive_path: int = 35
    dependency_change: int = 8
    mode_change: int = 8
    orphan_process: int = 10
    opened_port: int = 5
    budget_violation: int = 12
    scope_drift: int = 2

    @classmethod
    def from_mapping(cls, overrides: Mapping[str, int]) -> "BlastRadiusWeights": ...
```

### `BlastRadiusResult`

```python
@dataclass(frozen=True, slots=True)
class BlastRadiusResult:
    score: int
    raw_score: int
    level: RiskLevel
    counts: dict[str, int]
    components: tuple[RiskComponent, ...]

    def to_dict(self) -> dict: ...
```

### `RiskComponent`

```python
@dataclass(frozen=True, slots=True)
class RiskComponent:
    name: str
    count: int
    weight: int
    points: int
    detail: str
```

### `MutationRisk`

```python
@dataclass(frozen=True, slots=True)
class MutationRisk:
    path: str
    change_type: str  # created | modified | deleted
    decision: PolicyAction
    mode_changed: bool = False
```

### `RiskLevel`

```python
class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
```

---

## `agentdiff.state`

### `ManifestScanner`

```python
class ManifestScanner:
    def __init__(
        self,
        root: str | Path,
        ignores: Iterable[str] | None = None,
        follow_symlinks: bool = False,
    ) -> None: ...

    def scan(self) -> FilesystemSnapshot: ...
```

### `FilesystemSnapshot`

```python
@dataclass(frozen=True, slots=True)
class FilesystemSnapshot:
    files: tuple[FileRecord, ...]
    timestamp: float
    schema_version: int = 1
```

### `FileRecord`

```python
@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    kind: str  # file | dir | symlink | fifo | socket | device
    sha256: str | None
    size: int
    mode: int
    mtime_ns: int
    device: int | None
    inode: int | None
    link_count: int
    symlink_target: str | None
```

### `DiffEngine`

```python
class DiffEngine:
    def diff(self, pre: FilesystemSnapshot, post: FilesystemSnapshot) -> DiffResult: ...
```

### `DiffResult`

```python
@dataclass(frozen=True, slots=True)
class DiffResult:
    created: tuple[FileRecord, ...]
    modified: tuple[FileRecord, ...]
    deleted: tuple[FileRecord, ...]
    replaced: tuple[FileRecord, ...]
    permissions: tuple[FileRecord, ...]
    summary: dict[str, int]
```

### `PortSnapshot`

```python
@dataclass(frozen=True, slots=True)
class PortSnapshot:
    ports: frozenset[PortRecord]
    timestamp: float
```

### `PortRecord`

```python
@dataclass(frozen=True, slots=True)
class PortRecord:
    proto: str  # tcp | udp
    addr: str
    port: int
    pid: int | None
    process_name: str | None
```

### `PortDiff`

```python
@dataclass(frozen=True, slots=True)
class PortDiff:
    opened: tuple[PortRecord, ...]
    closed: tuple[PortRecord, ...]
```

---

## `agentdiff.recovery`

### `RecoveryEngine`

```python
class RecoveryEngine:
    def __init__(self, capsule_path: Path) -> None: ...

    def rollback(self, options: RecoveryOptions) -> RollbackResult: ...

    def restore_file(self, path: str) -> None: ...

    def list_backups(self) -> list[BackupInfo]: ...
```

### `RecoveryOptions`

```python
@dataclass(frozen=True, slots=True)
class RecoveryOptions:
    safe_only: bool = True
    decisions: frozenset[PolicyAction] = frozenset({PolicyAction.DENY, PolicyAction.REVIEW})
    paths: tuple[str, ...] = ()
    dry_run: bool = False
```

### `RollbackResult`

```python
@dataclass(frozen=True, slots=True)
class RollbackResult:
    reverted: tuple[str, ...]
    conflicts: tuple[str, ...]
    allowed: tuple[str, ...>
    errors: tuple[str, ...]
```

---

## `agentdiff.integrations`

### `AgentDiffCallbackHandler`

```python
class AgentDiffCallbackHandler(BaseCallbackHandler):
    def __init__(
        self,
        policy_path: str,
        task_description: str,
        root: str | Path = ".",
        observe_processes: bool = True,
        observe_ports: bool = True,
        backup_enabled: bool = True,
    ) -> None: ...

    # Properties available after run
    run_id: str
    status: TransactionStatus
    blast_radius: BlastRadiusResult
    mutations: tuple[MutationRecord, ...]

    def rollback(self, safe_only: bool = True) -> RollbackResult: ...
    def restore_file(self, path: str) -> None: ...
    def get_capsule(self) -> RunCapsule: ...
```

### `SandboxRuntimeAdapter`

```python
class SandboxRuntimeAdapter:
    def __init__(
        self,
        executable: str = "srt",
        settings: str | Path | None = None,
        observe_ports: bool = True,
        poll_interval_seconds: float = 0.05,
    ) -> None: ...

    def run(
        self,
        argv: Sequence[str],
        task_description: str,
        timeout_seconds: float | None = None,
    ) -> RuntimeResult: ...
```

### `MCPolicyHook`

```python
class MCPolicyHook:
    @classmethod
    def from_file(cls, path: str | Path) -> "MCPolicyHook": ...

    def evaluate_tool_call(self, tool: str, arguments: dict) -> PolicyDecision: ...

    def evaluate_batch(self, calls: list[dict]) -> list[PolicyDecision]: ...
```

---

## `agentdiff.exceptions`

```python
class AgentDiffError(Exception): ...

class PolicyValidationError(AgentDiffError): ...

class ManifestScanError(AgentDiffError): ...

class RecoveryError(AgentDiffError): ...

class BlastRadiusThresholdExceeded(AgentDiffError):
    def __init__(self, score: int, threshold: int): ...

class RunNotFoundError(AgentDiffError): ...

class BackupError(AgentDiffError): ...
```

---

## Version Info

```python
import agentdiff

agentdiff.__version__        # "0.1.0"
agentdiff.__version_info__   # (0, 1, 0)
```
"""AgentDiff runtime evidence, deterministic policy, and selective recovery.

The transaction API is the primary product surface. The original trajectory
evaluation API remains available for compatibility.
"""

__version__ = "0.1.0"

from .diff_engine import (
    DiffEngine,
    DiffEntry,
    DiffResult,
    DiffType,
    EnvironmentSnapshot,
    FilesystemSnapshot,
)
from .evaluator import (
    AgentDiffEvaluator,
    CleanlinessMetrics,
    EvaluationResult,
    SideEffect,
    SideEffectSeverity,
    evaluate_agent_run,
)
from .integrations import (
    AgentDiffConfig,
    AgentDiffSession,
    BaseAgentDiffAdapter,
    MCPPolicyHook,
    ToolCallBlockedError,
    ToolCallDecision,
)
from .policy import (
    Policy,
    PolicyAction,
    PolicyDecision,
    PolicyEngine,
    load_policy,
    load_policy_file,
)
from .scoring import (
    BlastRadiusResult,
    BlastRadiusScorer,
    BlastRadiusWeights,
    MutationRisk,
    RiskLevel,
)
from .trajectory import (
    AgentFramework,
    StepResult,
    ToolCall,
    TrajectoryRecord,
    TrajectoryStep,
    TrajectoryTracker,
)
from .transaction import AgentRunTransaction, RollbackEngine, RunInspector, TransactionResult

__all__ = [
    "AgentDiffConfig",
    "AgentDiffEvaluator",
    "AgentDiffSession",
    "AgentFramework",
    "AgentRunTransaction",
    "BaseAgentDiffAdapter",
    "BlastRadiusResult",
    "BlastRadiusScorer",
    "BlastRadiusWeights",
    "CleanlinessMetrics",
    "DiffEngine",
    "DiffEntry",
    "DiffResult",
    "DiffType",
    "EnvironmentSnapshot",
    "EvaluationResult",
    "FilesystemSnapshot",
    "MCPPolicyHook",
    "MutationRisk",
    "Policy",
    "PolicyAction",
    "PolicyDecision",
    "PolicyEngine",
    "RiskLevel",
    "RollbackEngine",
    "RunInspector",
    "SideEffect",
    "SideEffectSeverity",
    "StepResult",
    "ToolCall",
    "ToolCallBlockedError",
    "ToolCallDecision",
    "TrajectoryRecord",
    "TrajectoryStep",
    "TrajectoryTracker",
    "TransactionResult",
    "evaluate_agent_run",
    "load_policy",
    "load_policy_file",
]

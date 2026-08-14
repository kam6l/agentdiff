"""AgentDiff runtime evidence, deterministic policy, and selective recovery.

The transaction API is the primary product surface. The original trajectory
evaluation API remains available for compatibility.
"""

__version__ = "0.1.0"

from .cortex import (
    AgentMemoryStore,
    CompressedContextCard,
    ContextCompressor,
    ContextPacker,
    CortexResult,
    CortexRouter,
    MemoryHit,
    RepositoryMemoryProvider,
    SelfHealer,
    SkillContract,
    SkillSynthesizer,
)
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
from .providers import (
    AIProvider,
    AnthropicMessagesProvider,
    OllamaChatProvider,
    OllamaEmbeddingProvider,
    OpenAIResponsesProvider,
    ProviderError,
    ProviderResponse,
    create_provider,
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
    "AIProvider",
    "AgentDiffConfig",
    "AgentDiffEvaluator",
    "AgentDiffSession",
    "AgentFramework",
    "AgentMemoryStore",
    "AgentRunTransaction",
    "AnthropicMessagesProvider",
    "BaseAgentDiffAdapter",
    "BlastRadiusResult",
    "BlastRadiusScorer",
    "BlastRadiusWeights",
    "CleanlinessMetrics",
    "CompressedContextCard",
    "ContextCompressor",
    "ContextPacker",
    "CortexResult",
    "CortexRouter",
    "DiffEngine",
    "DiffEntry",
    "DiffResult",
    "DiffType",
    "EnvironmentSnapshot",
    "EvaluationResult",
    "FilesystemSnapshot",
    "MCPPolicyHook",
    "MemoryHit",
    "MutationRisk",
    "OllamaChatProvider",
    "OllamaEmbeddingProvider",
    "OpenAIResponsesProvider",
    "Policy",
    "PolicyAction",
    "PolicyDecision",
    "PolicyEngine",
    "ProviderError",
    "ProviderResponse",
    "RepositoryMemoryProvider",
    "RiskLevel",
    "RollbackEngine",
    "RunInspector",
    "SelfHealer",
    "SideEffect",
    "SideEffectSeverity",
    "SkillContract",
    "SkillSynthesizer",
    "StepResult",
    "ToolCall",
    "ToolCallBlockedError",
    "ToolCallDecision",
    "TrajectoryRecord",
    "TrajectoryStep",
    "TrajectoryTracker",
    "TransactionResult",
    "create_provider",
    "evaluate_agent_run",
    "load_policy",
    "load_policy_file",
]

"""AgentDiff runtime evidence, deterministic policy, and selective recovery.

The transaction API and trust pipeline are the primary product surfaces.
"""

__version__ = "0.2.1"

from .analyzers import FutureBlastEngine, FutureBlastResult
from .cortex import (
    AgentMemoryStore,
    CompressedContextCard,
    ContextCompressor,
    ContextPacker,
    CortexResult,
    CortexRouter,
    MemoryHit,
    RemediationAdvisor,
    RepositoryMemoryProvider,
    SkillCardGenerator,
    SkillContract,
)
from .evidence import CapsuleReader, PatchBundle, PatchEntry, PatchManifest
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
    ProofPolicy,
    load_policy,
    load_policy_file,
)
from .promotion import (
    PromotionEngine,
    PromotionPlan,
    PromotionRecovery,
    PromotionReport,
    WorkspaceLease,
)
from .proof import ProofEngine, ProofPhaseResult, ProofResult, ProofVerdict
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
from .runtime import (
    DockerRuntime,
    LocalRuntime,
    RuntimeBackend,
    RuntimeCapabilities,
    RuntimeCapability,
    RuntimeControlLevel,
    RuntimeResult,
    WorkspaceMaterializer,
)
from .safety import ControlLevel, HybridSafetyWatcher, SafetyController, SafetyReport
from .scoring import (
    BlastRadiusResult,
    BlastRadiusScorer,
    BlastRadiusWeights,
    MutationRisk,
    RiskLevel,
)
from .transaction import (
    AgentRunTransaction,
    RollbackEngine,
    RunInspector,
    RunStore,
    TransactionResult,
)

__all__ = [
    "AIProvider",
    "AgentDiffConfig",
    "AgentDiffSession",
    "AgentMemoryStore",
    "AgentRunTransaction",
    "AnthropicMessagesProvider",
    "BaseAgentDiffAdapter",
    "BlastRadiusResult",
    "BlastRadiusScorer",
    "BlastRadiusWeights",
    "CapsuleReader",
    "CompressedContextCard",
    "ContextCompressor",
    "ContextPacker",
    "ControlLevel",
    "CortexResult",
    "CortexRouter",
    "DockerRuntime",
    "FutureBlastEngine",
    "FutureBlastResult",
    "HybridSafetyWatcher",
    "LocalRuntime",
    "MCPPolicyHook",
    "MemoryHit",
    "MutationRisk",
    "OllamaChatProvider",
    "OllamaEmbeddingProvider",
    "OpenAIResponsesProvider",
    "PatchBundle",
    "PatchEntry",
    "PatchManifest",
    "Policy",
    "PolicyAction",
    "PolicyDecision",
    "PolicyEngine",
    "PromotionEngine",
    "PromotionPlan",
    "PromotionRecovery",
    "PromotionReport",
    "ProofEngine",
    "ProofPhaseResult",
    "ProofPolicy",
    "ProofResult",
    "ProofVerdict",
    "ProviderError",
    "ProviderResponse",
    "RemediationAdvisor",
    "RepositoryMemoryProvider",
    "RiskLevel",
    "RollbackEngine",
    "RunInspector",
    "RunStore",
    "RuntimeBackend",
    "RuntimeCapabilities",
    "RuntimeCapability",
    "RuntimeControlLevel",
    "RuntimeResult",
    "SafetyController",
    "SafetyReport",
    "SkillCardGenerator",
    "SkillContract",
    "ToolCallBlockedError",
    "ToolCallDecision",
    "TransactionResult",
    "WorkspaceLease",
    "WorkspaceMaterializer",
    "create_provider",
    "load_policy",
    "load_policy_file",
]

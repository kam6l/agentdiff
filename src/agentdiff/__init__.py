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
    RemediationAdvisor,
    RepositoryMemoryProvider,
    SkillCardGenerator,
    SkillContract,
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
from .transaction import AgentRunTransaction, RollbackEngine, RunInspector, TransactionResult

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
    "CompressedContextCard",
    "ContextCompressor",
    "ContextPacker",
    "CortexResult",
    "CortexRouter",
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
    "RemediationAdvisor",
    "RepositoryMemoryProvider",
    "RiskLevel",
    "RollbackEngine",
    "RunInspector",
    "SkillCardGenerator",
    "SkillContract",
    "ToolCallBlockedError",
    "ToolCallDecision",
    "TransactionResult",
    "create_provider",
    "load_policy",
    "load_policy_file",
]

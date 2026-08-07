"""
agentdiff - Full-State Trajectory Evaluation for AI Agents

A framework for evaluating AI agent trajectories by tracking
environment state changes, tool call sequences, and side effects.
"""

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
)
from .trajectory import (
    AgentFramework,
    StepResult,
    ToolCall,
    TrajectoryRecord,
    TrajectoryStep,
    TrajectoryTracker,
)

__version__ = "0.1.0"
__all__ = [
    # diff_engine
    "FilesystemSnapshot",
    "EnvironmentSnapshot",
    "DiffEngine",
    "DiffResult",
    "DiffEntry",
    "DiffType",
    # trajectory
    "TrajectoryStep",
    "TrajectoryRecord",
    "TrajectoryTracker",
    "ToolCall",
    "StepResult",
    "AgentFramework",
    # evaluator
    "EvaluationResult",
    "CleanlinessMetrics",
    "SideEffect",
    "SideEffectSeverity",
    "AgentDiffEvaluator",
    "evaluate_agent_run",
    # integrations
    "AgentDiffConfig",
    "AgentDiffSession",
    "BaseAgentDiffAdapter",
]
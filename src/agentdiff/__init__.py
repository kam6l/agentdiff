"""
agentdiff - Full-State Trajectory Evaluation for AI Agents

A framework for evaluating AI agent trajectories by tracking
environment state changes, tool call sequences, and side effects.
"""

from .diff_engine import (
    FilesystemSnapshot,
    EnvironmentSnapshot,
    DiffEngine,
    DiffResult,
    DiffEntry,
    DiffType,
)
from .trajectory import (
    TrajectoryStep,
    TrajectoryRecord,
    TrajectoryTracker,
    ToolCall,
    StepResult,
    AgentFramework,
)
from .evaluator import (
    EvaluationResult,
    CleanlinessMetrics,
    SideEffect,
    SideEffectSeverity,
    AgentDiffEvaluator,
    evaluate_agent_run,
)
from .integrations import (
    AgentDiffConfig,
    AgentDiffSession,
    BaseAgentDiffAdapter,
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
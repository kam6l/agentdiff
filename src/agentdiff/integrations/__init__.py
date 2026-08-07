"""
Framework Adapters for AgentDiff

Base classes and implementations for integrating AgentDiff with popular agent frameworks.
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Dict, List

from agentdiff import DiffEngine, TrajectoryTracker, AgentDiffEvaluator
from agentdiff.diff_engine import EnvironmentSnapshot
from agentdiff.trajectory import ToolCall, StepResult
from agentdiff.evaluator import EvaluationResult


@dataclass
class AgentDiffConfig:
    """Configuration for AgentDiff integration."""
    target_paths: List[str] = field(default_factory=list)
    cleanliness_threshold: float = 0.8
    efficiency_threshold: float = 0.7
    root: str = "."
    ignore_patterns: List[str] = field(default_factory=lambda: [
        "*.pyc", "__pycache__", ".git", "*.log", ".venv", "node_modules"
    ])
    capture_env_vars: bool = True
    capture_processes: bool = True
    capture_ports: bool = True


class BaseAgentDiffAdapter(ABC):
    """Base class for framework-specific adapters."""
    
    def __init__(self, config: Optional[AgentDiffConfig] = None):
        self.config = config or AgentDiffConfig()
        self.engine = DiffEngine(
            root=Path(self.config.root),
            ignore_patterns=self.config.ignore_patterns,
            capture_env_vars=self.config.capture_env_vars,
            capture_processes=self.config.capture_processes,
            capture_ports=self.config.capture_ports,
        )
        self.tracker = TrajectoryTracker()
        self.pre_snapshot: Optional[EnvironmentSnapshot] = None
        self.evaluator = AgentDiffEvaluator(
            target_paths=self.config.target_paths,
            cleanliness_threshold=self.config.cleanliness_threshold,
        )
    
    def start(self) -> None:
        """Capture pre-execution snapshot."""
        self.pre_snapshot = self.engine.capture()
    
    def record_step(
        self,
        thought: str,
        tool_call: Optional[Dict[str, Any]] = None,
        observation: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a trajectory step."""
        tc = ToolCall(
            name=tool_call.get("name", "") if tool_call else "",
            args=tool_call.get("args", {}) if tool_call else {},
            tool_id=tool_call.get("id") if tool_call else None,
        ) if tool_call else None
        
        sr = StepResult(
            success=result.get("success", True) if result else True,
            error=result.get("error") if result else None,
            tokens_in=result.get("tokens_in", 0) if result else 0,
            tokens_out=result.get("tokens_out", 0) if result else 0,
        ) if result else StepResult(success=True)
        
        self.tracker.record_step(
            thought=thought,
            tool_call=tc,
            observation=observation,
            result=sr,
        )
    
    def evaluate(self) -> EvaluationResult:
        """Evaluate the agent run."""
        if self.pre_snapshot is None:
            raise RuntimeError("Must call start() before evaluate()")
        
        post_snapshot = self.engine.capture()
        diff = self.engine.diff(self.pre_snapshot, post_snapshot)
        trajectory = self.tracker.get_trajectory()
        
        return self.evaluator.evaluate(diff, trajectory)
    
    @abstractmethod
    def wrap_agent(self, agent: Any) -> Any:
        """Wrap an agent with AgentDiff tracking."""
        pass


class AgentDiffSession:
    """Context manager for easy AgentDiff usage with any framework."""
    
    def __init__(self, config: Optional[AgentDiffConfig] = None):
        self.config = config or AgentDiffConfig()
        self.engine = DiffEngine(
            root=Path(self.config.root),
            ignore_patterns=self.config.ignore_patterns,
            capture_env_vars=self.config.capture_env_vars,
            capture_processes=self.config.capture_processes,
            capture_ports=self.config.capture_ports,
        )
        self.tracker = TrajectoryTracker()
        self.pre_snapshot: Optional[EnvironmentSnapshot] = None
        self.evaluator = AgentDiffEvaluator(
            target_paths=self.config.target_paths,
            cleanliness_threshold=self.config.cleanliness_threshold,
        )
    
    def __enter__(self) -> "AgentDiffSession":
        self.pre_snapshot = self.engine.capture()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
    
    def record(
        self,
        thought: str,
        tool_name: str = "",
        tool_args: Optional[Dict[str, Any]] = None,
        observation: str = "",
        success: bool = True,
        error: Optional[str] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """Record a step in the trajectory."""
        self.tracker.record_step(
            thought=thought,
            tool_call=ToolCall(name=tool_name, args=tool_args or {}) if tool_name else None,
            observation=observation,
            result=StepResult(
                success=success,
                error=error,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            ),
        )
    
    def evaluate(self) -> EvaluationResult:
        """Evaluate the complete run."""
        if self.pre_snapshot is None:
            raise RuntimeError("Session not started")
        
        post_snapshot = self.engine.capture()
        diff = self.engine.diff(self.pre_snapshot, post_snapshot)
        trajectory = self.tracker.get_trajectory()
        
        return self.evaluator.evaluate(diff, trajectory)


# Framework-specific adapters (to be implemented as needed)

class LangChainAdapter(BaseAgentDiffAdapter):
    """Adapter for LangChain/LangGraph agents."""
    
    def wrap_agent(self, agent: Any) -> Any:
        """Wrap a LangChain agent with callback handler."""
        from agentdiff.integrations.langchain_callback import AgentDiffCallbackHandler
        
        callback = AgentDiffCallbackHandler(
            target_paths=self.config.target_paths,
            cleanliness_threshold=self.config.cleanliness_threshold,
        )
        # This would be implemented in langchain_callback.py
        return agent


class CrewAIAdapter(BaseAgentDiffAdapter):
    """Adapter for CrewAI agents."""
    
    def wrap_agent(self, agent: Any) -> Any:
        """Wrap a CrewAI agent."""
        # Implementation in crewai_callback.py
        return agent


class AutoGenAdapter(BaseAgentDiffAdapter):
    """Adapter for AutoGen agents."""
    
    def wrap_agent(self, agent: Any) -> Any:
        """Wrap an AutoGen agent."""
        # Implementation in autogen_callback.py
        return agent
"""Framework-agnostic helpers for wrapping agent runs with AgentDiff."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

from typing_extensions import Self

if TYPE_CHECKING:
    from types import TracebackType

from ..diff_engine import DiffEngine, EnvironmentSnapshot, FilesystemSnapshot
from ..evaluator import AgentDiffEvaluator, EvaluationResult
from ..trajectory import AgentFramework, TrajectoryTracker
from .mcp_policy import MCPPolicyHook, ToolCallBlockedError, ToolCallDecision

Snapshot: TypeAlias = tuple[FilesystemSnapshot, EnvironmentSnapshot]


def _resolve_targets(root: str, targets: list[str]) -> list[str]:
    root_path = Path(root).resolve()
    return [
        str(path.resolve() if path.is_absolute() else (root_path / path).resolve())
        for target in targets
        if (path := Path(target))
    ]


@dataclass(slots=True)
class AgentDiffConfig:
    """Configuration shared by framework integrations."""

    target_paths: list[str] | None = None
    cleanliness_threshold: float = 0.8
    root: str = "."
    ignore_patterns: list[str] | None = None
    capture_env_vars: bool = True
    capture_processes: bool = True
    capture_ports: bool = True


class _EvaluationLifecycle:
    """Shared snapshot, trajectory, and evaluation lifecycle."""

    def __init__(
        self,
        task_description: str,
        config: AgentDiffConfig | None = None,
        framework: AgentFramework = AgentFramework.CUSTOM,
    ) -> None:
        self.config = config or AgentDiffConfig()
        targets = self.config.target_paths or []
        self.engine = DiffEngine(
            watch_paths=[self.config.root],
            ignore_patterns=self.config.ignore_patterns,
            capture_env_vars=self.config.capture_env_vars,
            capture_processes=self.config.capture_processes,
            capture_ports=self.config.capture_ports,
        )
        self.tracker = TrajectoryTracker(task_description=task_description, framework=framework)
        self.evaluator = AgentDiffEvaluator(
            target_paths=[self.config.root],
            cleanliness_threshold=self.config.cleanliness_threshold,
        )
        self.evaluator.set_target_mutations(_resolve_targets(self.config.root, targets))
        self.pre_snapshot: Snapshot | None = None
        self._final_result: Any = None
        self._final_error: str | None = None

    def start(self) -> None:
        """Capture the baseline snapshot."""
        self.pre_snapshot = self.engine.snapshot()

    def record_step(
        self,
        thought: str,
        tool_name: str = "",
        tool_args: dict[str, Any] | None = None,
        tool_result: Any = None,
        observation: str = "",
        error: str | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        """Record one agent step and its optional tool call."""
        self.tracker.start_step(thought=thought)
        if tool_name:
            self.tracker.record_tool_call(
                name=tool_name,
                arguments=tool_args or {},
                result=tool_result,
                error=error,
                duration_ms=duration_ms,
            )
        self.tracker.end_step(observation=observation)

    def evaluate(self) -> EvaluationResult:
        """Capture the final state and evaluate the completed trajectory."""
        if self.pre_snapshot is None:
            raise RuntimeError("Call start() or enter the session before evaluate()")
        post_snapshot = self.engine.snapshot()
        trajectory = self.tracker.finish(
            final_result=self._final_result,
            final_error=self._final_error,
        )
        return self.evaluator.evaluate_from_snapshots(
            trajectory,
            self.pre_snapshot,
            post_snapshot,
        )


class BaseAgentDiffAdapter(_EvaluationLifecycle, ABC):
    """Base lifecycle for framework-specific adapters."""

    @abstractmethod
    def attach(self, agent: Any) -> Any:
        """Attach framework callbacks and return the configured agent."""


class AgentDiffSession(_EvaluationLifecycle):
    """Context manager for evaluating any agent or automation workflow."""

    def __init__(
        self,
        task_description: str = "Agent run",
        config: AgentDiffConfig | None = None,
    ) -> None:
        super().__init__(task_description=task_description, config=config)

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_val is not None:
            self._final_error = str(exc_val)

    def record(
        self,
        thought: str,
        tool_name: str = "",
        tool_args: dict[str, Any] | None = None,
        tool_result: Any = None,
        observation: str = "",
        success: bool = True,
        error: str | None = None,
        duration_ms: float = 0.0,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """Record one framework-independent trajectory step."""
        step_error = error if error is not None else (None if success else "Step failed")
        self.tracker.start_step(thought=thought)
        if tool_name:
            self.tracker.record_tool_call(
                name=tool_name,
                arguments=tool_args or {},
                result=tool_result,
                error=step_error,
                duration_ms=duration_ms,
            )
        if tokens_in or tokens_out:
            self.tracker.record_llm_usage(tokens_in, tokens_out)
        self.tracker.end_step(observation=observation)


__all__ = [
    "AgentDiffConfig",
    "AgentDiffSession",
    "BaseAgentDiffAdapter",
    "MCPPolicyHook",
    "ToolCallBlockedError",
    "ToolCallDecision",
]

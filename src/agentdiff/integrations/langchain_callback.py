"""LangChain callback integration for AgentDiff."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from langchain_core.callbacks import BaseCallbackHandler

if TYPE_CHECKING:
    from types import TracebackType
    from uuid import UUID

    from langchain_core.agents import AgentAction, AgentFinish
    from langchain_core.outputs import LLMResult

from ..diff_engine import DiffEngine, DiffResult, EnvironmentSnapshot, FilesystemSnapshot
from ..evaluator import AgentDiffEvaluator, EvaluationResult
from ..trajectory import AgentFramework, TrajectoryRecord, TrajectoryTracker
from . import AgentDiffConfig, _resolve_targets

Snapshot = tuple[FilesystemSnapshot, EnvironmentSnapshot]


class AgentDiffCallbackHandler(BaseCallbackHandler):
    """Record LangChain tool activity and evaluate the resulting state changes."""

    def __init__(
        self,
        task_description: str = "LangChain agent run",
        target_paths: list[str] | None = None,
        cleanliness_threshold: float = 0.8,
        root: str = ".",
        ignore_patterns: list[str] | None = None,
        capture_env_vars: bool = True,
        capture_processes: bool = True,
        capture_ports: bool = True,
        config: AgentDiffConfig | None = None,
    ) -> None:
        super().__init__()
        self._task_description = task_description
        self.config = config or AgentDiffConfig(
            target_paths=target_paths,
            cleanliness_threshold=cleanliness_threshold,
            root=root,
            ignore_patterns=ignore_patterns,
            capture_env_vars=capture_env_vars,
            capture_processes=capture_processes,
            capture_ports=capture_ports,
        )
        targets = self.config.target_paths or []
        self.engine = DiffEngine(
            watch_paths=[self.config.root],
            ignore_patterns=self.config.ignore_patterns,
            capture_env_vars=self.config.capture_env_vars,
            capture_processes=self.config.capture_processes,
            capture_ports=self.config.capture_ports,
        )
        self.tracker = TrajectoryTracker(
            task_description=task_description,
            framework=AgentFramework.LANGCHAIN,
        )
        self.evaluator = AgentDiffEvaluator(
            target_paths=[self.config.root],
            cleanliness_threshold=self.config.cleanliness_threshold,
        )
        self.evaluator.set_target_mutations(_resolve_targets(self.config.root, targets))
        self.pre_snapshot: Snapshot | None = None
        self._current_thought = ""
        self._current_tool_name: str | None = None
        self._current_tool_args: dict[str, Any] = {}
        self._tool_start_time: float | None = None
        self._last_llm_tokens = (0, 0)
        self._final_result: Any = None
        self._final_error: str | None = None

    def start(self) -> None:
        """Capture the state immediately before the agent run."""
        self.pre_snapshot = self.engine.snapshot()

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Keep a bounded prompt excerpt as context for the next tool step."""
        del serialized, run_id, kwargs
        if prompts:
            self._current_thought = prompts[-1][:2000]

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Capture token usage when the model provider exposes it."""
        del run_id, kwargs
        usage = (response.llm_output or {}).get("token_usage", {})
        self._last_llm_tokens = (
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Start timing a LangChain tool call."""
        del run_id, kwargs
        self._tool_start_time = time.perf_counter()
        self._current_tool_name = str(serialized.get("name") or "unknown_tool")
        try:
            parsed = json.loads(input_str)
            self._current_tool_args = parsed if isinstance(parsed, dict) else {"input": parsed}
        except (json.JSONDecodeError, TypeError):
            self._current_tool_args = {"input": input_str}

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Record a successful tool call as one trajectory step."""
        del run_id, kwargs
        self._record_tool_step(result=output)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Record a failed tool call as one trajectory step."""
        del run_id, kwargs
        self._record_tool_step(error=str(error))

    def _record_tool_step(self, result: Any = None, error: str | None = None) -> None:
        duration_ms = 0.0
        if self._tool_start_time is not None:
            duration_ms = (time.perf_counter() - self._tool_start_time) * 1000
        self.tracker.start_step(thought=self._current_thought or "Tool execution")
        self.tracker.record_llm_usage(*self._last_llm_tokens)
        self.tracker.record_tool_call(
            name=self._current_tool_name or "unknown_tool",
            arguments=self._current_tool_args,
            result=result,
            error=error,
            duration_ms=duration_ms,
        )
        observation = f"ERROR: {error}" if error else str(result)
        self.tracker.end_step(observation=observation[:5000])
        self._current_thought = ""
        self._current_tool_name = None
        self._current_tool_args = {}
        self._tool_start_time = None
        self._last_llm_tokens = (0, 0)

    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Use ReAct logs as the thought associated with the next tool call."""
        del run_id, kwargs
        self._current_thought = action.log or f"Action: {action.tool}"

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Store the agent's final result without inventing an extra tool step."""
        del run_id, kwargs
        self._final_result = finish.return_values

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Store the final chain error for the evaluation record."""
        del run_id, kwargs
        self._final_error = str(error)

    def get_evaluation_result(self) -> EvaluationResult:
        """Capture the final state and evaluate the complete run."""
        if self.pre_snapshot is None:
            raise RuntimeError("Call start() before running the LangChain agent")
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

    def get_trajectory(self) -> TrajectoryRecord:
        """Return the trajectory collected so far."""
        return self.tracker.record

    def get_diff(self) -> DiffResult:
        """Capture and return the current state diff."""
        if self.pre_snapshot is None:
            raise RuntimeError("Call start() before requesting a diff")
        post_snapshot = self.engine.snapshot()
        pre_fs, pre_env = self.pre_snapshot
        post_fs, post_env = post_snapshot
        return self.engine.diff(pre_fs, post_fs, pre_env, post_env)

    def reset(self) -> None:
        """Reset callback state for a new run with the same configuration."""
        self.tracker = TrajectoryTracker(
            task_description=self._task_description,
            framework=AgentFramework.LANGCHAIN,
        )
        self.pre_snapshot = None
        self._current_thought = ""
        self._current_tool_name = None
        self._current_tool_args = {}
        self._tool_start_time = None
        self._last_llm_tokens = (0, 0)
        self._final_result = None
        self._final_error = None


LangChainCallbackHandler = AgentDiffCallbackHandler


def create_agentdiff_callback(**kwargs: Any) -> AgentDiffCallbackHandler:
    """Create a configured AgentDiff callback handler."""
    return AgentDiffCallbackHandler(**kwargs)


class AgentDiffLangChainSession:
    """Context manager that starts an AgentDiff LangChain callback."""

    def __init__(self, **kwargs: Any) -> None:
        self.callback = AgentDiffCallbackHandler(**kwargs)

    def __enter__(self) -> AgentDiffCallbackHandler:
        self.callback.start()
        return self.callback

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_val is not None:
            self.callback._final_error = str(exc_val)

    def evaluate(self) -> EvaluationResult:
        """Evaluate the callback's completed run."""
        return self.callback.get_evaluation_result()


__all__ = [
    "AgentDiffCallbackHandler",
    "AgentDiffLangChainSession",
    "LangChainCallbackHandler",
    "create_agentdiff_callback",
]

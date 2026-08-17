"""
Trajectory Tracker & Step Recorder for AgentDiff.

Records agent tool calls, thought processes, and execution steps
for later evaluation and debugging.
"""

import json
import time
import uuid
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from typing_extensions import Self

warnings.warn(
    "agentdiff.trajectory is deprecated since 0.2 and will be removed in 0.4 or later. "
    "Use agentdiff.transaction.RunStore for structured run evidence and event logging.",
    DeprecationWarning,
    stacklevel=2,
)


class AgentFramework(Enum):
    """Supported agent frameworks."""

    LANGCHAIN = "langchain"
    CREWAI = "crewai"
    AUTOGEN = "autogen"
    CLAUDE_CODE = "claude_code"
    HERMES = "hermes"
    CUSTOM = "custom"


@dataclass
class StepResult:
    """Result of a single trajectory step."""

    success: bool = True
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "error": self.error,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StepResult":
        return cls(
            success=data.get("success", True),
            error=data.get("error"),
            tokens_in=data.get("tokens_in", 0),
            tokens_out=data.get("tokens_out", 0),
            duration=data.get("duration", 0.0),
        )


@dataclass
class ToolCall:
    """A single tool/function call made by the agent."""

    name: str
    arguments: dict[str, Any]
    result: Any | None = None
    error: str | None = None
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass
class TrajectoryStep:
    """A single step in the agent's trajectory."""

    step_index: int
    thought: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    observation: str | None = None
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    llm_model: str | None = None
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "thought": self.thought,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "observation": self.observation,
            "llm_input_tokens": self.llm_input_tokens,
            "llm_output_tokens": self.llm_output_tokens,
            "llm_model": self.llm_model,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
        }

    @property
    def total_tool_duration_ms(self) -> float:
        return sum(tc.duration_ms for tc in self.tool_calls)

    @property
    def tool_call_count(self) -> int:
        return len(self.tool_calls)

    @property
    def failed_tool_calls(self) -> list[ToolCall]:
        return [tc for tc in self.tool_calls if not tc.succeeded]


@dataclass
class TrajectoryRecord:
    """Complete trajectory record for an agent run."""

    run_id: str
    task_description: str
    framework: AgentFramework
    steps: list[TrajectoryStep] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    final_result: Any | None = None
    final_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_description": self.task_description,
            "framework": self.framework.value,
            "steps": [s.to_dict() for s in self.steps],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "metadata": self.metadata,
            "final_result": self.final_result,
            "final_error": self.final_error,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path: str | Path) -> None:
        """Save trajectory to JSON file."""
        Path(path).write_text(self.to_json())

    @classmethod
    def load(cls, path: str | Path) -> "TrajectoryRecord":
        """Load trajectory from JSON file."""
        data = json.loads(Path(path).read_text())
        record = cls(
            run_id=data["run_id"],
            task_description=data["task_description"],
            framework=AgentFramework(data["framework"]),
            start_time=data["start_time"],
            end_time=data.get("end_time"),
            metadata=data.get("metadata", {}),
            final_result=data.get("final_result"),
            final_error=data.get("final_error"),
        )
        record.steps = [
            TrajectoryStep(
                step_index=s["step_index"],
                thought=s.get("thought"),
                tool_calls=[
                    ToolCall(
                        name=tc["name"],
                        arguments=tc["arguments"],
                        result=tc.get("result"),
                        error=tc.get("error"),
                        duration_ms=tc.get("duration_ms", 0),
                        timestamp=tc.get("timestamp", 0),
                        call_id=tc.get("call_id", ""),
                    )
                    for tc in s.get("tool_calls", [])
                ],
                observation=s.get("observation"),
                llm_input_tokens=s.get("llm_input_tokens", 0),
                llm_output_tokens=s.get("llm_output_tokens", 0),
                llm_model=s.get("llm_model"),
                timestamp=s.get("timestamp", 0),
                duration_ms=s.get("duration_ms", 0),
            )
            for s in data.get("steps", [])
        ]
        return record

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def total_tool_calls(self) -> int:
        return sum(s.tool_call_count for s in self.steps)

    @property
    def total_llm_tokens(self) -> int:
        return sum(s.llm_input_tokens + s.llm_output_tokens for s in self.steps)

    @property
    def failed_steps(self) -> list[TrajectoryStep]:
        return [s for s in self.steps if s.failed_tool_calls]

    def get_tool_call_sequence(self) -> list[ToolCall]:
        """Get all tool calls in execution order."""
        calls = []
        for step in self.steps:
            calls.extend(step.tool_calls)
        return calls

    def get_unique_tools_used(self) -> list[str]:
        """Get list of unique tool names used."""
        return list({tc.name for tc in self.get_tool_call_sequence()})

    def detect_loops(self, min_repeat: int = 3) -> list[dict[str, Any]]:
        """
        Detect repeated tool call patterns (potential loops).

        Returns list of loop patterns found.
        """
        calls = self.get_tool_call_sequence()
        if len(calls) < min_repeat * 2:
            return []

        loops = []
        # Simple sliding window detection
        for window_size in range(2, min(10, len(calls) // 2)):
            for i in range(len(calls) - window_size * min_repeat + 1):
                pattern = tuple(c.name for c in calls[i : i + window_size])
                matches = 1
                for j in range(1, min_repeat):
                    next_pattern = tuple(
                        c.name for c in calls[i + j * window_size : i + (j + 1) * window_size]
                    )
                    if next_pattern == pattern:
                        matches += 1
                    else:
                        break
                if matches >= min_repeat:
                    loops.append(
                        {
                            "pattern": list(pattern),
                            "start_index": i,
                            "repetitions": matches,
                            "window_size": window_size,
                        }
                    )
        return loops


class TrajectoryTracker:
    """
    Records agent execution trajectories.

    Can be used as a context manager or by manually calling
    start_step() / end_step() / record_tool_call().
    """

    def __init__(
        self,
        task_description: str,
        framework: AgentFramework = AgentFramework.CUSTOM,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.record = TrajectoryRecord(
            run_id=run_id or str(uuid.uuid4())[:12],
            task_description=task_description,
            framework=framework,
            metadata=metadata or {},
        )
        self._current_step: TrajectoryStep | None = None
        self._step_start_time: float | None = None

    def start_step(
        self, thought: str | None = None, step_index: int | None = None
    ) -> TrajectoryStep:
        """Begin a new trajectory step."""
        if self._current_step is not None:
            self.end_step()

        idx = step_index if step_index is not None else len(self.record.steps)
        self._current_step = TrajectoryStep(
            step_index=idx,
            thought=thought,
        )
        self._step_start_time = time.time()
        return self._current_step

    def end_step(self, observation: str | None = None) -> TrajectoryStep | None:
        """End the current step and add to record."""
        if self._current_step is None:
            return None

        if self._step_start_time:
            self._current_step.duration_ms = (time.time() - self._step_start_time) * 1000

        if observation:
            self._current_step.observation = observation

        self.record.steps.append(self._current_step)
        step = self._current_step
        self._current_step = None
        self._step_start_time = None
        return step

    def record_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
        result: Any = None,
        error: str | None = None,
        duration_ms: float = 0.0,
    ) -> ToolCall:
        """Record a tool call in the current step."""
        current_step = self._current_step
        if current_step is None:
            current_step = self.start_step()

        tool_call = ToolCall(
            name=name,
            arguments=arguments,
            result=result,
            error=error,
            duration_ms=duration_ms,
        )
        current_step.tool_calls.append(tool_call)
        return tool_call

    @contextmanager
    def track_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Iterator[Callable[[Any], None]]:
        """Context manager to time and record a tool call."""
        start = time.time()
        error: str | None = None
        result_box: dict[str, Any] = {}

        def set_result(value: Any) -> None:
            result_box["value"] = value

        try:
            yield set_result
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            self.record_tool_call(
                name,
                arguments,
                result_box.get("value"),
                error,
                duration_ms,
            )

    def record_llm_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str | None = None,
    ) -> None:
        """Record LLM token usage for current step."""
        current_step = self._current_step
        if current_step is None:
            current_step = self.start_step()
        current_step.llm_input_tokens = input_tokens
        current_step.llm_output_tokens = output_tokens
        current_step.llm_model = model

    def finish(
        self,
        final_result: Any = None,
        final_error: str | None = None,
    ) -> TrajectoryRecord:
        """Finalize the trajectory record."""
        if self._current_step is not None:
            self.end_step()

        self.record.end_time = time.time()
        self.record.final_result = final_result
        self.record.final_error = final_error
        return self.record

    def save(self, path: str | Path) -> None:
        """Save trajectory to file."""
        self.record.save(path)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.finish(
            final_error=str(exc_val) if exc_val else None,
        )


# Framework-specific integrations
class LangChainCallbackHandler:
    """LangChain callback handler for automatic trajectory tracking."""

    def __init__(self, tracker: TrajectoryTracker):
        self.tracker = tracker
        self._current_tool_start: float | None = None
        self._current_tool_name: str | None = None
        self._current_tool_args: dict | None = None

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs) -> None:
        # Could track LLM calls here
        pass

    def on_llm_end(self, response, **kwargs) -> None:
        # Extract token usage if available
        if hasattr(response, "llm_output") and response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            self.tracker.record_llm_usage(
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        self._current_tool_start = time.time()
        self._current_tool_name = serialized.get("name", "unknown")
        self._current_tool_args = {"input": input_str}

    def on_tool_end(self, output: str, **kwargs) -> None:
        if self._current_tool_start and self._current_tool_name:
            duration_ms = (time.time() - self._current_tool_start) * 1000
            self.tracker.record_tool_call(
                self._current_tool_name,
                self._current_tool_args or {},
                result=output,
                duration_ms=duration_ms,
            )
            self._current_tool_start = None

    def on_tool_error(self, error: Exception, **kwargs) -> None:
        if self._current_tool_start and self._current_tool_name:
            duration_ms = (time.time() - self._current_tool_start) * 1000
            self.tracker.record_tool_call(
                self._current_tool_name,
                self._current_tool_args or {},
                error=str(error),
                duration_ms=duration_ms,
            )
            self._current_tool_start = None


def create_tracker_for_framework(
    framework: AgentFramework,
    task_description: str,
    **kwargs,
) -> TrajectoryTracker:
    """Factory function to create tracker with framework-specific defaults."""
    return TrajectoryTracker(
        task_description=task_description,
        framework=framework,
        **kwargs,
    )

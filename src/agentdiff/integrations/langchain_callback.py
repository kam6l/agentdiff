"""
LangChain/LangGraph Callback Handler for AgentDiff

Usage:
    from agentdiff.integrations.langchain_callback import AgentDiffCallbackHandler
    
    callback = AgentDiffCallbackHandler(
        target_paths=["src/"],
        cleanliness_threshold=0.8,
    )
    
    agent = create_react_agent(..., callbacks=[callback])
    result = agent.invoke({"input": "Fix the bug"})
    
    eval_result = callback.get_evaluation_result()
    print(f"Cleanliness: {eval_result.metrics.cleanliness_score:.1%}")
"""

from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.agents import AgentAction, AgentFinish

from agentdiff import DiffEngine, TrajectoryTracker, AgentDiffEvaluator
from agentdiff.diff_engine import EnvironmentSnapshot
from agentdiff.trajectory import ToolCall, StepResult
from agentdiff.evaluator import EvaluationResult
from agentdiff.integrations import AgentDiffConfig


class AgentDiffCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that tracks agent trajectory and evaluates side effects.
    
    Captures:
    - LLM thoughts (on_llm_start/end)
    - Tool calls (on_tool_start/end)
    - Tool observations (on_tool_end)
    - Agent finish (on_agent_finish)
    
    Then evaluates full trajectory against environment state changes.
    """
    
    def __init__(
        self,
        target_paths: Optional[List[str]] = None,
        cleanliness_threshold: float = 0.8,
        efficiency_threshold: float = 0.7,
        root: str = ".",
        ignore_patterns: Optional[List[str]] = None,
        capture_env_vars: bool = True,
        capture_processes: bool = True,
        capture_ports: bool = True,
        config: Optional[AgentDiffConfig] = None,
    ):
        super().__init__()
        
        if config:
            self.config = config
        else:
            self.config = AgentDiffConfig(
                target_paths=target_paths or [],
                cleanliness_threshold=cleanliness_threshold,
                efficiency_threshold=efficiency_threshold,
                root=root,
                ignore_patterns=ignore_patterns or [
                    "*.pyc", "__pycache__", ".git", "*.log", ".venv", "node_modules"
                ],
                capture_env_vars=capture_env_vars,
                capture_processes=capture_processes,
                capture_ports=capture_ports,
            )
        
        self.engine = DiffEngine(
            root=self.config.root,
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
        
        # State tracking
        self._current_thought: str = ""
        self._current_tool_call: Optional[ToolCall] = None
        self._tool_start_time: float = 0
        self._llm_start_time: float = 0
        self._step_count: int = 0
    
    def start(self) -> None:
        """Explicitly start tracking (capture pre-snapshot)."""
        self.pre_snapshot = self.engine.capture()
    
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: uuid4,
        parent_run_id: Optional[uuid4] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Track LLM start - capture the prompt as 'thought'."""
        import time
        self._llm_start_time = time.time()
        
        # Extract the last user message or system prompt as thought
        if prompts:
            # Take the last prompt as the agent's current thinking
            self._current_thought = prompts[-1][:2000]  # Limit length
    
    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid4,
        parent_run_id: Optional[uuid4] = None,
        **kwargs: Any,
    ) -> None:
        """Track LLM end - capture token usage."""
        import time
        duration = time.time() - self._llm_start_time
        
        # Extract token usage if available
        tokens_in = 0
        tokens_out = 0
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)
        
        # Store for next tool call
        self._last_llm_tokens = (tokens_in, tokens_out)
        self._last_llm_duration = duration
    
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: uuid4,
        parent_run_id: Optional[uuid4] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Track tool start."""
        import time
        self._tool_start_time = time.time()
        
        tool_name = serialized.get("name", "unknown_tool")
        # Parse input_str as JSON if possible
        import json
        try:
            tool_args = json.loads(input_str)
        except (json.JSONDecodeError, TypeError):
            tool_args = {"input": input_str}
        
        self._current_tool_call = ToolCall(
            name=tool_name,
            args=tool_args,
            tool_id=str(run_id),
        )
    
    def on_tool_end(
        self,
        output: str,
        *,
        run_id: uuid4,
        parent_run_id: Optional[uuid4] = None,
        **kwargs: Any,
    ) -> None:
        """Track tool end - record complete step."""
        import time
        duration = time.time() - self._tool_start_time
        
        # Get token usage from last LLM call
        tokens_in, tokens_out = getattr(self, "_last_llm_tokens", (0, 0))
        
        # Record the step
        self.tracker.record_step(
            thought=self._current_thought or "Tool execution",
            tool_call=self._current_tool_call,
            observation=output[:5000],  # Limit length
            result=StepResult(
                success=True,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                duration=duration,
            ),
        )
        
        self._step_count += 1
        self._current_thought = ""
        self._current_tool_call = None
    
    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: uuid4,
        parent_run_id: Optional[uuid4] = None,
        **kwargs: Any,
    ) -> None:
        """Track tool error."""
        import time
        duration = time.time() - self._tool_start_time
        
        tokens_in, tokens_out = getattr(self, "_last_llm_tokens", (0, 0))
        
        self.tracker.record_step(
            thought=self._current_thought or "Tool execution (failed)",
            tool_call=self._current_tool_call,
            observation=f"ERROR: {str(error)}",
            result=StepResult(
                success=False,
                error=str(error),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                duration=duration,
            ),
        )
        
        self._step_count += 1
        self._current_thought = ""
        self._current_tool_call = None
    
    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: uuid4,
        parent_run_id: Optional[uuid4] = None,
        **kwargs: Any,
    ) -> None:
        """Track agent action (for ReAct-style agents)."""
        # This is called before tool execution in some agent types
        self._current_thought = action.log or f"Action: {action.tool}"
    
    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: uuid4,
        parent_run_id: Optional[uuid4] = None,
        **kwargs: Any,
    ) -> None:
        """Track agent finish - record final step."""
        # Record final thought/result
        output = finish.return_values.get("output", "")
        
        self.tracker.record_step(
            thought="Agent completed task",
            tool_call=None,
            observation=output[:5000],
            result=StepResult(
                success=True,
                tokens_in=0,
                tokens_out=0,
            ),
        )
        
        self._step_count += 1
    
    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: uuid4,
        parent_run_id: Optional[uuid4] = None,
        **kwargs: Any,
    ) -> None:
        """Track chain/agent error."""
        self.tracker.record_step(
            thought="Agent execution failed",
            tool_call=None,
            observation=f"ERROR: {str(error)}",
            result=StepResult(
                success=False,
                error=str(error),
            ),
        )
    
    def get_evaluation_result(self) -> EvaluationResult:
        """
        Evaluate the complete trajectory against environment changes.
        
        Must be called after agent execution completes.
        """
        if self.pre_snapshot is None:
            raise RuntimeError(
                "Pre-snapshot not captured. Call start() before running the agent, "
                "or ensure the callback is used from the beginning."
            )
        
        post_snapshot = self.engine.capture()
        diff = self.engine.diff(self.pre_snapshot, post_snapshot)
        trajectory = self.tracker.get_trajectory()
        
        return self.evaluator.evaluate(diff, trajectory)
    
    def get_trajectory(self):
        """Get the recorded trajectory."""
        return self.tracker.get_trajectory()
    
    def get_diff(self):
        """Get the environment diff (requires pre_snapshot to be set)."""
        if self.pre_snapshot is None:
            raise RuntimeError("Pre-snapshot not captured")
        post_snapshot = self.engine.capture()
        return self.engine.diff(self.pre_snapshot, post_snapshot)
    
    def reset(self) -> None:
        """Reset for a new agent run."""
        self.tracker = TrajectoryTracker()
        self.pre_snapshot = None
        self._current_thought = ""
        self._current_tool_call = None
        self._step_count = 0


# Convenience function for simple usage
def create_agentdiff_callback(
    target_paths: Optional[List[str]] = None,
    cleanliness_threshold: float = 0.8,
    **kwargs,
) -> AgentDiffCallbackHandler:
    """Create a pre-configured AgentDiff callback handler."""
    return AgentDiffCallbackHandler(
        target_paths=target_paths,
        cleanliness_threshold=cleanliness_threshold,
        **kwargs,
    )


# Context manager for explicit control
class AgentDiffLangChainSession:
    """
    Context manager for explicit AgentDiff tracking with LangChain.
    
    Usage:
        with AgentDiffLangChainSession(target_paths=["src/"]) as session:
            result = agent.invoke({"input": "Fix the bug"})
            eval_result = session.evaluate()
    """
    
    def __init__(self, **kwargs):
        self.callback = AgentDiffCallbackHandler(**kwargs)
    
    def __enter__(self) -> AgentDiffCallbackHandler:
        self.callback.start()
        return self.callback
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
    
    def evaluate(self) -> EvaluationResult:
        return self.callback.get_evaluation_result()
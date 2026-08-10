"""Transport-neutral policy hook for MCP-style tool calls.

This module does not implement an MCP client, server, or proxy. It provides a
small enforcement hook that a transport adapter can call before dispatching a
tool invocation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from agentdiff.policy import Policy, PolicyAction, PolicyDecision, PolicyEngine


@dataclass(frozen=True, slots=True)
class ToolCallDecision:
    """Redacted, serializable decision for a proposed tool call."""

    action: PolicyAction
    tool_name: str
    subjects: tuple[str, ...]
    rule: str
    reason: str
    policy_version: int
    phase: str = "intercept"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["action"] = self.action.value
        value["subjects"] = list(self.subjects)
        return value


class ToolCallBlockedError(PermissionError):
    """Raised when a hook refuses to dispatch a deny/review tool call."""

    def __init__(self, decision: ToolCallDecision) -> None:
        self.decision = decision
        super().__init__(decision.reason)


_MUTATING_FILESYSTEM_TOOLS = frozenset(
    {
        "apply_patch",
        "create_directory",
        "delete_file",
        "edit_file",
        "move_file",
        "remove_directory",
        "rename_file",
        "write_file",
    }
)
_READ_ONLY_FILESYSTEM_TOOLS = frozenset(
    {"get_file_info", "list_directory", "read_file", "search_files"}
)
_COMMAND_TOOLS = frozenset({"execute_command", "run_command", "spawn_process"})
_PATH_KEYS = ("path", "file_path", "source", "destination", "target")


def _tool_suffix(name: str) -> str:
    normalized = name.strip().lower().replace("-", "_")
    if "__" in normalized:
        return normalized.rsplit("__", 1)[-1]
    return normalized.rsplit(".", 1)[-1]


def _highest(decisions: list[PolicyDecision]) -> PolicyDecision:
    for action in (PolicyAction.DENY, PolicyAction.REVIEW, PolicyAction.ALLOW):
        for decision in decisions:
            if decision.action is action:
                return decision
    raise ValueError("at least one decision is required")


class MCPPolicyHook:
    """Evaluate recognized MCP-style filesystem and command calls pre-dispatch."""

    def __init__(self, policy: Policy) -> None:
        self.engine = PolicyEngine(policy)

    def evaluate(self, tool_name: str, arguments: object) -> ToolCallDecision:
        """Return allow/review/deny without retaining arbitrary tool arguments."""

        name = str(tool_name)
        suffix = _tool_suffix(name)
        if not isinstance(arguments, Mapping):
            return self._review(name, "tool arguments are not a mapping")

        if suffix in _READ_ONLY_FILESYSTEM_TOOLS:
            return ToolCallDecision(
                action=PolicyAction.ALLOW,
                tool_name=name,
                subjects=(),
                rule="mcp.read_only_tool",
                reason="recognized read-only filesystem tool",
                policy_version=self.engine.policy.version,
            )

        if suffix in _MUTATING_FILESYSTEM_TOOLS:
            subjects = tuple(
                str(arguments[key])
                for key in _PATH_KEYS
                if key in arguments and isinstance(arguments[key], str) and arguments[key]
            )
            if not subjects:
                return self._review(name, "recognized mutating tool has no usable path")
            try:
                decisions = [
                    self.engine.decide_path(subject, phase="intercept") for subject in subjects
                ]
            except ValueError:
                return self._review(name, "mutating tool contains an unsafe path")
            selected = _highest(decisions)
            return ToolCallDecision(
                action=selected.action,
                tool_name=name,
                subjects=subjects,
                rule=selected.rule,
                reason=selected.reason,
                policy_version=selected.policy_version,
                phase=selected.phase,
            )

        if suffix in _COMMAND_TOOLS:
            argv = arguments.get("argv")
            if isinstance(argv, list) and argv and all(isinstance(item, str) for item in argv):
                selected = self.engine.decide_command(argv, phase="intercept")
                return ToolCallDecision(
                    action=selected.action,
                    tool_name=name,
                    subjects=(selected.subject,),
                    rule=selected.rule,
                    reason=selected.reason,
                    policy_version=selected.policy_version,
                    phase=selected.phase,
                )
            if isinstance(arguments.get("command"), str):
                return self._review(name, "shell command strings are not parsed or authorized")
            return self._review(name, "command tool has no string argv sequence")

        return self._review(name, "unknown tool has no declared mutation semantics")

    def authorize(
        self,
        tool_name: str,
        arguments: object,
        *,
        allow_review: bool = False,
    ) -> ToolCallDecision:
        """Raise before dispatch unless the decision is accepted by the caller."""

        decision = self.evaluate(tool_name, arguments)
        if decision.action is PolicyAction.DENY or (
            decision.action is PolicyAction.REVIEW and not allow_review
        ):
            raise ToolCallBlockedError(decision)
        return decision

    def _review(self, tool_name: str, reason: str) -> ToolCallDecision:
        return ToolCallDecision(
            action=PolicyAction.REVIEW,
            tool_name=tool_name,
            subjects=(),
            rule="mcp.unresolved",
            reason=reason,
            policy_version=self.engine.policy.version,
        )

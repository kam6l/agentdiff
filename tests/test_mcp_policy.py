from __future__ import annotations

import pytest

from agentdiff.integrations import MCPPolicyHook, ToolCallBlockedError
from agentdiff.policy import PolicyAction, load_policy


def _hook() -> MCPPolicyHook:
    policy = load_policy(
        {
            "version": 1,
            "filesystem": {
                "allow_write": ["src/**"],
                "deny": [".env", ".env.*"],
                "default": "review",
            },
            "process": {"allow": ["python*"], "default": "review"},
        }
    )
    return MCPPolicyHook(policy)


def test_mcp_filesystem_write_uses_the_same_path_policy() -> None:
    hook = _hook()

    allowed = hook.evaluate("filesystem.write_file", {"path": "src/app.py", "content": "ok"})
    denied = hook.evaluate("mcp__filesystem__write_file", {"path": ".env", "content": "secret"})

    assert allowed.action is PolicyAction.ALLOW
    assert allowed.subjects == ("src/app.py",)
    assert denied.action is PolicyAction.DENY
    assert denied.rule == "filesystem.deny[0]"
    assert "secret" not in str(denied.to_dict())


def test_mcp_command_argv_uses_process_policy_without_shell_parsing() -> None:
    hook = _hook()

    allowed = hook.evaluate("execute_command", {"argv": ["python3", "agent.py"]})
    unparsed = hook.evaluate("execute_command", {"command": "python3 agent.py"})

    assert allowed.action is PolicyAction.ALLOW
    assert unparsed.action is PolicyAction.REVIEW
    assert "shell command strings are not parsed" in unparsed.reason


def test_unknown_or_malformed_mutating_tools_fail_to_review() -> None:
    hook = _hook()

    unknown = hook.evaluate("vendor.mutate_everything", {"token": "hidden"})
    missing_path = hook.evaluate("filesystem.delete_file", {})

    assert unknown.action is PolicyAction.REVIEW
    assert missing_path.action is PolicyAction.REVIEW
    assert "hidden" not in str(unknown.to_dict())


def test_authorize_blocks_deny_and_review_unless_review_is_explicitly_accepted() -> None:
    hook = _hook()

    with pytest.raises(ToolCallBlockedError):
        hook.authorize("filesystem.write_file", {"path": ".env"})
    with pytest.raises(ToolCallBlockedError):
        hook.authorize("vendor.unknown", {})

    decision = hook.authorize("vendor.unknown", {}, allow_review=True)
    assert decision.action is PolicyAction.REVIEW

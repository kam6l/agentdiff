"""Deterministic policy evaluation with explainable rule provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from agentdiff.pathing import glob_matches, normalize_relative_path

from .models import Policy, PolicyAction


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """One deterministic outcome and the exact rule that produced it."""

    action: PolicyAction
    subject: str
    rule: str
    pattern: str | None
    reason: str
    policy_version: int
    phase: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["action"] = self.action.value
        return value


@dataclass(frozen=True, slots=True)
class LimitViolation:
    """An observed count that exceeds a configured policy limit."""

    name: str
    observed: int | float
    limit: int

    def to_dict(self) -> dict[str, int | float | str]:
        return asdict(self)


def _matches(subject: str, pattern: str) -> bool:
    return glob_matches(subject, pattern)


def _evaluate_patterns(
    *,
    subject: str,
    sections: Sequence[tuple[str, PolicyAction, tuple[str, ...]]],
    default: PolicyAction,
    default_rule: str,
    policy_version: int,
    phase: str,
) -> PolicyDecision:
    for rule_name, action, patterns in sections:
        for index, pattern in enumerate(patterns):
            if _matches(subject, pattern):
                return PolicyDecision(
                    action=action,
                    subject=subject,
                    rule=f"{rule_name}[{index}]",
                    pattern=pattern,
                    reason=f"matched {rule_name}[{index}] pattern {pattern!r}",
                    policy_version=policy_version,
                    phase=phase,
                )
    return PolicyDecision(
        action=default,
        subject=subject,
        rule=default_rule,
        pattern=None,
        reason=f"no explicit rule matched; used {default_rule}",
        policy_version=policy_version,
        phase=phase,
    )


class PolicyEngine:
    """Evaluate schema-v1 policies without network or model calls."""

    def __init__(self, policy: Policy) -> None:
        self.policy = policy

    def decide_path(self, path: str, *, phase: str = "post_run") -> PolicyDecision:
        """Classify one root-relative path; deny rules always take precedence."""

        if phase not in {"intercept", "post_run"}:
            raise ValueError("path decision phase must be intercept or post_run")
        subject = normalize_relative_path(path)
        filesystem = self.policy.filesystem
        return _evaluate_patterns(
            subject=subject,
            sections=(
                ("filesystem.deny", PolicyAction.DENY, filesystem.deny),
                ("filesystem.review", PolicyAction.REVIEW, filesystem.review),
                ("filesystem.allow_write", PolicyAction.ALLOW, filesystem.allow_write),
            ),
            default=filesystem.default,
            default_rule="filesystem.default",
            policy_version=self.policy.version,
            phase=phase,
        )

    def decide_command(self, command: Sequence[str], *, phase: str = "preflight") -> PolicyDecision:
        """Classify the executable basename of a shell-free argv sequence."""

        if phase not in {"intercept", "preflight"}:
            raise ValueError("command decision phase must be intercept or preflight")
        if not command or not str(command[0]) or "\x00" in str(command[0]):
            raise ValueError("command must contain a valid executable")
        subject = str(command[0]).replace("\\", "/").rsplit("/", 1)[-1]
        process = self.policy.process
        return _evaluate_patterns(
            subject=subject,
            sections=(
                ("process.deny", PolicyAction.DENY, process.deny),
                ("process.review", PolicyAction.REVIEW, process.review),
                ("process.allow", PolicyAction.ALLOW, process.allow),
            ),
            default=process.default,
            default_rule="process.default",
            policy_version=self.policy.version,
            phase=phase,
        )

    def evaluate_limits(
        self,
        *,
        files_changed: int,
        files_deleted: int,
        processes_spawned: int,
        duration_seconds: float,
    ) -> list[LimitViolation]:
        """Return all exceeded non-negative limits in stable schema order."""

        observed: tuple[tuple[str, int | float, int | None], ...] = (
            ("files_changed", files_changed, self.policy.limits.files_changed),
            ("files_deleted", files_deleted, self.policy.limits.files_deleted),
            ("processes_spawned", processes_spawned, self.policy.limits.processes_spawned),
            ("duration_seconds", duration_seconds, self.policy.limits.duration_seconds),
        )
        return [
            LimitViolation(name=name, observed=value, limit=limit)
            for name, value, limit in observed
            if limit is not None and value > limit
        ]


def policy_to_dict(policy: Policy) -> dict[str, Any]:
    """Serialize a policy with stable primitive values and explicit defaults."""

    return {
        "version": policy.version,
        "filesystem": {
            "allow_write": list(policy.filesystem.allow_write),
            "review": list(policy.filesystem.review),
            "deny": list(policy.filesystem.deny),
            "default": policy.filesystem.default.value,
        },
        "process": {
            "allow": list(policy.process.allow),
            "review": list(policy.process.review),
            "deny": list(policy.process.deny),
            "default": policy.process.default.value,
        },
        "network": {"mode": policy.network.mode.value},
        "limits": {
            "files_changed": policy.limits.files_changed,
            "files_deleted": policy.limits.files_deleted,
            "processes_spawned": policy.limits.processes_spawned,
            "duration_seconds": policy.limits.duration_seconds,
        },
        "rollback": {
            "enabled": policy.rollback.enabled,
            "max_backup_file_mb": policy.rollback.max_backup_file_mb,
        },
        "scoring": {"weights": dict(policy.scoring.weights)},
    }

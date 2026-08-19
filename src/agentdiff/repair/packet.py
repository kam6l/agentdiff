"""Deterministic failure packet for bounded automatic repair.

When proof fails, AgentDiff does not immediately ask the developer. It creates
a small deterministic failure packet describing exactly what failed, what
changed, the current policy, the allowed scope, and the risk evidence, and
sends that packet back to the same agent for a bounded repair attempt.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FailurePacket:
    """The complete, bounded context a repair attempt is allowed to see."""

    run_id: str
    attempt: int
    failed_phases: tuple[dict[str, Any], ...]
    failed_tests: tuple[str, ...]
    changed_files: tuple[dict[str, Any], ...]
    policy: dict[str, Any]
    allowed_scope: tuple[str, ...]
    risk: dict[str, Any]
    reasons: tuple[str, ...]
    patch_digest: str = ""
    base_digest: str = ""
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FailurePacket":
        return cls(
            run_id=str(value["run_id"]),
            attempt=int(value["attempt"]),
            failed_phases=tuple(
                item for item in value.get("failed_phases", []) if isinstance(item, dict)
            ),
            failed_tests=tuple(str(item) for item in value.get("failed_tests", [])),
            changed_files=tuple(
                item for item in value.get("changed_files", []) if isinstance(item, dict)
            ),
            policy=dict(value.get("policy", {})),
            allowed_scope=tuple(str(item) for item in value.get("allowed_scope", [])),
            risk=dict(value.get("risk", {})),
            reasons=tuple(str(item) for item in value.get("reasons", [])),
            patch_digest=str(value.get("patch_digest", "")),
            base_digest=str(value.get("base_digest", "")),
        )

    def to_markdown(self) -> str:
        """Render the packet as a bounded repair directive for the agent."""
        phases = (
            "\n".join(
                f"- `{phase.get('phase')}` returncode={phase.get('returncode')}"
                for phase in self.failed_phases
            )
            or "- (no phase evidence)"
        )
        tests = "\n".join(f"- `{test}`" for test in self.failed_tests) or "- (unknown)"
        files = (
            "\n".join(
                f"- `{change.get('path')}` ({change.get('change_type')}, {change.get('decision')})"
                for change in self.changed_files
            )
            or "- (no file evidence)"
        )
        scope = ", ".join(self.allowed_scope) or "(none configured)"
        risk = (
            f"immediate={self.risk.get('immediate_blast_radius')} "
            f"future={self.risk.get('future_blast_radius')}"
        )
        return f"""# Bounded repair request (attempt {self.attempt})

Fix ONLY the failing verification below. Stay inside the allowed scope.
Do not add dependencies, change CI/build configuration, or request new
permissions. If a fix requires new scope, stop and report that instead.

## Failed verification phases
{phases}

## Failed tests
{tests}

## Changed files in this run
{files}

## Deterministic policy (immutable during repair)
```yaml
{self._yaml_summary()}
```

## Allowed write scope
{scope}

## Risk evidence
{risk}

## Reasons proof did not pass
{chr(10).join(f"- {reason}" for reason in self.reasons) or "- (none recorded)"}
"""

    def _yaml_summary(self) -> str:
        filesystem = self.policy.get("filesystem") or {}
        return (
            f"version: {self.policy.get('version', 1)}\n"
            f"default: {filesystem.get('default', 'review')}\n"
            f"allow_write: {filesystem.get('allow_write', [])}\n"
            f"review: {filesystem.get('review', [])}\n"
            f"deny: {filesystem.get('deny', [])}"
        )

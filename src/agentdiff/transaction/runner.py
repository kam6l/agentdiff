"""End-to-end AgentDiff run transaction orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from agentdiff.policy import (
    LimitViolation,
    NetworkMode,
    Policy,
    PolicyAction,
    PolicyDecision,
    PolicyEngine,
    policy_to_dict,
)
from agentdiff.runtime import LocalRuntime, RuntimeBackend, RuntimeResult
from agentdiff.scoring import (
    BlastRadiusResult,
    BlastRadiusScorer,
    BlastRadiusWeights,
    MutationRisk,
)
from agentdiff.state import (
    FileChange,
    FileRecord,
    FilesystemManifest,
    FilesystemScanner,
    diff_manifests,
)

from .store import RunStore

if TYPE_CHECKING:
    import os
    from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class ChangeAssessment:
    """One observed mutation enriched with deterministic policy and recovery evidence."""

    path: str
    change_type: str
    content_changed: bool
    mode_changed: bool
    decision: PolicyDecision
    reversible: bool
    recovery_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "content_changed": self.content_changed,
            "mode_changed": self.mode_changed,
            "decision": self.decision.action.value,
            "policy_decision": self.decision.to_dict(),
            "reversible": self.reversible,
            "recovery_reason": self.recovery_reason,
        }


@dataclass(frozen=True, slots=True)
class ObservationWarning:
    """Evidence that the scanner could not safely model an entry."""

    path: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class TransactionResult:
    """Unified result for one command transaction."""

    run_id: str
    status: str
    safety_outcome: PolicyAction
    command_decision: PolicyDecision
    changes: list[ChangeAssessment]
    limit_violations: list[LimitViolation]
    observation_warnings: list[ObservationWarning]
    blast_radius: BlastRadiusResult
    runtime: RuntimeResult | None
    execution_error: dict[str, Any] | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "status": self.status,
            "safety_outcome": self.safety_outcome.value,
            "command_decision": self.command_decision.to_dict(),
            "changes": [change.to_dict() for change in self.changes],
            "limit_violations": [violation.to_dict() for violation in self.limit_violations],
            "observation_warnings": [warning.to_dict() for warning in self.observation_warnings],
            "blast_radius": self.blast_radius.to_dict(),
            "runtime": self.runtime.to_dict() if self.runtime is not None else None,
            "execution_error": self.execution_error,
        }

    def recommended_exit_code(self, fail_on: str = "deny") -> int:
        """Map runtime and safety outcomes to a stable CLI exit status."""

        if fail_on not in {"never", "review", "deny"}:
            raise ValueError("fail_on must be never, review, or deny")
        if self.execution_error is not None or self.status == "error":
            return 1
        if self.runtime is not None and self.runtime.returncode != 0:
            return self.runtime.returncode if 0 < self.runtime.returncode < 256 else 1
        if self.status == "blocked":
            return 126
        if fail_on == "deny" and self.safety_outcome is PolicyAction.DENY:
            return 3
        if fail_on == "review" and self.safety_outcome in {
            PolicyAction.REVIEW,
            PolicyAction.DENY,
        }:
            return 2
        return 0


def _recovery_evidence(
    change: FileChange,
    before: FileRecord | None,
    after: FileRecord | None,
) -> tuple[bool, str]:
    if change.change_type == "created":
        if after is None or after.kind != "file":
            return False, "created entry is not a regular file"
        if after.sha256 is None:
            return False, "created file was not hashable"
        if after.link_count != 1:
            return False, "created file has multiple hardlinks"
        return True, "current state can be verified before deletion"

    if before is None or before.kind != "file":
        return False, "before-state is not a regular file"
    if before.sha256 is None:
        return False, "before-state was not hashable"
    if before.link_count != 1:
        return False, "before-state has multiple hardlinks"
    if before.backup_path is None:
        return False, before.backup_error or "no recovery backup is available"
    if change.change_type == "modified":
        if after is None or after.kind != "file" or after.sha256 is None:
            return False, "after-state cannot be verified"
        if after.link_count != 1:
            return False, "after-state has multiple hardlinks"
    return True, "verified backup is available"


def _highest_action(actions: list[PolicyAction]) -> PolicyAction:
    if PolicyAction.DENY in actions:
        return PolicyAction.DENY
    if PolicyAction.REVIEW in actions:
        return PolicyAction.REVIEW
    return PolicyAction.ALLOW


def _validate_recovery_backups(
    store: RunStore,
    before: FilesystemManifest,
) -> FilesystemManifest:
    """Drop recovery references that a wrapped process altered during execution."""

    files = dict(before.files)
    unsupported = dict(before.unsupported)
    for path, record in before.files.items():
        if record.backup_path is None or record.sha256 is None:
            continue
        try:
            store.verify_backup(
                record.backup_path,
                sha256=record.sha256,
                size=record.size,
            )
        except (OSError, RuntimeError, ValueError):
            reason = "backup integrity verification failed after execution"
            files[path] = replace(
                record,
                backup_path=None,
                backup_error=reason,
            )
            unsupported[path] = reason
    return replace(before, files=files, unsupported=unsupported)


class AgentRunTransaction:
    """Observe, execute, classify, score, and persist one local command run."""

    def __init__(
        self,
        *,
        root: str | os.PathLike[str],
        policy: Policy,
        task: str | None = None,
        runtime: RuntimeBackend | None = None,
        run_id: str | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self.policy = policy
        self.task = task
        self.runtime = runtime
        self.requested_run_id = run_id
        self._used = False

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        stdin: int | IO[Any] | None = None,
        stdout: int | IO[Any] | None = None,
        stderr: int | IO[Any] | None = None,
    ) -> TransactionResult:
        if self._used:
            raise RuntimeError("a transaction instance can run only once")
        self._used = True
        command = tuple(argv)
        engine = PolicyEngine(self.policy)
        command_decision = engine.decide_command(command)
        store = RunStore.create(
            self.root,
            task=self.task,
            command=command,
            run_id=self.requested_run_id,
        )
        trusted_metadata = store.read_json("metadata.json")
        store.write_json("policy.json", policy_to_dict(self.policy))
        store.append_event("transaction_started", {"command_decision": command_decision.to_dict()})

        protected_patterns = list(self.policy.filesystem.deny)
        scanner = FilesystemScanner(
            self.root,
            backup_dir=store.backup_dir if self.policy.rollback.enabled else None,
            backup_max_file_mb=self.policy.rollback.max_backup_file_mb,
            protected_patterns=protected_patterns,
        )
        before = scanner.capture(backup=self.policy.rollback.enabled)
        store.write_json("before.json", before.to_dict())
        store.append_event(
            "before_captured",
            {"files": len(before.files), "unsupported": len(before.unsupported)},
        )

        runtime_result: RuntimeResult | None = None
        execution_error: dict[str, Any] | None = None
        blocked = command_decision.action is PolicyAction.DENY
        if not blocked:
            selected_runtime = self.runtime or LocalRuntime(
                self.root,
                observe_ports=self.policy.network.mode is NetworkMode.OBSERVE,
            )
            effective_timeout = timeout_seconds
            policy_timeout = self.policy.limits.duration_seconds
            if policy_timeout is not None:
                normalized_policy_timeout = max(0.001, float(policy_timeout))
                effective_timeout = (
                    normalized_policy_timeout
                    if effective_timeout is None
                    else min(effective_timeout, normalized_policy_timeout)
                )
            try:
                runtime_result = selected_runtime.run(
                    command,
                    timeout_seconds=effective_timeout,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                )
            except OSError as error:
                execution_error = {
                    "type": type(error).__name__,
                    "errno": error.errno,
                }
                store.restore_trusted_event_log()
                store.append_event("execution_error", execution_error)
            else:
                store.restore_trusted_event_log()
                store.append_event(
                    "runtime_completed",
                    {
                        "returncode": runtime_result.returncode,
                        "timed_out": runtime_result.timed_out,
                        "duration_seconds": runtime_result.duration_seconds,
                    },
                )

        before = _validate_recovery_backups(store, before)
        store.write_json("metadata.json", trusted_metadata)
        store.write_json("policy.json", policy_to_dict(self.policy))
        store.write_json("before.json", before.to_dict())
        store.write_json(
            "runtime.json",
            runtime_result.to_dict()
            if runtime_result is not None
            else {
                "schema_version": 1,
                "executed": False,
                "blocked": blocked,
                "execution_error": execution_error,
            },
        )
        after = FilesystemScanner(
            self.root,
            protected_patterns=protected_patterns,
        ).capture()
        store.write_json("after.json", after.to_dict())

        changes = []
        for change in diff_manifests(before, after):
            decision = engine.decide_path(change.path)
            if self.policy.rollback.enabled:
                reversible, recovery_reason = _recovery_evidence(
                    change,
                    before.files.get(change.path),
                    after.files.get(change.path),
                )
            else:
                reversible, recovery_reason = False, "rollback disabled by policy"
            changes.append(
                ChangeAssessment(
                    path=change.path,
                    change_type=change.change_type,
                    content_changed=change.content_changed,
                    mode_changed=change.mode_changed,
                    decision=decision,
                    reversible=reversible,
                    recovery_reason=recovery_reason,
                )
            )

        unsupported_paths = sorted(set(before.unsupported) | set(after.unsupported))
        observation_warnings = [
            ObservationWarning(
                path=path,
                reason=after.unsupported.get(path)
                or before.unsupported.get(path)
                or "unsupported entry",
            )
            for path in unsupported_paths
        ]
        files_deleted = sum(change.change_type == "deleted" for change in changes)
        processes_spawned = len(runtime_result.owned_processes) if runtime_result is not None else 0
        duration = runtime_result.duration_seconds if runtime_result is not None else 0.0
        limit_violations = engine.evaluate_limits(
            files_changed=len(changes),
            files_deleted=files_deleted,
            processes_spawned=processes_spawned,
            duration_seconds=duration,
        )
        orphan_processes = 0
        opened_ports = 0
        if runtime_result is not None:
            opened_ports = len(runtime_result.port_observation.opened)
            if runtime_result.cleanup is None:
                orphan_processes = len(runtime_result.owned_processes)
            else:
                orphan_processes = sum(
                    outcome.action in {"access_denied", "still_running"}
                    for outcome in runtime_result.cleanup.outcomes
                )
        weights = BlastRadiusWeights.from_mapping(dict(self.policy.scoring.weights))
        blast_radius = BlastRadiusScorer(weights).score(
            (
                MutationRisk(
                    path=change.path,
                    change_type=change.change_type,
                    decision=change.decision.action,
                    mode_changed=change.mode_changed,
                )
                for change in changes
            ),
            orphan_processes=orphan_processes,
            opened_ports=opened_ports,
            budget_violations=len(limit_violations),
        )

        actions = [command_decision.action, *(change.decision.action for change in changes)]
        if limit_violations or observation_warnings:
            actions.append(PolicyAction.REVIEW)
        safety_outcome = _highest_action(actions)
        if blocked:
            status = "blocked"
        elif execution_error is not None:
            status = "error"
        elif runtime_result is not None and runtime_result.timed_out:
            status = "timed_out"
        elif runtime_result is not None and runtime_result.returncode != 0:
            status = "failed"
        elif safety_outcome is PolicyAction.DENY:
            status = "denied"
        elif safety_outcome is PolicyAction.REVIEW:
            status = "review"
        else:
            status = "passed"

        result = TransactionResult(
            run_id=store.run_id,
            status=status,
            safety_outcome=safety_outcome,
            command_decision=command_decision,
            changes=changes,
            limit_violations=limit_violations,
            observation_warnings=observation_warnings,
            blast_radius=blast_radius,
            runtime=runtime_result,
            execution_error=execution_error,
        )
        store.write_json("result.json", result.to_dict())
        store.append_event(
            "transaction_completed",
            {
                "status": status,
                "safety_outcome": safety_outcome.value,
                "files_changed": len(changes),
                "blast_radius": blast_radius.score,
            },
        )
        store.finalize_integrity()
        return result

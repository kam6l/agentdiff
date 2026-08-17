"""End-to-end AgentDiff run transaction orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from agentdiff.analyzers import FutureBlastEngine, FutureBlastResult
from agentdiff.evidence.patch import (
    capture_patch,
    capture_source_snapshot,
    validate_source_snapshot,
)
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
from agentdiff.safety import SafetyController
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
    future_blast_radius: FutureBlastResult | None = None
    safety: dict[str, Any] | None = None
    patch_digest: str | None = None
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
            "future_blast_radius": (
                self.future_blast_radius.to_dict() if self.future_blast_radius is not None else None
            ),
            "safety": self.safety,
            "patch_digest": self.patch_digest,
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
            PolicyAction.DENY,
            PolicyAction.REVIEW,
        }:
            return 3
        return 0


def _recovery_evidence(
    change: FileChange,
    before_record: FileRecord | None,
    after_record: FileRecord | None,
) -> tuple[bool, str]:
    if change.change_type == "created":
        if after_record is not None and after_record.kind == "file":
            return True, "created regular file can be unlinked"
        return False, "created non-regular entry cannot be unlinked safely"
    if before_record is not None and before_record.backup_error is not None:
        return False, f"backup integrity failed: {before_record.backup_error}"
    if change.change_type == "deleted":
        if before_record is not None and before_record.backup_path is not None:
            return True, "pre-run regular file backup is available"
        return False, "file backup is missing or unsupported"
    if change.change_type == "modified":
        if before_record is not None and before_record.backup_path is not None:
            return True, "pre-run regular file backup is available"
        return False, "pre-run backup is missing or unsupported"
    return False, "unsupported mutation type"


def _highest_action(actions: Sequence[PolicyAction]) -> PolicyAction:
    if any(action is PolicyAction.DENY for action in actions):
        return PolicyAction.DENY
    if any(action is PolicyAction.REVIEW for action in actions):
        return PolicyAction.REVIEW
    return PolicyAction.ALLOW


def _validate_recovery_backups(
    store: RunStore,
    manifest: FilesystemManifest,
) -> FilesystemManifest:
    """Drop backup references for files modified during the run."""

    if not manifest.files:
        return manifest
    verified_files: dict[str, FileRecord] = {}
    verified_unsupported = dict(manifest.unsupported)
    for path, record in manifest.files.items():
        if record.backup_path is None:
            verified_files[path] = record
            continue
        assert record.sha256 is not None
        try:
            store.verify_backup(
                record.backup_path,
                sha256=record.sha256,
                size=record.size,
            )
            verified_files[path] = record
        except Exception as error:
            verified_unsupported[path] = f"backup validation failed: {error}"
            verified_files[path] = replace(
                record,
                backup_path=None,
                backup_error=f"backup validation failed: {error}",
            )
    return FilesystemManifest(
        schema_version=manifest.schema_version,
        captured_at=manifest.captured_at,
        root=manifest.root,
        files=verified_files,
        unsupported=verified_unsupported,
    )


class AgentRunTransaction:
    """Stateful coordinator for one AgentDiff command transaction."""

    def __init__(
        self,
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

        source_snapshot = capture_source_snapshot(store, before)

        runtime_result: RuntimeResult | None = None
        execution_error: dict[str, Any] | None = None
        blocked = command_decision.action is PolicyAction.DENY
        safety_controller: SafetyController | None = None
        selected_runtime: RuntimeBackend | None = None

        if not blocked:
            selected_runtime = self.runtime or LocalRuntime(
                self.root,
                observe_ports=self.policy.network.mode is NetworkMode.OBSERVE,
            )
            if hasattr(selected_runtime, "configure_source"):
                selected_runtime.configure_source(store.artifact_path("source/files"))

            isolated_workspace = (
                getattr(selected_runtime, "enforcement", "") == "isolated_private_workspace"
            )
            safety_controller = SafetyController(
                policy=self.policy,
                before=before,
                backend=getattr(selected_runtime, "backend", "local-observe"),
                isolated_workspace=isolated_workspace,
            )
            if hasattr(selected_runtime, "configure_safety"):
                selected_runtime.configure_safety(safety_controller)

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

        observation_root = (
            Path(runtime_result.observation_root)
            if runtime_result is not None and runtime_result.observation_root is not None
            else self.root
        )
        after = FilesystemScanner(
            observation_root,
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

        patch_manifest = capture_patch(
            store,
            changes=changes,
            before=before,
            after=after,
            after_root=observation_root,
        )

        future_engine = FutureBlastEngine()
        future_blast = future_engine.analyze(
            changes,
            before_root=store.artifact_path("source/files"),
            after_root=observation_root,
        )

        validate_source_snapshot(store, source_snapshot)

        unsupported_paths = sorted(set(before.unsupported) | set(after.unsupported))
        observation_warnings = [
            ObservationWarning(
                path=path,
                reason=after.unsupported.get(path)
                or before.unsupported.get(path)
                or "unsupported entry",
            )
        ] if False else [
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

        is_terminated = bool(safety_controller is not None and safety_controller.terminated)
        if blocked:
            status = "blocked"
        elif is_terminated:
            status = "terminated"
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

        safety_report = safety_controller.report.to_dict() if safety_controller is not None else None
        result = TransactionResult(
            run_id=store.run_id,
            status=status,
            safety_outcome=safety_outcome,
            command_decision=command_decision,
            changes=changes,
            limit_violations=limit_violations,
            observation_warnings=observation_warnings,
            blast_radius=blast_radius,
            future_blast_radius=future_blast,
            safety=safety_report,
            patch_digest=patch_manifest.digest,
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
                "future_blast_radius": future_blast.score,
            },
        )
        store.finalize_integrity()
        if selected_runtime is not None and hasattr(selected_runtime, "close"):
            selected_runtime.close()
        return result


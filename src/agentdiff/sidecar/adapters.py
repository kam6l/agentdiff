"""Zero-touch agent adapter: ``agentdiff wrap -- <agent argv>``.

Wraps any coding-agent CLI (codex, claude, gemini, copilot) so AgentDiff
automatically manages:

1. a trusted warm workspace (immutable base, private CoW clone);
2. the observed/enforced transaction with the canonical policy;
3. clean-room proof (impact-aware, cache-backed);
4. bounded automatic repair when proof fails;
5. conflict-safe promotion of the proven result to the host repository;
6. local notifications for AUTO / RETRY / HUMAN routing.

The human is interrupted only when the trust boundary changes.
"""

from __future__ import annotations

import contextlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agentdiff.impact.cache import ProofCache
from agentdiff.policy import Policy, load_policy
from agentdiff.promotion import PromotionEngine
from agentdiff.proof import ProofEngine, ProofVerdict
from agentdiff.repair import RepairLoop, default_repair_command_builder
from agentdiff.runtime import DockerRuntime, LocalRuntime, MaterializationStrategy
from agentdiff.transaction import AgentRunTransaction
from agentdiff.workspace import WarmWorkspaceFactory, compute_identity

from .notify import Notification, Notifier

_PROOF_TIMEOUT_SECONDS = 900.0


@dataclass(frozen=True, slots=True)
class WrapSummary:
    """Machine-readable result of one zero-touch agent wrap."""

    run_id: str
    status: str  # PROVEN | NOT_PROVEN | REPAIRED | NEEDS_HUMAN | NEEDS_AGENT | BLOCKED | ERROR
    routing: str  # AUTO | RETRY | HUMAN
    workspace: str
    proof_verdict: str | None = None
    repair_outcome: str | None = None
    promotion_status: str | None = None
    human_reason: str = ""
    notifications: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "status": self.status,
            "routing": self.routing,
            "workspace": self.workspace,
            "proof_verdict": self.proof_verdict,
            "repair_outcome": self.repair_outcome,
            "promotion_status": self.promotion_status,
            "human_reason": self.human_reason,
            "notifications": list(self.notifications),
        }


class WrapRunner:
    """Execute one agent command through the full zero-touch pipeline."""

    def __init__(
        self,
        root: str | Path,
        *,
        policy: Policy | None = None,
        policy_file: str | None = None,
        enable_proof: bool = True,
        enable_repair: bool = True,
        enable_promote: bool = True,
        max_attempts: int = 2,
        max_repair_runtime: float = 1800.0,
        use_cache: bool = True,
        notify: bool = True,
        environment_factory: Callable[..., Any] | None = None,
        runtime_backend: Any = None,
        session_id: str | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self.policy = policy
        self.policy_file = policy_file
        self.enable_proof = enable_proof
        self.enable_repair = enable_repair
        self.enable_promote = enable_promote
        self.max_attempts = max_attempts
        self.max_repair_runtime = max_repair_runtime
        self.use_cache = use_cache
        self.notifier = Notifier(self.root, echo=notify)
        self.environment_factory = environment_factory
        self.runtime_backend = runtime_backend
        self.session_id = session_id

    def wrap(self, argv: list[str], *, task: str = "") -> WrapSummary:
        notifications: list[str] = []
        policy = self._resolve_policy()
        factory = WarmWorkspaceFactory(self.root, strategy=MaterializationStrategy.AUTO)
        identity = compute_identity(self.root, policy=policy)
        agent_workspace = factory.create_workspace(identity, session_id=self.session_id)
        cache = ProofCache(self.root) if self.use_cache else None
        attempt_workspaces: list[Any] = []

        def base_preparer(workspace: Path) -> None:
            _copy_writable(agent_workspace.base.path, workspace)

        def fresh_attempt_workspace() -> Path:
            # Every repair attempt starts from the same trusted warm base, so
            # proof always verifies a clean base plus the repaired patch.
            attempt_ws = factory.create_workspace(identity)
            attempt_workspaces.append(attempt_ws)
            return attempt_ws.path

        try:
            runtime = self.runtime_backend or self._select_runtime(policy, agent_workspace.path)
            transaction = AgentRunTransaction(
                root=agent_workspace.path,
                policy=policy,
                task=task or "agentdiff wrap",
                runtime=runtime,
            )
            result = transaction.run(argv)

            if not self.enable_proof:
                self._notify(
                    notifications,
                    Notification(
                        kind="auto",
                        title="Run completed without proof",
                        message=f"run {result.run_id} status={result.status}",
                        run_id=result.run_id,
                    ),
                )
                return WrapSummary(
                    run_id=result.run_id,
                    status="NOT_PROVEN",
                    routing="AUTO",
                    workspace=str(agent_workspace.path),
                )

            proof = ProofEngine(
                agent_workspace.path,
                result.run_id,
                cache=cache,
                base_preparer=base_preparer,
                environment_factory=self.environment_factory,
            ).prove(timeout_seconds=_PROOF_TIMEOUT_SECONDS)

            repair_outcome: str | None = None
            repair_workspace: Path | None = None
            final_run_id = result.run_id
            if proof.verdict is not ProofVerdict.PROVEN and self.enable_repair:
                loop = RepairLoop(
                    agent_workspace.path,
                    result.run_id,
                    policy=policy,
                    max_attempts=self.max_attempts,
                    max_runtime_seconds=self.max_repair_runtime,
                    cache=cache,
                    base_preparer=base_preparer,
                    environment_factory=self.environment_factory,
                    repair_command_builder=default_repair_command_builder(argv),
                    runtime_backend=runtime,
                    attempt_workspace_factory=fresh_attempt_workspace,
                )
                outcome = loop.run()
                repair_outcome = outcome.status
                repair_workspace = (
                    Path(outcome.workspace) if outcome.workspace is not None else None
                )
                if outcome.status == "REPAIRED" and outcome.repaired_run_id is not None:
                    final_run_id = outcome.repaired_run_id
                    proof = ProofEngine(
                        repair_workspace or agent_workspace.path,
                        final_run_id,
                        cache=cache,
                        base_preparer=base_preparer,
                        environment_factory=self.environment_factory,
                    ).prove(timeout_seconds=_PROOF_TIMEOUT_SECONDS)
                elif outcome.status in {"NEEDS_HUMAN", "BLOCKED"}:
                    self._notify(
                        notifications,
                        Notification(
                            kind="human",
                            title="Repair stopped: trust boundary would change",
                            message=outcome.human_reason,
                            run_id=result.run_id,
                        ),
                    )
                    return WrapSummary(
                        run_id=result.run_id,
                        status="NEEDS_HUMAN",
                        routing="HUMAN",
                        workspace=str(agent_workspace.path),
                        proof_verdict=proof.verdict.value,
                        repair_outcome=repair_outcome,
                        human_reason=outcome.human_reason,
                        notifications=tuple(notifications),
                    )
                elif outcome.status == "NEEDS_AGENT":
                    self._notify(
                        notifications,
                        Notification(
                            kind="human",
                            title="Repair needs the agent",
                            message=(
                                "Failure packet written; re-run wrap with the same agent command."
                            ),
                            run_id=result.run_id,
                        ),
                    )
                    return WrapSummary(
                        run_id=result.run_id,
                        status="NEEDS_AGENT",
                        routing="HUMAN",
                        workspace=str(agent_workspace.path),
                        proof_verdict=proof.verdict.value,
                        repair_outcome=repair_outcome,
                        notifications=tuple(notifications),
                    )

            if proof.verdict is not ProofVerdict.PROVEN:
                self._notify(
                    notifications,
                    Notification(
                        kind="human",
                        title="Proof did not pass",
                        message="; ".join(proof.reasons[:3]),
                        run_id=final_run_id,
                    ),
                )
                return WrapSummary(
                    run_id=final_run_id,
                    status="NOT_PROVEN",
                    routing="RETRY",
                    workspace=str(agent_workspace.path),
                    proof_verdict=proof.verdict.value,
                    repair_outcome=repair_outcome,
                    notifications=tuple(notifications),
                )

            promotion_status: str | None = None
            if self.enable_promote:
                capsule_root = repair_workspace or agent_workspace.path
                promotion = PromotionEngine(
                    self.root,
                    final_run_id,
                    store_root=capsule_root,
                ).promote(safe_only=True)
                promotion_status = promotion.status
                if promotion.status == "PROMOTED":
                    self._notify(
                        notifications,
                        Notification(
                            kind="auto",
                            title="Proven change promoted",
                            message=f"run {final_run_id} delivered to the repository",
                            run_id=final_run_id,
                        ),
                    )
                else:
                    self._notify(
                        notifications,
                        Notification(
                            kind="human",
                            title="Promotion blocked",
                            message=f"{promotion.status}: "
                            + ", ".join(conflict.reason for conflict in promotion.conflicts[:3]),
                            run_id=final_run_id,
                        ),
                    )
                    return WrapSummary(
                        run_id=final_run_id,
                        status="NEEDS_HUMAN",
                        routing="HUMAN",
                        workspace=str(agent_workspace.path),
                        proof_verdict=proof.verdict.value,
                        repair_outcome=repair_outcome,
                        promotion_status=promotion_status,
                        human_reason="promotion conflicts require human attention",
                        notifications=tuple(notifications),
                    )

            self._notify(
                notifications,
                Notification(
                    kind="auto",
                    title="Proof passed",
                    message=f"run {final_run_id} is PROVEN",
                    run_id=final_run_id,
                ),
            )
            return WrapSummary(
                run_id=final_run_id,
                status="REPAIRED" if repair_outcome == "REPAIRED" else "PROVEN",
                routing="AUTO",
                workspace=str(agent_workspace.path),
                proof_verdict=proof.verdict.value,
                repair_outcome=repair_outcome,
                promotion_status=promotion_status,
                notifications=tuple(notifications),
            )
        finally:
            agent_workspace.close()
            for attempt_ws in attempt_workspaces:
                attempt_ws.close()

    def _resolve_policy(self) -> Policy:
        if self.policy is not None:
            return self.policy
        if self.policy_file:
            from agentdiff.policy import load_policy_file

            return load_policy_file(self.policy_file)
        default_path = self.root / "agentdiff.yaml"
        if default_path.is_file() and not default_path.is_symlink():
            from agentdiff.policy import load_policy_file

            return load_policy_file(default_path)
        return load_policy(
            {
                "version": 2,
                "filesystem": {"allow_write": ["**"], "default": "allow"},
                "process": {"default": "allow"},
                "network": {"mode": "observe"},
            }
        )

    @staticmethod
    def _select_runtime(policy: Policy, workspace: Path) -> Any:
        backend = getattr(getattr(policy, "runtime", None), "backend", None)
        if backend == "docker" and shutil.which("docker") is not None:
            try:
                return DockerRuntime(
                    workspace,
                    image=policy.proof.image or "python:3.12-slim",
                )
            except (OSError, TypeError, ValueError):
                pass
        return LocalRuntime(workspace)

    def _notify(self, notifications: list[str], notification: Notification) -> None:
        path = self.notifier.notify(notification)
        notifications.append(str(path))


def _copy_writable(source: Path, destination: Path) -> None:
    """Copy an immutable warm base tree into a writable proof workspace."""
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True, symlinks=False)
        else:
            shutil.copy2(child, target)
    # Reset permissions so the proof workspace is writable.
    for directory, directory_names, file_names in _walk(destination):
        for name in directory_names:
            with contextlib.suppress(OSError):
                (Path(directory) / name).chmod(0o755)
        for name in file_names:
            with contextlib.suppress(OSError):
                (Path(directory) / name).chmod(0o644)


def _walk(root: Path):
    import os

    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        yield directory, directory_names, file_names

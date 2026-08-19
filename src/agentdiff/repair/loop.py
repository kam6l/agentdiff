"""Proof-driven automatic repair loop.

When proof fails, AgentDiff builds a deterministic failure packet and sends it
back to the same agent for a bounded repair attempt — without asking the
developer. Limits:

- ``max_attempts`` (bounded, no infinite retry loops)
- ``max_runtime_seconds`` (monotonic budget)
- no silent scope expansion: any dependency/CI/config/security change,
  any ``review``/``deny`` policy action, or high future risk stops the loop
  and routes to a human
- no permission escalation: repair runs under the same policy and sandbox
- the agent can never approve its own permissions

The loop is deterministic: verdicts come from :class:`ProofEngine` only.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from agentdiff.policy import Policy, load_policy, policy_to_dict
from agentdiff.proof import ProofEngine, ProofVerdict
from agentdiff.transaction import AgentRunTransaction
from agentdiff.transaction.store import RunStore

from .packet import FailurePacket

if TYPE_CHECKING:
    from agentdiff.impact.cache import ProofCache

RepairCommandBuilder = Callable[[FailurePacket], list[str]]


def build_repair_prompt(packet: FailurePacket, packet_path: str) -> str:
    """Build the bounded repair prompt sent back to the same agent."""
    return (
        "Your previous change did not pass AgentDiff clean-room proof.\n"
        f"Read the failure packet: {packet_path}\n\n"
        "Fix ONLY the failing verification. Keep every change inside the "
        "allowed scope from the packet. Do NOT add dependencies, do NOT "
        "change CI/build/agent configuration, and do NOT request new "
        "permissions. If a correct fix requires new scope, stop and say so."
    )


def default_repair_command_builder(original_argv: list[str]) -> RepairCommandBuilder:
    """Re-invoke the same agent CLI with the bounded repair prompt.

    Prompt-taking CLIs (codex/claude/gemini: ``exec``/``-p``/``ask``) have the
    prompt argument replaced; other commands get the prompt appended. The
    agent still runs under the original policy and sandbox.
    """

    def build(packet: FailurePacket) -> list[str]:
        prompt = build_repair_prompt(packet, str(packet_path(packet)))
        argv = list(original_argv)
        if len(argv) >= 2 and argv[1] in {"exec", "-p", "--print", "ask"}:
            return [*argv[:2], prompt, *argv[2:]]
        return [*argv, prompt]

    def packet_path(packet: FailurePacket) -> Path:
        # Placeholder; replaced by the loop which knows the real path.
        return Path(f".agentdiff/repair/{packet.run_id}/attempt-{packet.attempt}-packet.json")

    return build


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """One proof attempt in a repair loop."""

    attempt: int
    run_id: str
    verdict: str
    reasons: tuple[str, ...]
    packet_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "run_id": self.run_id,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "packet_path": self.packet_path,
        }


@dataclass(frozen=True, slots=True)
class RepairOutcome:
    """Final result of one repair loop."""

    status: str  # REPAIRED | FAILED | NEEDS_HUMAN | NEEDS_AGENT | BLOCKED
    run_id: str
    attempts: tuple[AttemptRecord, ...]
    human_reason: str = ""
    repaired_run_id: str | None = None
    workspace: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "run_id": self.run_id,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "human_reason": self.human_reason,
            "repaired_run_id": self.repaired_run_id,
            "workspace": self.workspace,
        }


def detect_scope_change(
    changes_payload: list[dict[str, Any]],
    future_payload: dict[str, Any] | None,
    policy: Policy,
) -> tuple[bool, str]:
    """Return whether a run crossed the trust boundary.

    Crossing means: a ``review``/``deny`` policy action, a high-risk path
    (dependencies, CI, build config, agent configs, security paths), or a
    high/critical future blast radius.
    """
    from agentdiff.impact.impact import classify_risk
    from agentdiff.scoring import RiskLevel

    for change in changes_payload:
        decision = str(change.get("decision", ""))
        path = str(change.get("path", ""))
        if decision in {"deny", "review"}:
            return True, f"policy action {decision} on {path}"
        if classify_risk(path) == "full":
            return True, f"high-risk path changed: {path}"
    if future_payload is not None:
        level = str(future_payload.get("level", "")).upper()
        if level in {RiskLevel.HIGH.value.upper(), RiskLevel.CRITICAL.value.upper()}:
            return True, f"high future blast radius: {level}"
    return False, ""


class RepairLoop:
    """Run verified retries until proof passes or the trust boundary changes."""

    def __init__(
        self,
        root: str | Path,
        run_id: str,
        *,
        policy: Policy | None = None,
        max_attempts: int = 2,
        max_runtime_seconds: float = 1800.0,
        environment_factory: Callable[..., Any] | None = None,
        cache: ProofCache | None = None,
        base_preparer: Callable[[Path], None] | None = None,
        repair_command_builder: RepairCommandBuilder | None = None,
        runtime_backend: Any = None,
        target: str = "full",
        prove_timeout_seconds: float = 900.0,
        attempt_workspace_factory: Callable[[], Path] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be greater than zero")
        self.root = Path(root).expanduser().resolve(strict=True)
        self.run_id = run_id
        self.policy = policy
        self.max_attempts = max_attempts
        self.max_runtime_seconds = max_runtime_seconds
        self.environment_factory = environment_factory
        self.cache = cache
        self.base_preparer = base_preparer
        self.repair_command_builder = repair_command_builder
        self.runtime_backend = runtime_backend
        self.target = target
        self.prove_timeout_seconds = prove_timeout_seconds
        self.attempt_workspace_factory = attempt_workspace_factory

    def run(self) -> RepairOutcome:
        store = RunStore.open(self.root, self.run_id)
        integrity = store.verify_integrity()
        if not integrity.ok:
            raise PermissionError("sealed capsule integrity verification failed")
        policy = self.policy or load_policy(store.read_json("policy.json"))
        policy_payload = policy_to_dict(policy)

        started = time.monotonic()
        attempts: list[AttemptRecord] = []
        current_run_id = self.run_id
        current_workspace: Path | None = None
        attempt = 0

        while True:
            elapsed = time.monotonic() - started
            if elapsed > self.max_runtime_seconds:
                return RepairOutcome(
                    status="BLOCKED",
                    run_id=self.run_id,
                    attempts=tuple(attempts),
                    human_reason="repair loop exceeded the maximum runtime budget",
                )

            proof = ProofEngine(
                current_workspace or self.root,
                current_run_id,
                environment_factory=self.environment_factory,
                cache=self.cache,
                base_preparer=self.base_preparer,
                target=self.target,
            ).prove(timeout_seconds=self.prove_timeout_seconds)
            attempts.append(
                AttemptRecord(
                    attempt=attempt,
                    run_id=current_run_id,
                    verdict=proof.verdict.value,
                    reasons=proof.reasons,
                )
            )
            if proof.verdict is ProofVerdict.PROVEN:
                return RepairOutcome(
                    status="REPAIRED",
                    run_id=self.run_id,
                    attempts=tuple(attempts),
                    repaired_run_id=current_run_id,
                    workspace=str(current_workspace) if current_workspace is not None else None,
                )

            # Proof failed: decide between bounded retry and human review.
            if attempt >= self.max_attempts - 1:
                return RepairOutcome(
                    status="FAILED",
                    run_id=self.run_id,
                    attempts=tuple(attempts),
                    human_reason=f"proof failed after {attempt + 1} attempts",
                )

            run_store = RunStore.open(current_workspace or self.root, current_run_id)
            result_payload = run_store.read_json("result.json")
            changes_payload = (
                result_payload.get("changes", []) if isinstance(result_payload, dict) else []
            )
            future_payload = (
                result_payload.get("future_blast_radius")
                if isinstance(result_payload, dict)
                else None
            )
            crossed, reason = detect_scope_change(changes_payload, future_payload, policy)
            if crossed:
                return RepairOutcome(
                    status="NEEDS_HUMAN",
                    run_id=self.run_id,
                    attempts=tuple(attempts),
                    human_reason=f"repair would cross the trust boundary: {reason}",
                )

            packet = self._build_packet(
                run_store,
                result_payload,
                policy_payload,
                proof,
                attempt=attempt + 1,
            )
            packet_path = self._write_packet(packet)
            attempts[-1] = AttemptRecord(
                attempt=attempt,
                run_id=current_run_id,
                verdict=proof.verdict.value,
                reasons=proof.reasons,
                packet_path=str(packet_path),
            )

            if self.repair_command_builder is None:
                return RepairOutcome(
                    status="NEEDS_AGENT",
                    run_id=self.run_id,
                    attempts=tuple(attempts),
                    human_reason=(
                        "no repair command builder configured; "
                        "packet written for manual/agent repair"
                    ),
                )

            repair_argv = self.repair_command_builder(packet)
            workspace = (
                self.attempt_workspace_factory()
                if self.attempt_workspace_factory is not None
                else self.root
            )
            repaired = self._run_repair(
                root=workspace,
                policy=policy,
                argv=repair_argv,
                attempt=attempt + 1,
            )
            if repaired is None:
                return RepairOutcome(
                    status="NEEDS_HUMAN",
                    run_id=self.run_id,
                    attempts=tuple(attempts),
                    human_reason="repair run crossed the trust boundary",
                )
            current_run_id = repaired
            current_workspace = workspace if workspace != self.root else None
            attempt += 1

    def _build_packet(
        self,
        store: RunStore,
        result_payload: dict[str, Any],
        policy_payload: dict[str, Any],
        proof: Any,
        *,
        attempt: int,
    ) -> FailurePacket:
        changes = result_payload.get("changes", [])
        failed_tests: list[str] = []
        failed_phases: list[dict[str, Any]] = []
        for phase in proof.phases:
            if not phase.passed:
                failed_phases.append(
                    {
                        "phase": phase.phase,
                        "returncode": phase.returncode,
                        "output_sha256": phase.output_sha256,
                        "tests_passed": phase.tests_passed,
                        "tests_total": phase.tests_total,
                    }
                )
                if phase.tests_passed is not None and phase.tests_total is not None:
                    failed_tests.append(
                        f"{phase.phase}: {phase.tests_passed}/{phase.tests_total} passed"
                    )
        filesystem = policy_payload.get("filesystem", {})
        source = store.read_json_path("source/manifest.json")
        return FailurePacket(
            run_id=store.run_id,
            attempt=attempt,
            failed_phases=tuple(failed_phases),
            failed_tests=tuple(failed_tests),
            changed_files=tuple(
                {
                    "path": change.get("path"),
                    "change_type": change.get("change_type"),
                    "decision": change.get("decision"),
                }
                for change in changes
                if isinstance(change, dict)
            ),
            policy=policy_payload,
            allowed_scope=tuple(filesystem.get("allow_write", [])),
            risk={
                "immediate_blast_radius": (result_payload.get("blast_radius", {}).get("score", 0)),
                "future_blast_radius": (
                    result_payload.get("future_blast_radius", {}).get("score", 0)
                ),
                "future_level": (result_payload.get("future_blast_radius", {}).get("level", "")),
            },
            reasons=tuple(proof.reasons),
            patch_digest=str(proof.patch_digest),
            base_digest=str(source.get("digest", "")) if isinstance(source, dict) else "",
        )

    def _write_packet(self, packet: FailurePacket) -> Path:
        repair_dir = self.root / ".agentdiff" / "repair" / packet.run_id
        repair_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = repair_dir / f"attempt-{packet.attempt}-packet.json"
        payload = json.dumps(packet.to_dict(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(repair_dir)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            if os.name != "nt":
                path.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def _run_repair(
        self,
        *,
        root: Path,
        policy: Policy,
        argv: list[str],
        attempt: int,
    ) -> str | None:
        """Run one bounded repair attempt under the same policy and sandbox."""
        transaction = AgentRunTransaction(
            root=root,
            policy=policy,
            task=f"bounded repair attempt {attempt}",
            runtime=self.runtime_backend,
        )
        result = transaction.run(argv)
        crossed, _ = detect_scope_change(
            [change.to_dict() for change in result.changes],
            (
                result.future_blast_radius.to_dict()
                if result.future_blast_radius is not None
                else None
            ),
            policy,
        )
        if crossed:
            return None
        return result.run_id

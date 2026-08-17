"""Clean-room proof orchestration bound to sealed run evidence.

Two distinguishable verification concepts are produced:

- **Patched verification**: the complete patched project tests run in the
  clean room, exactly as today.
- **Baseline verification**: after the patched run, verifier-related files
  (tests, fixtures, runner config, manifests, lockfiles, CI workflows) are
  deterministically restored to their sealed **pre-run** versions, and the
  trusted test commands run again. This tests patched product code against
  the original trusted tests, so an agent that weakened the test suite to
  make it pass cannot hide behind its own modifications.

The baseline result, verifier-mutation report, and proof strength are
explanatory metadata; the PROVEN / NOT_PROVEN verdict stays deterministic
and fails closed whenever the baseline cannot confirm the patched run.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable

from agentdiff.evidence import PatchBundle
from agentdiff.policy import PolicyAction, load_policy
from agentdiff.redaction import redact_argv
from agentdiff.transaction.store import RunStore

from .environment import DockerProofEnvironment
from .hidden_state import hidden_state_result
from .models import (
    ProofPhaseResult,
    ProofResult,
    ProofStrengthLabel,
    ProofStrengthLevel,
    ProofVerdict,
    VerifierIndependence,
    strength_label,
)
from .plan import select_trusted_verification_plan
from .verifier_files import analyze_verifier_mutations, is_verifier_related

EnvironmentFactory = Callable[..., Any]

_CHUNK_SIZE = 1024 * 1024


def compute_proof_strength(
    *,
    clean_environment: str,
    trusted_plan: bool,
    baseline_verifier: str,
    baseline_available: bool,
    verifier_files_changed: int,
) -> tuple[ProofStrengthLevel, ProofStrengthLabel, VerifierIndependence]:
    """Deterministically derive proof-strength metadata from recorded evidence.

    Levels are cumulative: L3 implies L2/L1/L0. The label is a human summary
    of the level; neither the level nor the verdict is an LLM decision.
    """
    level = ProofStrengthLevel.L0_EXECUTION_ONLY
    if clean_environment == "PASS":
        level = ProofStrengthLevel.L1_CLEAN_ROOM
    if trusted_plan:
        level = ProofStrengthLevel.L2_TRUSTED_COMMAND
    baseline_confirms = baseline_available and baseline_verifier == "PASS"
    if baseline_confirms:
        level = ProofStrengthLevel.L3_BASELINE_VERIFIER
    if not baseline_available:
        independence = VerifierIndependence.WEAK
    elif baseline_verifier == "PASS":
        independence = VerifierIndependence.STRONG
    elif verifier_files_changed == 0:
        # No verifier file was touched and the baseline still could not run;
        # treat the verification as unconfirmed rather than independent.
        independence = VerifierIndependence.REVIEW
    else:
        independence = VerifierIndependence.REVIEW
    return level, strength_label(level), independence


class ProofEngine:
    """Rebuild a base-plus-patch workspace and verify it without LLM decisions."""

    def __init__(
        self,
        root: str | Path,
        run_id: str,
        *,
        environment_factory: EnvironmentFactory = DockerProofEnvironment,
    ) -> None:
        self.store = RunStore.open(root, run_id)
        self.environment_factory = environment_factory

    @classmethod
    def open(cls, root: str | Path, run_id: str) -> "ProofEngine":
        return cls(root, run_id)

    def prove(self, *, timeout_seconds: float = 900.0) -> ProofResult:
        if timeout_seconds <= 0:
            raise ValueError("proof timeout must be greater than zero")
        integrity = self.store.verify_integrity()
        if not integrity.ok:
            raise PermissionError("sealed capsule integrity verification failed")
        result_payload = self.store.read_json("result.json")
        policy_payload = self.store.read_json("policy.json")
        if not isinstance(result_payload, dict) or not isinstance(policy_payload, dict):
            raise ValueError("run result and policy must be mappings")
        policy = load_policy(policy_payload)
        bundle = PatchBundle(self.store)
        original_passed = str(result_payload.get("status")) in {"passed", "review"}
        policy_allowed = str(result_payload.get("safety_outcome")) == PolicyAction.ALLOW.value
        immediate = self._score(result_payload, "blast_radius")
        future = self._score(result_payload, "future_blast_radius")
        phases: list[ProofPhaseResult] = []
        reasons: list[str] = []
        environment_payload: dict[str, Any] = {
            "schema_version": 1,
            "backend": "docker",
            "clean_environment": False,
        }
        clean_environment = "FAIL"
        verifier_mutations = analyze_verifier_mutations(
            (entry.path, entry.change_type) for entry in bundle.manifest.entries
        )
        baseline_available = self._base_has_verifier_files()

        with tempfile.TemporaryDirectory(prefix="agentdiff-proof-") as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir(mode=0o700)
            try:
                # 1. Materialize base source first
                bundle.materialize_source(workspace)
                # 2. Select trusted verification plan from base state + patch analysis
                plan = select_trusted_verification_plan(workspace, policy, patch_bundle=bundle)
                if not plan.trusted:
                    reasons.append(f"untrusted verification plan: {plan.reason}")

                # 3. Apply patch on top of base
                bundle.apply(workspace)

                environment = self.environment_factory(
                    workspace=workspace,
                    image=plan.image,
                    network=plan.network,
                )
                try:
                    environment_payload = environment.start()
                    environment_payload["verification_plan"] = {
                        "schema_version": 1,
                        "source": plan.source,
                        "trusted": plan.trusted,
                        "plan_digest": plan.plan_digest,
                        "tampered_files": list(plan.tampered_files),
                        "setup": [redact_argv(command) for command in plan.setup],
                        "build": [redact_argv(command) for command in plan.build],
                        "tests": [redact_argv(command) for command in plan.tests],
                    }
                    environment_payload["verifier_mutations"] = verifier_mutations.to_dict()
                    clean_environment = "PASS"
                    commands = (
                        *(("dependency_setup", command) for command in plan.setup),
                        *(("build", command) for command in plan.build),
                        *(("tests", command) for command in plan.tests),
                    )
                    if not plan.tests:
                        reasons.append(
                            "no deterministic test command is configured or discoverable"
                        )
                    for phase_name, command in commands:
                        phase = environment.run_phase(
                            phase_name,
                            command,
                            timeout_seconds=timeout_seconds,
                        )
                        phases.append(phase)
                        if not phase.passed:
                            reasons.append(
                                f"{phase_name} failed with return code {phase.returncode}"
                            )
                            break

                    # 4. Baseline verification: patched product code against
                    #    the ORIGINAL trusted tests, independent of any
                    #    agent-modified verifier files.
                    baseline_verifier, baseline_phases, baseline_reasons = (
                        self._run_baseline_verification(
                            environment,
                            workspace,
                            bundle,
                            plan.tests,
                            timeout_seconds=timeout_seconds,
                            baseline_available=baseline_available,
                        )
                    )
                    phases.extend(baseline_phases)
                    reasons.extend(baseline_reasons)
                    environment_payload["baseline_verifier"] = baseline_verifier
                    environment_payload["baseline_available"] = baseline_available
                finally:
                    environment.close()
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                reasons.append(f"clean-room setup failed: {type(error).__name__}: {error}")

        if not original_passed:
            reasons.append("original agent run did not pass")
        if not policy_allowed:
            reasons.append("deterministic policy outcome is not ALLOW")
        if not bundle.manifest.complete:
            reasons.append("sealed patch evidence is incomplete")
        all_phases_pass = bool(phases) and all(phase.passed for phase in phases)
        has_test_phase = any(phase.phase == "tests" for phase in phases)
        baseline_verifier = str(environment_payload.get("baseline_verifier", "SKIPPED"))
        baseline_required = verifier_mutations.any_modification
        baseline_confirms = (
            not baseline_required
            or (baseline_available and baseline_verifier == "PASS")
        )
        if baseline_required and not baseline_confirms:
            if not baseline_available:
                reasons.append(
                    "verifier-related files were modified but no baseline verifier "
                    "is available from the pre-run state"
                )
            else:
                reasons.append(
                    "baseline verifier did not pass; patched tests cannot be "
                    "trusted against modified test/verifier code"
                )
        proven = (
            original_passed
            and policy_allowed
            and bundle.manifest.complete
            and clean_environment == "PASS"
            and all_phases_pass
            and has_test_phase
            and plan.trusted
            and baseline_confirms
            and not reasons
        )
        hidden_state = hidden_state_result(
            original_passed=original_passed,
            phases=tuple(phases),
        )
        tests_phase = next((phase for phase in phases if phase.phase == "tests"), None)
        baseline_phase = next(
            (phase for phase in phases if phase.phase == "baseline_tests"), None
        )
        level, label, independence = compute_proof_strength(
            clean_environment=clean_environment,
            trusted_plan=plan.trusted,
            baseline_verifier=baseline_verifier,
            baseline_available=baseline_available,
            verifier_files_changed=verifier_mutations.modified_count,
        )
        proof = ProofResult(
            run_id=self.store.run_id,
            verdict=ProofVerdict.PROVEN if proven else ProofVerdict.NOT_PROVEN,
            promotion="ALLOWED" if proven else "BLOCKED",
            agent_run="PASS" if original_passed else "FAIL",
            policy=(
                "ALLOW"
                if policy_allowed
                else str(result_payload.get("safety_outcome", "UNKNOWN")).upper()
            ),
            immediate_blast_radius=immediate,
            future_blast_radius=future,
            clean_environment=clean_environment,
            hidden_state_dependency=hidden_state,
            patch_digest=bundle.manifest.digest,
            immutable_manifest_sha256=self.store.immutable_manifest_sha256(),
            phases=tuple(phases),
            reasons=tuple(dict.fromkeys(reasons)),
            verification_source=plan.source,
            verification_digest=plan.plan_digest,
            trusted_plan=plan.trusted,
            baseline_verifier=baseline_verifier,
            baseline_tests_passed=(
                baseline_phase.tests_passed if baseline_phase is not None else None
            ),
            baseline_tests_total=(
                baseline_phase.tests_total if baseline_phase is not None else None
            ),
            patched_tests_passed=tests_phase.tests_passed if tests_phase is not None else None,
            patched_tests_total=tests_phase.tests_total if tests_phase is not None else None,
            verifier_files_changed=verifier_mutations.modified_count,
            verifier_changes=(
                *verifier_mutations.existing_changed,
                *verifier_mutations.added,
                *verifier_mutations.removed,
            ),
            baseline_available=baseline_available,
            verifier_independence=independence.value,
            proof_strength=level.value,
            proof_strength_label=label.value,
        )
        self.store.write_json_path("proof/environment.json", environment_payload)
        self.store.write_json_path("proof/result.json", proof.to_dict())
        self.store.seal_extension("proof", ("environment.json", "result.json"))
        return proof

    def _run_baseline_verification(
        self,
        environment: Any,
        workspace: Path,
        bundle: PatchBundle,
        test_commands: tuple[tuple[str, ...], ...],
        *,
        timeout_seconds: float,
        baseline_available: bool,
    ) -> tuple[str, list[ProofPhaseResult], list[str]]:
        """Overlay base verifier files and re-run the trusted test commands.

        Returns ``(status, phases, reasons)`` where status is PASS, FAIL, or
        SKIPPED. The overlay is applied in place: verifier-related files are
        restored to their sealed pre-run versions (including files the patch
        deleted or created), so the baseline run executes the original tests
        against the patched product code.
        """
        if not baseline_available or not test_commands:
            return "SKIPPED", [], []
        try:
            overlay_digest = self._overlay_baseline_verifier_files(workspace, bundle)
        except (OSError, RuntimeError, ValueError) as error:
            return "FAIL", [], [f"baseline verifier overlay failed: {error}"]
        phases: list[ProofPhaseResult] = []
        reasons: list[str] = []
        for command in test_commands:
            phase = environment.run_phase(
                "baseline_tests",
                command,
                timeout_seconds=timeout_seconds,
            )
            phases.append(phase)
            if not phase.passed:
                reasons.append(
                    f"baseline_tests failed with return code {phase.returncode}"
                )
                break
        status = "PASS" if phases and all(phase.passed for phase in phases) else "FAIL"
        return status, phases, reasons

    def _overlay_baseline_verifier_files(
        self,
        workspace: Path,
        bundle: PatchBundle,
    ) -> str:
        """Restore sealed pre-run verifier files over the patched workspace.

        Returns a digest of the restored file list for evidence. Only paths
        classified as verifier-related are touched; all writes are fsynced
        and atomic replacements, and every parent directory is validated.
        """
        raw = self.store.read_json_path("source/manifest.json")
        captured = raw.get("captured", []) if isinstance(raw, dict) else []
        base_verifier_paths = sorted(
            path for path in captured if isinstance(path, str) and is_verifier_related(path)
        )
        hasher = hashlib.sha256()
        for path in base_verifier_paths:
            source = self.store.artifact_path(f"source/files/{path}")
            info = source.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RuntimeError(f"baseline source is not a regular file: {path}")
            target = _safe_workspace_target(workspace, path, create_parents=True)
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            source_fd = os.open(source, flags)
            temporary = target.parent / (
                f".agentdiff-baseline-{hashlib.sha256(path.encode()).hexdigest()[:16]}.tmp"
            )
            try:
                opened = os.fstat(source_fd)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                    or opened.st_dev != info.st_dev
                    or opened.st_ino != info.st_ino
                ):
                    raise RuntimeError(f"baseline source changed while opening: {path}")
                digest = hashlib.sha256()
                with (
                    os.fdopen(source_fd, "rb", closefd=False) as src,
                    temporary.open("wb") as dst,
                ):
                    while chunk := src.read(_CHUNK_SIZE):
                        digest.update(chunk)
                        dst.write(chunk)
                    dst.flush()
                    os.fsync(dst.fileno())
                finished = os.fstat(source_fd)
                if (
                    finished.st_dev != opened.st_dev
                    or finished.st_ino != opened.st_ino
                    or finished.st_size != opened.st_size
                    or finished.st_mtime_ns != opened.st_mtime_ns
                ):
                    raise RuntimeError(f"baseline source changed while copying: {path}")
                os.replace(temporary, target)
                if os.name != "nt":
                    target.chmod(stat.S_IMODE(info.st_mode))
            finally:
                os.close(source_fd)
                temporary.unlink(missing_ok=True)
            hasher.update(path.encode("utf-8"))
        # Remove verifier files the patch added (they are not part of the
        # original trusted verifier and must not run during baseline tests).
        base_set = set(base_verifier_paths)
        for entry in bundle.manifest.entries:
            if entry.change_type != "created" or not is_verifier_related(entry.path):
                continue
            if entry.path in base_set:
                continue
            target = _safe_workspace_target(workspace, entry.path, create_parents=False)
            if target.is_file() and not target.is_symlink():
                target.unlink(missing_ok=True)
                hasher.update(f"removed:{entry.path}".encode("utf-8"))
        return hasher.hexdigest()

    def _base_has_verifier_files(self) -> bool:
        try:
            raw = self.store.read_json_path("source/manifest.json")
        except (OSError, ValueError, TypeError, FileNotFoundError):
            return False
        captured = raw.get("captured", []) if isinstance(raw, dict) else []
        return any(
            isinstance(path, str) and is_verifier_related(path) for path in captured
        )

    @staticmethod
    def _score(result: dict[str, Any], name: str) -> int:
        raw = result.get(name, {})
        return int(raw.get("score", 0)) if isinstance(raw, dict) else 0


def _safe_workspace_target(root: Path, relative: str, *, create_parents: bool) -> Path:
    """Validate a workspace-relative target without following symlinks."""
    from agentdiff.pathing import normalize_relative_path

    normalized = normalize_relative_path(relative)
    if normalized != relative:
        raise ValueError(f"unsafe workspace path: {relative!r}")
    target = root.joinpath(*normalized.split("/"))
    current = root
    for part in normalized.split("/")[:-1]:
        current /= part
        if current.exists() or current.is_symlink():
            info = current.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise ValueError(f"unsafe workspace parent: {current}")
        elif create_parents:
            current.mkdir(mode=0o700)
        else:
            raise ValueError(f"missing workspace parent: {current}")
    if target.is_symlink():
        raise ValueError(f"unsafe workspace target: {relative}")
    return target

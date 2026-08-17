"""Clean-room proof orchestration bound to sealed run evidence."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from agentdiff.evidence import PatchBundle
from agentdiff.policy import PolicyAction, load_policy
from agentdiff.redaction import redact_argv
from agentdiff.transaction.store import RunStore

from .environment import DockerProofEnvironment
from .hidden_state import hidden_state_result
from .models import ProofPhaseResult, ProofResult, ProofVerdict
from .verification import select_verification_plan

EnvironmentFactory = Callable[..., Any]


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

        with tempfile.TemporaryDirectory(prefix="agentdiff-proof-") as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir(mode=0o700)
            try:
                bundle.materialize_source(workspace)
                bundle.apply(workspace)
                plan = select_verification_plan(workspace, policy)
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
                        "setup": [redact_argv(command) for command in plan.setup],
                        "build": [redact_argv(command) for command in plan.build],
                        "tests": [redact_argv(command) for command in plan.tests],
                    }
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
        proven = (
            original_passed
            and policy_allowed
            and bundle.manifest.complete
            and clean_environment == "PASS"
            and all_phases_pass
            and has_test_phase
            and not reasons
        )
        hidden_state = hidden_state_result(
            original_passed=original_passed,
            phases=tuple(phases),
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
        )
        self.store.write_json_path("proof/environment.json", environment_payload)
        self.store.write_json_path("proof/result.json", proof.to_dict())
        self.store.seal_extension("proof", ("environment.json", "result.json"))
        return proof

    @staticmethod
    def _score(result: dict[str, Any], name: str) -> int:
        raw = result.get(name, {})
        return int(raw.get("score", 0)) if isinstance(raw, dict) else 0

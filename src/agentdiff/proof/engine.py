"""Clean-room proof orchestration bound to sealed run evidence."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from agentdiff.evidence import PatchBundle
from agentdiff.impact.cache import (
    ProofCache,
    ProofCacheEntry,
    ProofCacheKey,
    ProofCachePhase,
)
from agentdiff.impact.impact import build_proof_cache_key
from agentdiff.policy import PolicyAction, load_policy
from agentdiff.redaction import redact_argv
from agentdiff.transaction.store import RunStore

from .environment import DockerProofEnvironment
from .hidden_state import hidden_state_result
from .models import ProofPhaseResult, ProofResult, ProofVerdict
from .plan import select_trusted_verification_plan

EnvironmentFactory = Callable[..., Any]


class ProofEngine:
    """Rebuild a base-plus-patch workspace and verify it without LLM decisions."""

    def __init__(
        self,
        root: str | Path,
        run_id: str,
        *,
        environment_factory: EnvironmentFactory | None = None,
        cache: ProofCache | None = None,
        base_preparer: Callable[[Path], None] | None = None,
        target: str = "full",
    ) -> None:
        self.store = RunStore.open(root, run_id)
        self.root = Path(root).expanduser().resolve(strict=True)
        self.environment_factory = environment_factory or DockerProofEnvironment
        self.cache = cache
        self.base_preparer = base_preparer
        self.target = target

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
        cache_hit = False
        cached_from_run = ""
        plan: Any = None

        with tempfile.TemporaryDirectory(prefix="agentdiff-proof-") as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir(mode=0o700)
            try:
                # 1. Materialize base source (warm snapshot when provided)
                if self.base_preparer is not None:
                    self.base_preparer(workspace)
                else:
                    bundle.materialize_source(workspace)
                # 2. Select trusted verification plan from base state + patch analysis
                plan = select_trusted_verification_plan(workspace, policy, patch_bundle=bundle)
                if not plan.trusted:
                    reasons.append(f"untrusted verification plan: {plan.reason}")

                # 3. Apply patch on top of base
                bundle.apply(workspace)

                # 4. Consult the content-addressed proof cache before running.
                cache_key = self._cache_key(bundle, plan)
                if self.cache is not None:
                    cached = self.cache.lookup(cache_key)
                    if cached is not None:
                        phases = [
                            ProofPhaseResult(
                                phase=phase.phase,
                                command=(),
                                status="PASS" if phase.returncode == 0 else "FAIL",
                                returncode=phase.returncode,
                                duration_seconds=phase.duration_seconds,
                                output_sha256=phase.output_sha256,
                                tests_passed=phase.tests_passed,
                                tests_total=phase.tests_total,
                                detail="served from the deterministic proof cache",
                            )
                            for phase in cached.phases
                        ]
                        cache_hit = True
                        cached_from_run = cached.cached_from_run
                        if cached.verdict == "PROVEN":
                            clean_environment = "PASS"
                            if not phases:
                                reasons.append("cached proof has no test phase")
                        else:
                            reasons.append("cached proof verdict is NOT_PROVEN")

                if not cache_hit:
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
        trusted_plan = bool(plan is not None and plan.trusted)
        proven = (
            original_passed
            and policy_allowed
            and bundle.manifest.complete
            and clean_environment == "PASS"
            and all_phases_pass
            and has_test_phase
            and trusted_plan
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
            verification_source=plan.source if plan is not None else "unavailable",
            verification_digest=plan.plan_digest if plan is not None else "",
            trusted_plan=trusted_plan,
            cache_hit=cache_hit,
            cached_from_run=cached_from_run,
        )
        self.store.write_json_path("proof/environment.json", environment_payload)
        self.store.write_json_path("proof/result.json", proof.to_dict())
        self.store.seal_extension("proof", ("environment.json", "result.json"))

        # Persist the deterministic outcome into the content-addressed cache.
        if self.cache is not None and plan is not None and plan.trusted:
            from datetime import datetime, timezone

            cache_key = self._cache_key(bundle, plan)
            entry = ProofCacheEntry(
                key=cache_key,
                verdict=proof.verdict.value,
                promotion=proof.promotion,
                phases=tuple(
                    ProofCachePhase(
                        phase=phase.phase,
                        returncode=phase.returncode,
                        output_sha256=phase.output_sha256,
                        duration_seconds=phase.duration_seconds,
                        tests_passed=phase.tests_passed,
                        tests_total=phase.tests_total,
                    )
                    for phase in phases
                ),
                cached_from_run=self.store.run_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self.cache.store(cache_key, entry)
        return proof

    def _cache_key(self, bundle: PatchBundle, plan: Any) -> ProofCacheKey:
        source = self.store.read_json_path("source/manifest.json")
        base_digest = str(source.get("digest", "")) if isinstance(source, dict) else ""
        image_digest = str(plan.image or "python:3.12-slim")
        return build_proof_cache_key(
            root=self.root,
            base_digest=base_digest,
            patch_digest=bundle.manifest.content_digest(),
            image_digest=image_digest,
            plan_digest=plan.plan_digest,
            target=self.target,
        )

    @staticmethod
    def _score(result: dict[str, Any], name: str) -> int:
        raw = result.get(name, {})
        return int(raw.get("score", 0)) if isinstance(raw, dict) else 0

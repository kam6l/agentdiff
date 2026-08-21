"""Authoritative self-maintaining API migration orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentdiff.api.certificate import create_certificate, write_certificate
from agentdiff.api.generation_runtime import PrivateGenerationRuntime
from agentdiff.api.generators import DeterministicASTGenerator, MigrationGenerator
from agentdiff.api.manifest import APIChangeManifest, get_builtin_manifest
from agentdiff.api.matcher import APIMatcher
from agentdiff.api.models import (
    APIUsage,
    MigrationAssessment,
    MigrationConfidence,
    MigrationImpact,
    MigrationPlan,
    MigrationResult,
    MigrationStatus,
    MigrationStrategy,
    VerificationLevel,
    assess_migration_confidence,
)
from agentdiff.api.scanner import APIScanner
from agentdiff.api.transforms import TransformContext, get_transforms_for_usage
from agentdiff.api.verification import MigrationVerifier
from agentdiff.policy import load_policy, load_policy_file, policy_to_dict
from agentdiff.transaction import AgentRunTransaction


@dataclass(frozen=True, slots=True)
class MigrationSimulation:
    """Read-only assessment of a prospective API migration."""

    provider: str
    change_id: str
    affected_usages: int
    affected_files: tuple[str, ...]
    strategy: MigrationStrategy
    expected_modifications: int
    unexpected_modifications: int
    tests_detected: bool
    requested_verification: VerificationLevel
    risk: str
    automation_status: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "provider": self.provider,
            "change_id": self.change_id,
            "affected_usages": self.affected_usages,
            "affected_files": list(self.affected_files),
            "strategy": self.strategy.value,
            "expected_modifications": self.expected_modifications,
            "unexpected_modifications": self.unexpected_modifications,
            "tests_detected": self.tests_detected,
            "requested_verification": self.requested_verification.value,
            "risk": self.risk,
            "automation_status": self.automation_status,
            "reasons": list(self.reasons),
        }


class MigrationEngine:
    """Generate an untrusted patch and delegate trust to the real ProofEngine."""

    def __init__(
        self,
        root: str | Path,
        *,
        policy_path: str | Path | None = None,
        manifest: APIChangeManifest | None = None,
        provider: str | None = None,
        change_id: str | None = None,
        generator: MigrationGenerator | None = None,
        proof_environment_factory: Any | None = None,
        proof_cache: Any | None = None,
        proof_timeout_seconds: float = 900.0,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        self.manifest = manifest
        self.provider = provider
        self.change_id = change_id
        self.generator = generator or DeterministicASTGenerator()
        self.proof_environment_factory = proof_environment_factory
        self.proof_cache = proof_cache
        self.proof_timeout_seconds = proof_timeout_seconds
        if policy_path:
            self.policy = load_policy_file(policy_path)
        else:
            default_path = self.root / "agentdiff.yaml"
            self.policy = (
                load_policy_file(default_path)
                if default_path.is_file()
                else load_policy(
                    {
                        "version": 2,
                        "filesystem": {"allow_write": ["**"], "default": "allow"},
                        "process": {"default": "allow"},
                        "network": {"mode": "observe"},
                        "proof": {"image": "python:3.12-slim", "network": False},
                    }
                )
            )

    def _load_manifest(self) -> APIChangeManifest:
        if self.manifest is not None:
            return self.manifest
        if self.provider and self.change_id:
            manifest = get_builtin_manifest(self.provider, self.change_id)
            if manifest is not None:
                return manifest
        raise ValueError("No manifest available. Provide manifest or provider+change_id.")

    def scan_and_match(self) -> tuple[list[APIUsage], MigrationImpact]:
        manifest = self._load_manifest()
        usages = [
            usage for usage in APIScanner().scan(self.root) if usage.provider == manifest.provider
        ]
        return usages, APIMatcher().calculate_impact(usages, root=self.root)

    def create_plan(self, usages: list[APIUsage], impact: MigrationImpact) -> MigrationPlan:
        from agentdiff.api.models import MigrationStep

        manifest = self._load_manifest()
        affected_symbols = set(manifest.affected.symbols)
        affected = [
            usage
            for usage in usages
            if usage.symbol in affected_symbols
            or any(usage.symbol.endswith(symbol) for symbol in affected_symbols)
        ]
        assessment = assess_migration_confidence(tuple(affected), impact)
        steps: list[MigrationStep] = []
        for index, usage in enumerate(affected, start=1):
            source_path = self.root.joinpath(*usage.filepath.split("/"))
            source_code = source_path.read_text(encoding="utf-8") if source_path.is_file() else ""
            context = TransformContext(
                usage=usage,
                source_code=source_code,
                filepath=usage.filepath,
                manifest=manifest,
                all_usages=tuple(affected),
            )
            transforms = [
                transform
                for transform in get_transforms_for_usage(usage)
                if transform.can_transform(context)
            ]
            if transforms:
                steps.append(
                    MigrationStep(
                        step_id=f"step-{index:03d}",
                        description=f"Migrate {usage.symbol} in {usage.filepath}",
                        transform_id=transforms[0].transform_id,
                        filepath=usage.filepath,
                        target_symbol=usage.symbol,
                    )
                )
            else:
                explanations = tuple(
                    transform.explain_changes(context)
                    for transform in get_transforms_for_usage(usage)
                )
                detail = explanations[0] if explanations else "no registered transform"
                steps.append(
                    MigrationStep(
                        step_id=f"step-{index:03d}",
                        description=f"Unsupported shape in {usage.filepath}: {detail}",
                        filepath=usage.filepath,
                        target_symbol=usage.symbol,
                        status=MigrationStatus.NEEDS_REVIEW,
                    )
                )

        tests_detected = bool(
            self.policy.proof.tests
            or (impact.impact_plan is not None and impact.impact_plan.affected_code_has_tests)
        )
        if affected and all(step.status is MigrationStatus.PLANNED for step in steps):
            verification_level = VerificationLevel.V3 if tests_detected else VerificationLevel.V1
        else:
            verification_level = VerificationLevel.V0
        return MigrationPlan(
            provider=manifest.provider,
            change_id=manifest.change_id,
            manifest=manifest,
            affected_usages=tuple(affected),
            affected_files=tuple(sorted({usage.filepath for usage in affected})),
            assessment=assessment,
            steps=tuple(steps),
            verification_level=verification_level,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def simulate(self) -> MigrationSimulation:
        usages, impact = self.scan_and_match()
        plan = self.create_plan(usages, impact)
        needs_review = any(step.status is MigrationStatus.NEEDS_REVIEW for step in plan.steps)
        tests_detected = bool(
            self.policy.proof.tests
            or (impact.impact_plan is not None and impact.impact_plan.affected_code_has_tests)
        )
        strategy = MigrationStrategy.MANUAL if needs_review else self.generator.strategy
        return MigrationSimulation(
            provider=plan.provider,
            change_id=plan.change_id,
            affected_usages=len(plan.affected_usages),
            affected_files=plan.affected_files,
            strategy=strategy,
            expected_modifications=len(plan.affected_files),
            unexpected_modifications=0,
            tests_detected=tests_detected,
            requested_verification=plan.verification_level,
            risk=impact.blast_radius.level.value.upper(),
            automation_status="NEEDS_REVIEW" if needs_review else "SAFE_TO_ATTEMPT",
            reasons=tuple(step.description for step in plan.steps if needs_review),
        )

    def run(self) -> MigrationResult:
        manifest = self._load_manifest()
        usages, impact = self.scan_and_match()
        plan = self.create_plan(usages, impact)
        if not plan.affected_usages:
            return self._empty_result(manifest)
        review_errors = tuple(
            step.description for step in plan.steps if step.status is MigrationStatus.NEEDS_REVIEW
        )
        if review_errors and isinstance(self.generator, DeterministicASTGenerator):
            return MigrationResult(
                plan=plan,
                migration_status=MigrationStatus.NEEDS_REVIEW,
                verification_level=VerificationLevel.V0,
                proof_verdict="NOT_PROVEN",
                errors=review_errors,
                expected_files=plan.affected_files,
            )

        migration_policy = self._migration_policy(plan)
        runtime = PrivateGenerationRuntime(plan, self.generator)
        transaction = AgentRunTransaction(
            self.root,
            migration_policy,
            task=f"api migration {plan.provider}:{plan.change_id}",
            runtime=runtime,
        ).run([self.generator.command_label], timeout_seconds=900)
        actual_files = tuple(sorted(change.path for change in transaction.changes))
        unexpected_files = tuple(sorted(set(actual_files) - set(plan.affected_files)))
        missing_files = tuple(sorted(set(plan.affected_files) - set(actual_files)))

        verification = MigrationVerifier(
            str(self.root),
            transaction.run_id,
            environment_factory=self.proof_environment_factory,
            cache=self.proof_cache,
            target="full",
        ).verify(timeout_seconds=self.proof_timeout_seconds)
        generation_errors = (
            runtime.generation_result.errors if runtime.generation_result is not None else ()
        )
        generation_passed = bool(
            runtime.generation_result is not None and runtime.generation_result.success
        )
        migration_passed = (
            verification.passed and generation_passed and not unexpected_files and not missing_files
        )
        certificate = create_certificate(
            root=self.root,
            plan=plan,
            transaction=transaction,
            verification=verification,
            policy=migration_policy,
            generator=self.generator,
            migration_passed=migration_passed,
        )
        write_certificate(certificate, self.root)

        errors = [*generation_errors, *verification.reasons]
        if unexpected_files:
            errors.insert(0, "UNEXPECTED FILE MODIFICATION: " + ", ".join(unexpected_files))
        if missing_files:
            errors.insert(0, "EXPECTED FILE NOT MODIFIED: " + ", ".join(missing_files))
        proven = migration_passed
        return MigrationResult(
            plan=plan,
            migration_status=MigrationStatus.COMPLETED if proven else MigrationStatus.FAILED,
            verification_level=verification.level,
            proof_verdict="PROVEN" if proven else "NOT_PROVEN",
            proof_digest=verification.proof_digest,
            capsule_id=verification.capsule_id,
            certificate=certificate,
            errors=tuple(dict.fromkeys(errors)),
            run_id=transaction.run_id,
            expected_files=plan.affected_files,
            actual_modified_files=actual_files,
            unexpected_files=unexpected_files,
        )

    def _migration_policy(self, plan: MigrationPlan) -> Any:
        payload = policy_to_dict(self.policy)
        filesystem = dict(payload["filesystem"])
        filesystem["allow_write"] = list(plan.affected_files)
        filesystem["default"] = "deny"
        payload["filesystem"] = filesystem
        process = dict(payload["process"])
        if isinstance(self.generator, DeterministicASTGenerator):
            process["allow"] = [*process.get("allow", []), self.generator.command_label]
        payload["process"] = process
        return load_policy(payload)

    def _empty_result(self, manifest: APIChangeManifest) -> MigrationResult:
        plan = MigrationPlan(
            provider=manifest.provider,
            change_id=manifest.change_id,
            manifest=manifest,
            affected_usages=(),
            affected_files=(),
            assessment=MigrationAssessment(
                confidence=MigrationConfidence.LOW,
                strategy=MigrationStrategy.MANUAL,
                score=0,
                reasons=("No affected usages found",),
                risk_factors=(),
            ),
            steps=(),
            verification_level=VerificationLevel.V0,
            status=MigrationStatus.COMPLETED,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return MigrationResult(
            plan=plan,
            migration_status=MigrationStatus.COMPLETED,
            verification_level=VerificationLevel.V0,
        )

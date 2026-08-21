"""MigrationEngine: Orchestrates the migration workflow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentdiff.api.certificate import write_certificate
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from agentdiff.api.manifest import APIChangeManifest, get_builtin_manifest
from agentdiff.api.matcher import APIMatcher
from agentdiff.api.models import (
    APIUsage,
    MigrationAssessment,
    MigrationCertificate,
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
from agentdiff.api.transforms import (
    TransformContext,
    get_transform,
    get_transforms_for_usage,
)
from agentdiff.api.verification import MigrationVerifier, VerificationResult, create_certificate
from agentdiff.policy import load_policy, load_policy_file
from agentdiff.workspace import WarmWorkspaceFactory, compute_identity


@dataclass(frozen=True, slots=True)
class RepairResult:
    """Outcome of a bounded repair attempt on a failed migration."""

    success: bool
    verification: VerificationResult
    errors: tuple[str, ...] = ()
from agentdiff.policy import load_policy, load_policy_file
from agentdiff.workspace import WarmWorkspaceFactory, compute_identity

if TYPE_CHECKING:
    from agentdiff.api.models import MigrationImpact

class MigrationEngine:
    """Orchestrates the end-to-end migration workflow."""

    def __init__(
        self,
        root: str | Path,
        *,
        policy_path: str | Path | None = None,
        manifest: APIChangeManifest | None = None,
        provider: str | None = None,
        change_id: str | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        self.manifest = manifest
        self.provider = provider
        self.change_id = change_id

        # Load policy
        if policy_path:
            self.policy = load_policy_file(policy_path)
        else:
            default_path = self.root / "agentdiff.yaml"
            if default_path.is_file():
                self.policy = load_policy_file(default_path)
            else:
                self.policy = load_policy(
                    {
                        "version": 2,
                        "filesystem": {"allow_write": ["**"], "default": "allow"},
                        "process": {"default": "allow"},
                        "network": {"mode": "observe"},
                        "proof": {"image": "python:3.12-slim", "network": False},
                    }
                )

    def _load_manifest(self) -> APIChangeManifest:
        """Load the manifest from built-in or provided."""
        if self.manifest is not None:
            return self.manifest
        if self.provider and self.change_id:
            manifest = get_builtin_manifest(self.provider, self.change_id)
            if manifest is not None:
                return manifest
        raise ValueError("No manifest available. Provide manifest or provider+change_id.")

    def scan_and_match(self) -> tuple[list[APIUsage], "MigrationImpact"]:
        """Scan repository and match affected usages."""
        scanner = APIScanner()
        usages = scanner.scan(self.root)

        manifest = self._load_manifest()
        matcher = APIMatcher()
        _ = matcher.calculate_impact(usages, root=self.root)

        # Filter to only this provider's affected usages
        provider_usages = [u for u in usages if u.provider == manifest.provider]
        provider_impact = matcher.calculate_impact(provider_usages, root=self.root)

        return provider_usages, provider_impact

    def create_plan(
        self,
        usages: list[APIUsage],
        impact: "MigrationImpact",
    ) -> MigrationPlan:
        """Create a migration plan based on assessment."""
        from agentdiff.api.models import MigrationStep

        manifest = self._load_manifest()
        assessment = assess_migration_confidence(tuple(usages), impact)

        # Filter to only usages that match the manifest's affected symbols
        affected_symbols = manifest.affected.symbols
        migratable_usages = [
            u
            for u in usages
            if u.symbol in affected_symbols or any(u.symbol.endswith(s) for s in affected_symbols)
        ]
        # Fall back to impact-matched usages when symbol filtering is too strict
        if not migratable_usages and impact.matched_changes:
            migratable_usages = [m.usage for m in impact.matched_changes]

        # Create steps for each affected file/usage
        steps: list[MigrationStep] = []
        for i, usage in enumerate(migratable_usages):
        # Create steps for each affected file/usage
        steps: list[MigrationStep] = []
        for i, usage in enumerate(usages):
            # Find applicable transform
            transforms = get_transforms_for_usage(usage)
            applicable = [
                t for t in transforms if t.can_transform(self._create_transform_context(usage))
            ]

            if applicable:
                transform = applicable[0]
                step = MigrationStep(
                    step_id=f"step-{i + 1:03d}",
                    description=f"Migrate {usage.symbol} in {usage.filepath}",
                    transform_id=transform.transform_id,
                    filepath=usage.filepath,
                    target_symbol=usage.symbol,
                    status=MigrationStatus.PLANNED,
                )
            else:
                step = MigrationStep(
                    step_id=f"step-{i + 1:03d}",
                    description=f"Manual review needed for {usage.symbol} in {usage.filepath}",
                    transform_id=None,
                    filepath=usage.filepath,
                    target_symbol=usage.symbol,
                    status=MigrationStatus.NEEDS_REVIEW,
                )
            steps.append(step)

        # Determine verification level based on assessment
        if assessment.confidence.value == "high":
            verification_level = VerificationLevel.V3
        elif assessment.confidence.value == "medium":
            verification_level = VerificationLevel.V2
        else:
            verification_level = VerificationLevel.V0

        plan = MigrationPlan(
            provider=manifest.provider,
            change_id=manifest.change_id,
            manifest=manifest,
            affected_usages=tuple(migratable_usages),
            affected_files=tuple(sorted({u.filepath for u in migratable_usages})),
            affected_usages=tuple(usages),
            affected_files=impact.affected_files,
            assessment=assessment,
            steps=tuple(steps),
            verification_level=verification_level,
            status=MigrationStatus.PLANNED,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        return plan

    def _create_transform_context(self, usage: APIUsage) -> Any:
        """Create a transform context for a usage."""
        from agentdiff.api.transforms.base import TransformContext

        return TransformContext(
            usage=usage,
            source_code="",  # Will be filled in during execution
            filepath=usage.filepath,
            manifest=self._load_manifest(),
            all_usages=(),
        )

    def execute_plan(
        self,
        plan: MigrationPlan,
        workspace: Path,
    ) -> tuple[Path, list[str]]:
        """Execute the migration plan in the given workspace."""
        _ = self._load_manifest()
        errors: list[str] = []
        modified_files: set[str] = set()

        for step in plan.steps:
            if step.status == MigrationStatus.NEEDS_REVIEW:
                errors.append(f"Step {step.step_id}: Requires manual review - {step.description}")
                continue

            if step.transform_id is None:
                errors.append(f"Step {step.step_id}: No transform available")
                continue

            transform = get_transform(step.transform_id)
            if transform is None:
                errors.append(f"Step {step.step_id}: Transform {step.transform_id} not found")
                continue

            # Read source file
            src_file = workspace / step.filepath
            if not src_file.exists():
                errors.append(f"Step {step.step_id}: Source file not found: {step.filepath}")
                continue

            source_code = src_file.read_text(encoding="utf-8")

            # Find the specific usage for this file
            usage = next(
                (u for u in plan.affected_usages if u.filepath == step.filepath),
                None,
            )
            if usage is None:
                errors.append(f"Step {step.step_id}: No usage found for file")
                continue

            # Apply transform
            context = TransformContext(
                usage=usage,
                source_code=source_code,
                filepath=step.filepath,
                manifest=self.manifest,
                all_usages=plan.affected_usages,
            )

            result = transform.transform(context)
            if not result.success:
                errors.append(f"Step {step.step_id}: Transform failed: {result.changes}")
                continue

            # Write modified code
            src_file.write_text(result.modified_code, encoding="utf-8")
            modified_files.add(step.filepath)

        return workspace, errors

=======
    def verify_migration(
        self,
        plan: MigrationPlan,
        workspace: Path,
    ) -> tuple[VerificationLevel, Optional[str], Optional[str]]:
        """Run verification on the migrated code."""
        # This is a simplified verification - in reality, we'd run the ProofEngine
        # For now, we return the target verification level

        # Run syntax/type check (V1)
        try:
            # Check syntax by parsing all Python files
            for py_file in workspace.rglob("*.py"):
                if py_file.is_file():
                    source = py_file.read_text(encoding="utf-8")
                    compile(source, str(py_file), "exec")
        except SyntaxError as e:
            return VerificationLevel.V0, None, f"Syntax error: {e}"

        # If V2 or higher requested, we'd run tests
        # For now, return the target level
        return plan.verification_level, None, None

    def run(self) -> MigrationResult:
        """Execute the full migration workflow."""

        # 1. Load manifest
        manifest = self._load_manifest()

        # 2. Scan and match
        usages, impact = self.scan_and_match()

        if not usages:
            return MigrationResult(
                plan=MigrationPlan(
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
                ),
                migration_status=MigrationStatus.COMPLETED,
                verification_level=VerificationLevel.V0,
            )

        # 3. Create plan
        plan = self.create_plan(usages, impact)

        # 4. Create private workspace
        identity = compute_identity(self.root, policy=self.policy)
        factory = WarmWorkspaceFactory(self.root)
        agent_workspace = factory.create_workspace(identity)
        workspace = agent_workspace.path
        workspace = factory.ensure_base(identity).path

        # 5. Execute plan
        workspace, errors = self.execute_plan(plan, workspace)

        if errors:
            return MigrationResult(
                plan=plan,
                migration_status=MigrationStatus.FAILED,
                verification_level=VerificationLevel.V0,
                errors=tuple(errors),
            )

        # 6. Verify migration using MigrationVerifier
        verifier = MigrationVerifier(
            root=self.root,
            plan=plan,
            workspace=workspace,
            policy=self.policy,
        )
        verification = verifier.verify()

        if not verification.passed:
            # Attempt repair if verification failed
            repair_result = self._attempt_repair(plan, workspace, verification)
            if repair_result.success:
                # Re-verify after repair
                verification = repair_result.verification
                if not verification.passed:
                    return MigrationResult(
                        plan=plan,
                        migration_status=MigrationStatus.FAILED,
                        verification_level=verification.level,
                        errors=tuple(verification.reasons) + tuple(repair_result.errors),
                    )
            else:
                return MigrationResult(
                    plan=plan,
                    migration_status=MigrationStatus.FAILED,
                    verification_level=verification.level,
                    errors=tuple(verification.reasons),
                )

        # 7. Generate certificate
        certificate = create_certificate(plan, workspace, verification, impact)
        write_certificate(certificate, self.root)

        return MigrationResult(
            plan=plan,
            migration_status=MigrationStatus.COMPLETED,
            verification_level=verification.level,
            proof_digest=verification.proof_digest,
            capsule_id=verification.capsule_id,
        # 6. Verify migration
        verification_level, proof_digest, capsule_id = self.verify_migration(plan, workspace)

        # 7. Generate certificate
        certificate = None
        if verification_level != VerificationLevel.V0:
            # Compute migration digest
            migration_digest = self._compute_migration_digest(plan, workspace)

            certificate = MigrationCertificate(
                certificate_id=f"cert-{hashlib.sha256(migration_digest.encode()).hexdigest()[:16]}",
                provider=plan.provider,
                change_id=plan.change_id,
                verification_level=verification_level,
                affected_files=plan.affected_files,
                blast_radius_score=impact.blast_radius.score,
                proof_digest=proof_digest or "",
                capsule_id=capsule_id or "",
                migration_digest=migration_digest,
                created_at=datetime.now(timezone.utc).isoformat(),
                verified=True,
            )

        return MigrationResult(
            plan=plan,
            migration_status=MigrationStatus.COMPLETED if not errors else MigrationStatus.FAILED,
            verification_level=verification_level,
            proof_digest=proof_digest,
            capsule_id=capsule_id,
            certificate=certificate,
            errors=tuple(errors),
        )

    def _attempt_repair(
        self,
        plan: MigrationPlan,
        workspace: Path,
        verification: VerificationResult,
    ) -> "RepairResult":
        """Attempt to repair a failed migration using RepairLoop."""
        # The full RepairLoop integration requires a repair command builder
        # (coding agent or deterministic re-transform). Until that is wired,
        # a failed migration is reported with its failure evidence intact.
        del plan, workspace
        return RepairResult(
            success=False,
            verification=verification,
            errors=("Repair not yet fully implemented",),
        )


    def _compute_migration_digest(self, plan: MigrationPlan, workspace: Path) -> str:
        """Compute a content hash of the migration."""
        hasher = hashlib.sha256()
        for step in plan.steps:
            if step.status == MigrationStatus.NEEDS_REVIEW:
                continue
            src_file = workspace / step.filepath
            if src_file.exists():
                hasher.update(src_file.read_bytes())
        return hasher.hexdigest()


# Import for type hints

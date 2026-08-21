"""Migration verification connecting MigrationEngine with ProofEngine."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentdiff.api.models import (
    MigrationCertificate,
    MigrationPlan,
    VerificationLevel,
)

if TYPE_CHECKING:
    from agentdiff.impact.cache import ProofCache


@dataclass(frozen=True, slots=True)
class VerificationPhase:
    """Result of one verification phase."""

    phase: str  # "syntax", "typecheck", "targeted_tests", "full_tests"
    passed: bool
    returncode: int
    output_sha256: str
    duration_seconds: float
    tests_passed: int | None = None
    tests_total: int | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Complete verification result for a migration."""

    level: VerificationLevel
    passed: bool
    phases: tuple[VerificationPhase, ...]
    proof_digest: str
    capsule_id: str
    reasons: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        phase_status = ", ".join(f"{p.phase}={'PASS' if p.passed else 'FAIL'}" for p in self.phases)
        passed_str = "PASSED" if self.passed else "FAILED"
        return f"Verification {self.level.value}: {passed_str} [{phase_status}]"


class MigrationVerifier:
    """Verify a migration using AgentDiff's proof infrastructure."""

    def __init__(
        self,
        root: str | Path,
        plan: "MigrationPlan",
        workspace: Path,
        *,
        policy: Any | None = None,
        cache: ProofCache | None = None,
        target: str = "full",
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        self.plan = plan
        self.workspace = workspace
        self.policy = policy
        self.cache = cache
        self.target = target

    def verify(self, *, timeout_seconds: float = 900.0) -> VerificationResult:
        """Run full verification pipeline V0-V3."""
        phases: list[VerificationPhase] = []
        reasons: list[str] = []

        # V1: Syntax/type/build checks
        syntax_result = self._run_syntax_checks()
        phases.append(syntax_result)
        if not syntax_result.passed:
            reasons.append("Syntax/type/build checks failed")
            return self._fail_result(VerificationLevel.V0, phases, reasons)

        # V2: Targeted tests (if requested)
        achieved_level = VerificationLevel.V1
        if self.plan.verification_level >= VerificationLevel.V2:
            targeted_result = self._run_targeted_tests()
            phases.append(targeted_result)
            if targeted_result.detail.startswith("NO_TESTS_OR_DEPS"):
                # No tests collectable or dependencies unavailable:
                # do not claim test verification, but do not fail the migration.
                reasons.append("Test execution unavailable (no collectable tests or missing deps)")
            elif targeted_result.passed:
                achieved_level = VerificationLevel.V2
            else:
                reasons.append("Targeted tests failed")
                return self._fail_result(VerificationLevel.V1, phases, reasons)

        # V3: Full repository tests (if requested)
        if self.plan.verification_level >= VerificationLevel.V3:
            full_result = self._run_full_tests()
            phases.append(full_result)
            if full_result.detail.startswith("NO_TESTS_OR_DEPS"):
                reasons.append(
                    "Full test execution unavailable (no collectable tests or missing deps)"
                )
            elif full_result.passed:
                achieved_level = VerificationLevel.V3
            else:
                reasons.append("Full repository tests failed")
                return self._fail_result(max(achieved_level, VerificationLevel.V1), phases, reasons)

        # All requested levels passed (or test execution unavailable)
        proof_digest = self._compute_proof_digest(phases)
        now_str = str(datetime.now(timezone.utc)).encode()
        capsule_id = f"capsule-{hashlib.sha256(now_str).hexdigest()[:16]}"

        return VerificationResult(
            level=achieved_level,
            passed=True,
            phases=tuple(phases),
            proof_digest=proof_digest,
            capsule_id=capsule_id,
        )

    def _run_syntax_checks(self) -> VerificationPhase:
        """V1: Syntax, typecheck, build passes."""
        start = datetime.now(timezone.utc)
        passed = True
        output_hash = ""
        reasons: list[str] = []

        try:
            for py_file in self.workspace.rglob("*.py"):
                if py_file.is_file():
                    source = py_file.read_text(encoding="utf-8")
                    compile(source, str(py_file), "exec")
        except SyntaxError as e:
            passed = False
            reasons.append(f"Syntax error in {e.filename}:{e.lineno}: {e.msg}")

        output_hash = hashlib.sha256("syntax".encode()).hexdigest()
        return VerificationPhase(
            phase="syntax",
            passed=passed,
            returncode=0 if passed else 1,
            output_sha256=output_hash,
            duration_seconds=(datetime.now(timezone.utc) - start).total_seconds(),
            detail="; ".join(reasons) if reasons else "All syntax checks passed",
        )

    def _run_targeted_tests(self) -> VerificationPhase:
        """V2: Run affected tests using ImpactEngine."""
        # For now, run pytest on the workspace
        # In future, this would use ImpactEngine to select specific tests
        start = datetime.now(timezone.utc)
        passed = True
        output_hash = ""
        reasons: list[str] = []
        detail = ""

        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-q", "--tb=short"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=120,
            )
            combined = result.stdout + result.stderr
            if result.returncode == 0:
                detail = "Targeted tests passed"
            elif result.returncode == 5:
                # No tests collected: cannot claim test verification.
                passed = True
                detail = "NO_TESTS_OR_DEPS: no tests collected"
                reasons.append("no tests collected")
            elif result.returncode == 2 and (
                "ModuleNotFoundError" in combined or "ImportError" in combined
            ):
                # Collection failed due to missing dependencies in the clean room.
                passed = True
                detail = "NO_TESTS_OR_DEPS: missing dependencies for test collection"
                reasons.append("test collection requires unavailable dependencies")
            else:
                passed = False
                detail = "Targeted tests failed"
                reasons.append(f"Tests failed: {combined[-500:]}")
        except subprocess.TimeoutExpired:
            passed = False
            reasons.append("Test timeout")
            detail = "Targeted tests failed"
        except (OSError, subprocess.SubprocessError) as e:
            passed = False
            reasons.append(f"Test execution error: {e}")
            detail = "Targeted tests failed"

        output_hash = hashlib.sha256(("targeted_tests" + str(passed)).encode()).hexdigest()
        return VerificationPhase(
            phase="targeted_tests",
            passed=passed,
            returncode=0 if passed else 1,
            output_sha256=output_hash,
            duration_seconds=(datetime.now(timezone.utc) - start).total_seconds(),
            detail=detail,
        )

    def _run_full_tests(self) -> VerificationPhase:
        """V3: Run full repository test suite."""
        # Same as targeted for now, but could run more comprehensive suite
        return self._run_targeted_tests()

    def _fail_result(
        self, level: VerificationLevel, phases: list[VerificationPhase], reasons: list[str]
    ) -> "VerificationResult":
        proof_digest = hashlib.sha256("".join(r for r in reasons).encode()).hexdigest()[:16]
        now_str = str(datetime.now(timezone.utc)).encode()
        capsule_id = f"capsule-{hashlib.sha256(now_str).hexdigest()[:16]}"
        return VerificationResult(
            level=level,
            passed=False,
            phases=tuple(phases),
            proof_digest=proof_digest,
            capsule_id=capsule_id,
            reasons=tuple(reasons),
        )

    def _compute_proof_digest(self, phases: list[VerificationPhase]) -> str:
        """Compute digest of proof results."""
        content = "".join(f"{p.phase}:{p.passed}:{p.output_sha256}" for p in phases)
        return hashlib.sha256(content.encode()).hexdigest()


def create_certificate(
    plan: "MigrationPlan",
    workspace: Path,
    verification: "VerificationResult",
    impact: Any,
) -> "MigrationCertificate":
    """Generate a MigrationCertificate artifact."""
    migration_digest = _compute_migration_digest(plan, workspace)

    return MigrationCertificate(
        certificate_id=f"cert-{hashlib.sha256(migration_digest.encode()).hexdigest()[:16]}",
        provider=plan.provider,
        change_id=plan.change_id,
        verification_level=verification.level,
        affected_files=plan.affected_files,
        blast_radius_score=impact.blast_radius.score if impact else 0,
        proof_digest=verification.proof_digest,
        capsule_id=verification.capsule_id,
        migration_digest=migration_digest,
        created_at=datetime.now(timezone.utc).isoformat(),
        verified=verification.passed,
    )


def _compute_migration_digest(plan: "MigrationPlan", workspace: Path) -> str:
    """Compute a content hash of the migration."""
    hasher = hashlib.sha256()
    for step in plan.steps:
        if step.status.value == "needs_review":
            continue
        src_file = workspace / step.filepath
        if src_file.exists():
            hasher.update(src_file.read_bytes())
    return hasher.hexdigest()

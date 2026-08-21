"""Canonical migration certificate creation, storage, and verification."""

from __future__ import annotations

import json
import subprocess  # nosec B404 -- exact git argv only
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentdiff.api.models import MigrationCertificate
from agentdiff.api.verification import canonical_sha256
from agentdiff.api.version_detector import detect_installed_sdk_versions
from agentdiff.policy import policy_to_dict
from agentdiff.transaction.store import RunStore

if TYPE_CHECKING:
    from agentdiff.api.generators import MigrationGenerator
    from agentdiff.api.models import MigrationPlan
    from agentdiff.api.verification import VerificationResult
    from agentdiff.policy import Policy
    from agentdiff.transaction import TransactionResult

CERTIFICATE_DIR = ".agentdiff/certificates"


class CertificateStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    MISMATCH = "MISMATCH"


def _canonical_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in data.items() if key not in {"integrity_sha256", "written_at"}
    }


def _integrity(data: dict[str, Any]) -> str:
    return canonical_sha256(_canonical_payload(data))


def _git_head(root: Path) -> str:
    if not (root / ".git").exists():
        return ""
    try:
        completed = subprocess.run(  # nosec B603
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _phase_result(verification: VerificationResult, phase_name: str) -> str:
    matching = [phase for phase in verification.phases if phase.phase == phase_name]
    if not matching:
        return "NOT_RUN"
    return "PASS" if all(phase.passed for phase in matching) else "FAIL"


def create_certificate(
    *,
    root: str | Path,
    plan: MigrationPlan,
    transaction: TransactionResult,
    verification: VerificationResult,
    policy: Policy,
    generator: MigrationGenerator,
    migration_passed: bool | None = None,
) -> MigrationCertificate:
    """Bind an exact patch, base, policy, proof, and verification plan."""

    root_path = Path(root).expanduser().resolve(strict=True)
    store = RunStore.open(root_path, transaction.run_id)
    source = store.read_json_path("source/manifest.json")
    source_digest = str(source.get("digest", "")) if isinstance(source, dict) else ""
    actual_files = tuple(sorted(change.path for change in transaction.changes))
    expected_files = tuple(sorted(plan.affected_files))
    unexpected_files = tuple(sorted(set(actual_files) - set(expected_files)))
    versions = detect_installed_sdk_versions(root_path)
    sdk = versions.get(plan.provider)
    upstream = plan.manifest.source
    upstream_payload = {
        "type": upstream.type.value,
        "url": upstream.url,
        "retrieved_at": upstream.retrieved_at,
        "version": upstream.version,
    }
    policy_digest = canonical_sha256(policy_to_dict(policy))
    proof_passed = verification.proof.verdict.value == "PROVEN"
    final_verdict = "PROVEN" if proof_passed and migration_passed is not False else "NOT_PROVEN"
    certificate = MigrationCertificate(
        certificate_id="",
        provider=plan.provider,
        change_id=plan.change_id,
        verification_level=verification.level,
        affected_files=actual_files,
        blast_radius_score=transaction.blast_radius.score,
        proof_digest=verification.proof_digest,
        capsule_id=transaction.run_id,
        migration_digest=verification.proof.patch_digest,
        created_at=str(store.read_json("metadata.json").get("created_at", "")),
        verified=final_verdict == "PROVEN",
        final_verdict=final_verdict,
        upstream_source=upstream.url,
        upstream_source_digest=canonical_sha256(upstream_payload),
        repository_base_sha=_git_head(root_path),
        repository_base_digest=source_digest,
        sdk_package=sdk.library if sdk else plan.provider,
        sdk_version=(sdk.exact_version or sdk.version_specifier or "") if sdk else "",
        affected_symbols=tuple(sorted({usage.symbol for usage in plan.affected_usages})),
        affected_usages=len(plan.affected_usages),
        expected_files=expected_files,
        actual_modified_files=actual_files,
        unexpected_files=unexpected_files,
        migration_generator=generator.name,
        migration_strategy=generator.strategy.value,
        policy_result=transaction.safety_outcome.value.upper(),
        policy_digest=policy_digest,
        blast_radius_level=transaction.blast_radius.level.value.upper(),
        verification_requested=plan.verification_level,
        build_result=_phase_result(verification, "build"),
        affected_test_result="NOT_RUN",
        full_test_result=_phase_result(verification, "tests"),
    )
    provisional = certificate.to_dict()
    provisional.pop("certificate_id", None)
    provisional.pop("integrity_sha256", None)
    certificate = replace(certificate, certificate_id=f"cert-{canonical_sha256(provisional)[:16]}")
    return replace(certificate, integrity_sha256=_integrity(certificate.to_dict()))


def write_certificate(certificate: MigrationCertificate, root: str | Path) -> Path:
    """Write a sealed certificate below ``.agentdiff/certificates``."""

    root_path = Path(root).expanduser().resolve(strict=True)
    cert_dir = root_path / CERTIFICATE_DIR
    cert_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cert_path = cert_dir / f"{certificate.certificate_id}.json"
    data = certificate.to_dict()
    if not certificate.integrity_sha256 or certificate.integrity_sha256 != _integrity(data):
        raise ValueError("certificate integrity digest is missing or invalid")
    cert_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return cert_path


def write_certificate_legacy(certificate: MigrationCertificate, path: str | Path) -> Path:
    """Write a sealed certificate to an explicit path."""

    candidate = Path(path).expanduser().resolve()
    candidate.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = certificate.to_dict()
    if certificate.integrity_sha256 != _integrity(data):
        raise ValueError("certificate integrity digest is invalid")
    candidate.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return candidate


def read_certificate(path: str | Path) -> dict[str, Any]:
    candidate = Path(path).expanduser().resolve(strict=True)
    data = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("certificate root must be an object")
    return data


def verify_certificate(
    path: str | Path,
    *,
    root: str | Path | None = None,
) -> tuple[CertificateStatus, str]:
    """Verify certificate integrity, evidence binding, and optional repository freshness."""

    try:
        data = read_certificate(path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        return CertificateStatus.INVALID, f"unreadable certificate: {type(error).__name__}"
    if data.get("schema_version") != 1:
        return CertificateStatus.INVALID, "unsupported certificate schema"
    recorded_integrity = str(data.get("integrity_sha256", ""))
    if not recorded_integrity or recorded_integrity != _integrity(data):
        return CertificateStatus.INVALID, "certificate integrity digest mismatch"
    if root is None:
        return CertificateStatus.VALID, "certificate integrity is valid"

    root_path = Path(root).expanduser().resolve(strict=True)
    run_id = str(data.get("capsule_id", ""))
    try:
        store = RunStore.open(root_path, run_id)
        integrity = store.verify_integrity()
    except (OSError, ValueError, TypeError):
        return CertificateStatus.MISMATCH, "evidence capsule is missing"
    if not integrity.ok:
        return CertificateStatus.MISMATCH, "evidence capsule integrity failed"
    mutation = store.read_json_path("mutations/manifest.json")
    if not isinstance(mutation, dict) or mutation.get("digest") != data.get("migration_digest"):
        return CertificateStatus.MISMATCH, "patch digest does not match sealed evidence"
    proof = store.read_json_path("proof/result.json")
    if not isinstance(proof, dict) or canonical_sha256(proof) != data.get("proof_digest"):
        return CertificateStatus.MISMATCH, "proof digest does not match sealed evidence"
    base_sha = str(data.get("repository_base_sha", ""))
    if base_sha and _git_head(root_path) != base_sha:
        return CertificateStatus.STALE, "repository HEAD changed after verification"
    return CertificateStatus.VALID, "certificate and evidence bindings are valid"


def list_certificates(root: str | Path) -> list[Path]:
    root_path = Path(root).expanduser().resolve(strict=True)
    cert_dir = root_path / CERTIFICATE_DIR
    return sorted(cert_dir.glob("*.json")) if cert_dir.is_dir() else []


def get_latest_certificate(root: str | Path, provider: str, change_id: str) -> Path | None:
    matching: list[Path] = []
    for certificate in list_certificates(root):
        try:
            data = read_certificate(certificate)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if data.get("provider") == provider and data.get("change_id") == change_id:
            matching.append(certificate)
    return matching[-1] if matching else None

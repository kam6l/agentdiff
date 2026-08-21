"""Organization-wide API change campaigns backed by per-repository proof."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import yaml

from agentdiff.api.certificate import CertificateStatus, verify_certificate
from agentdiff.api.manifest import APIChangeManifest, get_builtin_manifest
from agentdiff.api.migrate import MigrationEngine, MigrationSimulation
from agentdiff.api.models import MigrationResult, MigrationStatus

if TYPE_CHECKING:
    from agentdiff.api.generators import MigrationGenerator


_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_MAX_REPOSITORIES = 100
_MAX_CONFIG_BYTES = 1_000_000
_MAX_REPORT_BYTES = 5_000_000


@dataclass(frozen=True, slots=True)
class FleetRepository:
    """One explicit local repository in a verified campaign."""

    name: str
    path: Path
    display_path: str


@dataclass(frozen=True, slots=True)
class FleetConfig:
    """Validated, data-only campaign configuration."""

    campaign: str
    provider: str
    change_id: str
    repositories: tuple[FleetRepository, ...]
    config_path: Path
    manifest_path: Path | None = None
    schema_version: int = 1

    @classmethod
    def load(cls, path: str | Path) -> FleetConfig:
        unresolved_config = Path(path).expanduser()
        if unresolved_config.is_symlink():
            raise ValueError("fleet config must be a regular, non-symlink file")
        config_path = unresolved_config.resolve(strict=True)
        if not config_path.is_file():
            raise ValueError("fleet config must be a regular, non-symlink file")
        if config_path.stat().st_size > _MAX_CONFIG_BYTES:
            raise ValueError("fleet config exceeds the 1 MB limit")
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("fleet config must be a YAML/JSON object")
        if payload.get("version") != 1:
            raise ValueError("fleet config version must be 1")

        campaign = _validated_name(payload.get("campaign"), field="campaign")
        provider = _validated_name(payload.get("provider"), field="provider")
        change_id = _validated_name(payload.get("change"), field="change")
        raw_repositories = payload.get("repositories")
        if not isinstance(raw_repositories, list) or not raw_repositories:
            raise ValueError("fleet config repositories must be a non-empty list")
        if len(raw_repositories) > _MAX_REPOSITORIES:
            raise ValueError(f"fleet config supports at most {_MAX_REPOSITORIES} repositories")

        repositories: list[FleetRepository] = []
        names: set[str] = set()
        roots: set[Path] = set()
        for raw_repository in raw_repositories:
            if not isinstance(raw_repository, dict):
                raise ValueError("each fleet repository must be an object")
            name = _validated_name(raw_repository.get("name"), field="repository name")
            raw_path = raw_repository.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError(f"repository {name!r} requires a path")
            unresolved = Path(raw_path).expanduser()
            if not unresolved.is_absolute():
                unresolved = config_path.parent / unresolved
            if unresolved.is_symlink():
                raise ValueError(f"repository {name!r} path cannot be a symlink")
            root = unresolved.resolve(strict=True)
            if not root.is_dir():
                raise ValueError(f"repository {name!r} path must be a directory")
            if name in names:
                raise ValueError(f"duplicate fleet repository name: {name}")
            if root in roots:
                raise ValueError(f"duplicate fleet repository path: {raw_path}")
            names.add(name)
            roots.add(root)
            repositories.append(
                FleetRepository(name=name, path=root, display_path=raw_path.strip())
            )

        manifest_path: Path | None = None
        raw_manifest = payload.get("manifest")
        if raw_manifest is not None:
            if not isinstance(raw_manifest, str) or not raw_manifest.strip():
                raise ValueError("fleet manifest must be a non-empty path")
            unresolved_manifest = Path(raw_manifest).expanduser()
            if not unresolved_manifest.is_absolute():
                unresolved_manifest = config_path.parent / unresolved_manifest
            if unresolved_manifest.is_symlink():
                raise ValueError("fleet manifest cannot be a symlink")
            manifest_path = unresolved_manifest.resolve(strict=True)
            if not manifest_path.is_file() or manifest_path.suffix not in {
                ".json",
                ".yaml",
                ".yml",
            }:
                raise ValueError("fleet manifest must be a YAML or JSON file")

        return cls(
            campaign=campaign,
            provider=provider,
            change_id=change_id,
            repositories=tuple(repositories),
            config_path=config_path,
            manifest_path=manifest_path,
        )

    def load_manifest(self) -> APIChangeManifest:
        manifest: APIChangeManifest | None
        if self.manifest_path is not None:
            if self.manifest_path.suffix == ".json":
                manifest = APIChangeManifest.from_json(self.manifest_path)
            else:
                manifest = APIChangeManifest.from_yaml(self.manifest_path)
        else:
            manifest = get_builtin_manifest(self.provider, self.change_id)
            if manifest is None:
                raise ValueError(f"no built-in manifest for {self.provider}:{self.change_id}")
        if manifest is None:
            raise ValueError(f"no built-in manifest for {self.provider}:{self.change_id}")
        valid, errors = manifest.validate()
        if not valid:
            raise ValueError("invalid campaign manifest: " + "; ".join(errors))
        if manifest.provider != self.provider or manifest.change_id != self.change_id:
            raise ValueError("campaign manifest provider/change does not match fleet config")
        return manifest


@dataclass(frozen=True, slots=True)
class FleetRepositoryResult:
    """One repository's independently computed campaign outcome."""

    name: str
    path: str
    status: str
    affected_usages: int = 0
    affected_files: tuple[str, ...] = ()
    risk: str = "UNKNOWN"
    verification_requested: str = "v0"
    verification_achieved: str = "v0"
    certificate_id: str = ""
    certificate_path: str = ""
    certificate_digest: str = ""
    patch_digest: str = ""
    proof_digest: str = ""
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "status": self.status,
            "affected_usages": self.affected_usages,
            "affected_files": list(self.affected_files),
            "risk": self.risk,
            "verification_requested": self.verification_requested,
            "verification_achieved": self.verification_achieved,
            "certificate_id": self.certificate_id,
            "certificate_path": self.certificate_path,
            "certificate_digest": self.certificate_digest,
            "patch_digest": self.patch_digest,
            "proof_digest": self.proof_digest,
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class FleetCampaignResult:
    """Integrity-bound rollup of independently assessed repositories."""

    campaign: str
    provider: str
    change_id: str
    mode: str
    verdict: str
    repositories: tuple[FleetRepositoryResult, ...]
    created_at: str
    campaign_digest: str = ""
    schema_version: int = 1

    @classmethod
    def create(
        cls,
        *,
        config: FleetConfig,
        mode: str,
        repositories: tuple[FleetRepositoryResult, ...],
    ) -> FleetCampaignResult:
        verdict = _campaign_verdict(mode, repositories)
        result = cls(
            campaign=config.campaign,
            provider=config.provider,
            change_id=config.change_id,
            mode=mode,
            verdict=verdict,
            repositories=repositories,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        return replace(result, campaign_digest=result.expected_digest())

    @property
    def counts(self) -> dict[str, int]:
        statuses = {repository.status for repository in self.repositories}
        return {
            status: sum(repository.status == status for repository in self.repositories)
            for status in sorted(statuses)
        }

    def _integrity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign": self.campaign,
            "provider": self.provider,
            "change_id": self.change_id,
            "mode": self.mode,
            "verdict": self.verdict,
            "repositories": [repository.to_dict() for repository in self.repositories],
            "created_at": self.created_at,
        }

    def expected_digest(self) -> str:
        payload = json.dumps(
            self._integrity_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._integrity_payload(),
            "counts": self.counts,
            "campaign_digest": self.campaign_digest,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FleetCampaignResult:
        campaign = _validated_name(payload.get("campaign"), field="campaign")
        provider = _validated_name(payload.get("provider"), field="provider")
        change_id = _validated_name(payload.get("change_id"), field="change_id")
        mode = payload.get("mode")
        if mode not in {"simulate", "migrate"}:
            raise ValueError("campaign report mode must be simulate or migrate")
        raw_repositories = payload.get("repositories")
        if not isinstance(raw_repositories, list):
            raise ValueError("campaign report repositories must be a list")
        if not raw_repositories or len(raw_repositories) > _MAX_REPOSITORIES:
            raise ValueError("campaign report has an invalid repository count")
        repositories = tuple(
            FleetRepositoryResult(
                name=_validated_name(item.get("name"), field="repository name"),
                path=str(item["path"]),
                status=str(item["status"]),
                affected_usages=int(item.get("affected_usages", 0)),
                affected_files=tuple(str(value) for value in item.get("affected_files", [])),
                risk=str(item.get("risk", "UNKNOWN")),
                verification_requested=str(item.get("verification_requested", "v0")),
                verification_achieved=str(item.get("verification_achieved", "v0")),
                certificate_id=str(item.get("certificate_id", "")),
                certificate_path=str(item.get("certificate_path", "")),
                certificate_digest=str(item.get("certificate_digest", "")),
                patch_digest=str(item.get("patch_digest", "")),
                proof_digest=str(item.get("proof_digest", "")),
                errors=tuple(str(value) for value in item.get("errors", [])),
            )
            for item in raw_repositories
            if isinstance(item, dict)
        )
        if len(repositories) != len(raw_repositories):
            raise ValueError("campaign report contains an invalid repository entry")
        if len({repository.name for repository in repositories}) != len(repositories):
            raise ValueError("campaign report contains duplicate repository names")
        allowed_statuses = {
            "SAFE_TO_ATTEMPT",
            "PROVEN",
            "NEEDS_REVIEW",
            "REJECTED",
            "UNAFFECTED",
            "ERROR",
        }
        if any(repository.status not in allowed_statuses for repository in repositories):
            raise ValueError("campaign report contains an invalid repository status")
        verdict = str(payload["verdict"])
        if verdict != _campaign_verdict(mode, repositories):
            raise ValueError("campaign report verdict does not match repository outcomes")
        return cls(
            campaign=campaign,
            provider=provider,
            change_id=change_id,
            mode=mode,
            verdict=verdict,
            repositories=repositories,
            created_at=str(payload["created_at"]),
            campaign_digest=str(payload.get("campaign_digest", "")),
            schema_version=int(payload.get("schema_version", 0)),
        )


EngineFactory = Callable[..., MigrationEngine]


def simulate_fleet(
    config: FleetConfig,
    *,
    engine_factory: EngineFactory = MigrationEngine,
) -> FleetCampaignResult:
    """Read-only simulation across explicit repositories."""

    manifest = config.load_manifest()
    results: list[FleetRepositoryResult] = []
    for repository in config.repositories:
        try:
            simulation = engine_factory(root=repository.path, manifest=manifest).simulate()
            results.append(_simulation_result(repository, simulation))
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            results.append(
                FleetRepositoryResult(
                    name=repository.name,
                    path=repository.display_path,
                    status="ERROR",
                    errors=(f"{type(error).__name__}: {error}",),
                )
            )
    return FleetCampaignResult.create(config=config, mode="simulate", repositories=tuple(results))


def migrate_fleet(
    config: FleetConfig,
    *,
    generator: MigrationGenerator,
    engine_factory: EngineFactory = MigrationEngine,
) -> FleetCampaignResult:
    """Run the authoritative migration pipeline independently for every repository."""

    manifest = config.load_manifest()
    results: list[FleetRepositoryResult] = []
    for repository in config.repositories:
        try:
            migration = engine_factory(
                root=repository.path,
                manifest=manifest,
                generator=generator,
            ).run()
            results.append(_migration_result(repository, migration))
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            results.append(
                FleetRepositoryResult(
                    name=repository.name,
                    path=repository.display_path,
                    status="ERROR",
                    errors=(f"{type(error).__name__}: {error}",),
                )
            )
    return FleetCampaignResult.create(config=config, mode="migrate", repositories=tuple(results))


def write_campaign_report(
    result: FleetCampaignResult,
    path: str | Path,
) -> Path:
    """Atomically persist one campaign report."""

    unresolved_destination = Path(path).expanduser()
    if unresolved_destination.is_symlink():
        raise ValueError("campaign report destination cannot be a symlink")
    if not unresolved_destination.is_absolute():
        unresolved_destination = Path.cwd() / unresolved_destination
    unresolved_destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = unresolved_destination.parent.resolve(strict=True) / unresolved_destination.name
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("campaign report destination must be a regular, non-symlink file")
    payload = json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        if os.name != "nt":
            destination.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def verify_campaign_report(path: str | Path) -> tuple[CertificateStatus, str]:
    """Verify campaign integrity and every repository marked PROVEN."""

    unresolved_report = Path(path).expanduser()
    if unresolved_report.is_symlink():
        return CertificateStatus.INVALID, "campaign report must be a regular file"
    try:
        report_path = unresolved_report.resolve(strict=True)
    except OSError as error:
        return CertificateStatus.INVALID, f"campaign report is unreadable: {error}"
    if not report_path.is_file():
        return CertificateStatus.INVALID, "campaign report must be a regular file"
    if report_path.stat().st_size > _MAX_REPORT_BYTES:
        return CertificateStatus.INVALID, "campaign report exceeds the 5 MB limit"
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("campaign report must be an object")
        report = FleetCampaignResult.from_dict(payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return CertificateStatus.INVALID, f"invalid campaign report: {error}"
    if report.schema_version != 1:
        return CertificateStatus.INVALID, "unsupported campaign report schema"
    if not report.campaign_digest or report.campaign_digest != report.expected_digest():
        return CertificateStatus.INVALID, "campaign digest mismatch"

    for repository in report.repositories:
        if repository.status != "PROVEN":
            continue
        unresolved_root = Path(repository.path).expanduser()
        unresolved_certificate = Path(repository.certificate_path).expanduser()
        if unresolved_root.is_symlink() or unresolved_certificate.is_symlink():
            return CertificateStatus.MISMATCH, f"symlinked evidence for {repository.name}"
        try:
            root = unresolved_root.resolve(strict=True)
            certificate_path = unresolved_certificate.resolve(strict=True)
        except OSError as error:
            return CertificateStatus.INVALID, f"missing evidence for {repository.name}: {error}"
        if not root.is_dir() or not certificate_path.is_file():
            return CertificateStatus.INVALID, f"invalid evidence for {repository.name}"
        expected_parent = (root / ".agentdiff" / "certificates").resolve(strict=True)
        if certificate_path.parent != expected_parent:
            return CertificateStatus.MISMATCH, f"certificate path mismatch for {repository.name}"
        status, reason = verify_certificate(certificate_path, root=root)
        if status is not CertificateStatus.VALID:
            return status, f"{repository.name}: {reason}"
        certificate_payload = json.loads(certificate_path.read_text(encoding="utf-8"))
        if (
            certificate_payload.get("certificate_id") != repository.certificate_id
            or certificate_payload.get("integrity_sha256") != repository.certificate_digest
            or certificate_payload.get("migration_digest") != repository.patch_digest
            or certificate_payload.get("proof_digest") != repository.proof_digest
        ):
            return CertificateStatus.MISMATCH, f"child evidence mismatch for {repository.name}"
    return CertificateStatus.VALID, "campaign digest and all PROVEN child certificates are valid"


def _validated_name(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError(f"{field} must match {_NAME.pattern}")
    return value


def _campaign_verdict(
    mode: str,
    repositories: tuple[FleetRepositoryResult, ...],
) -> str:
    affected = tuple(repository for repository in repositories if repository.status != "UNAFFECTED")
    if mode == "simulate":
        return (
            "NEEDS_REVIEW"
            if any(repository.status in {"NEEDS_REVIEW", "ERROR"} for repository in affected)
            else "SAFE_TO_ATTEMPT"
        )
    if mode != "migrate":
        raise ValueError("campaign mode must be simulate or migrate")
    if not affected:
        return "NO_CHANGE"
    return (
        "PROVEN" if all(repository.status == "PROVEN" for repository in affected) else "NOT_PROVEN"
    )


def _simulation_result(
    repository: FleetRepository,
    simulation: MigrationSimulation,
) -> FleetRepositoryResult:
    status = "UNAFFECTED" if simulation.affected_usages == 0 else simulation.automation_status
    return FleetRepositoryResult(
        name=repository.name,
        path=repository.display_path,
        status=status,
        affected_usages=simulation.affected_usages,
        affected_files=simulation.affected_files,
        risk=simulation.risk,
        verification_requested=simulation.requested_verification.value,
        errors=simulation.reasons,
    )


def _migration_result(
    repository: FleetRepository,
    migration: MigrationResult,
) -> FleetRepositoryResult:
    if not migration.plan.affected_usages:
        status = "UNAFFECTED"
    elif migration.proof_verdict == "PROVEN":
        status = "PROVEN"
    elif migration.migration_status is MigrationStatus.NEEDS_REVIEW:
        status = "NEEDS_REVIEW"
    else:
        status = "REJECTED"
    certificate = migration.certificate
    certificate_path = ""
    if certificate is not None:
        certificate_path = str(
            repository.path / ".agentdiff" / "certificates" / f"{certificate.certificate_id}.json"
        )
    return FleetRepositoryResult(
        name=repository.name,
        path=str(repository.path),
        status=status,
        affected_usages=len(migration.plan.affected_usages),
        affected_files=migration.plan.affected_files,
        risk=(certificate.blast_radius_level if certificate is not None else "UNKNOWN"),
        verification_requested=migration.plan.verification_level.value,
        verification_achieved=migration.verification_level.value,
        certificate_id=certificate.certificate_id if certificate is not None else "",
        certificate_path=certificate_path,
        certificate_digest=certificate.integrity_sha256 if certificate is not None else "",
        patch_digest=certificate.migration_digest if certificate is not None else "",
        proof_digest=migration.proof_digest or "",
        errors=migration.errors,
    )

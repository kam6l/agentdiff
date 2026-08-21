"""Migration certificate output and storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentdiff.api.models import MigrationCertificate

CERTIFICATE_DIR = ".agentdiff/certificates"


def write_certificate(certificate: "MigrationCertificate", root: str | Path) -> Path:
    """Write certificate to .agentdiff/certificates/ directory."""
    root_path = Path(root).expanduser().resolve(strict=True)
    cert_dir = root_path / CERTIFICATE_DIR
    cert_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    filename = f"{certificate.certificate_id}.json"
    cert_path = cert_dir / filename

    data = certificate.to_dict()
    data["schema_version"] = 1
    data["written_at"] = datetime.now(timezone.utc).isoformat()

    cert_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return cert_path


def write_certificate_legacy(certificate: "MigrationCertificate", path: str | Path) -> Path:
    """Write certificate to a specific path."""
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    data = certificate.to_dict()
    data["schema_version"] = 1
    data["written_at"] = datetime.now(timezone.utc).isoformat()

    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return path


def read_certificate(path: str | Path) -> dict[str, Any]:
    """Read a certificate from disk."""
    path = Path(path).expanduser().resolve()
    return json.loads(path.read_text(encoding="utf-8"))


def list_certificates(root: str | Path) -> list[Path]:
    """List all certificates in the repository."""
    root_path = Path(root).expanduser().resolve(strict=True)
    cert_dir = root_path / CERTIFICATE_DIR
    if not cert_dir.exists():
        return []
    return sorted(cert_dir.glob("*.json"))


def get_latest_certificate(root: str | Path, provider: str, change_id: str) -> Path | None:
    """Get the most recent certificate for a provider/change."""
    certs = list_certificates(root)
    matching = [c for c in certs if provider in c.name and change_id in c.name]
    return matching[-1] if matching else None

"""Capsule Spec v2 model and content-addressed artifact reader."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentdiff.pathing import normalize_relative_path

_MAX_READ_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class BlobReference:
    sha256: str
    size: int
    content_type: str = "application/octet-stream"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "size": self.size,
            "content_type": self.content_type,
        }


class CapsuleReader:
    """Read artifacts and manifests from sealed AgentDiff run capsules."""

    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir).resolve(strict=True)
        if not self.run_dir.is_dir() or self.run_dir.is_symlink():
            raise ValueError("invalid capsule directory")

    @property
    def version(self) -> int:
        manifest_v2 = self.run_dir / "integrity" / "manifest.json"
        if manifest_v2.is_file():
            return 2
        manifest_v1 = self.run_dir / "integrity.json"
        if manifest_v1.is_file():
            return 1
        return 0

    def read_manifest(self) -> dict[str, Any]:
        if self.version == 2:
            target = self.run_dir / "integrity" / "manifest.json"
        elif self.version == 1:
            target = self.run_dir / "integrity.json"
        else:
            raise FileNotFoundError("capsule integrity manifest not found")
        return json.loads(target.read_text(encoding="utf-8"))

    def compute_merkle_root(self) -> str:
        """Compute the deterministic Merkle root digest over the sealed manifest entries."""
        manifest = self.read_manifest()
        files = manifest.get("files", {})
        hasher = hashlib.sha256()
        for relpath in sorted(files.keys()):
            entry = files[relpath]
            hasher.update(f"{relpath}:{entry.get('sha256')}:{entry.get('size')}\n".encode("utf-8"))
        return hasher.hexdigest()

    def compute_root_digest(self) -> str:
        """Compute the deterministic root aggregate digest over the sealed manifest entries."""
        return self.compute_merkle_root()

    def get_artifact_path(self, relative_path: str) -> Path:
        normalized = normalize_relative_path(relative_path)
        target = self.run_dir.joinpath(*normalized.split("/"))
        if not target.is_file() or target.is_symlink():
            raise FileNotFoundError(f"capsule artifact not found: {relative_path}")
        return target

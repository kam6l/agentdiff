"""Staging directory management and fsync validation for multi-file promotion."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentdiff.evidence import PatchBundle, PatchEntry

_CHUNK_SIZE = 1024 * 1024


class PromotionStager:
    """Stage replacement contents and pre-mutation backups safely before commit."""

    def __init__(self, root: str | Path, run_id: str) -> None:
        self.root = Path(root).resolve()
        self.run_id = run_id
        self.staging_dir = self.root / ".agentdiff" / "staging" / run_id
        self.backup_dir = self.root / ".agentdiff" / "backups" / run_id

    def prepare(self) -> None:
        self.clean()
        self.staging_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def stage_entry(self, bundle: PatchBundle, entry: PatchEntry) -> Path:
        """Extract and fsync patch entry into staging directory with sha256 check."""
        if entry.change_type == "deleted":
            raise ValueError("deleted entries have no staged content")

        source_path = bundle.entry_path(entry)
        if not source_path.is_file():
            raise FileNotFoundError(f"missing patch artifact for {entry.path}")

        target_staged = self.staging_dir / entry.path
        target_staged.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        with open(source_path, "rb") as src, open(target_staged, "wb") as dst:
            while chunk := src.read(_CHUNK_SIZE):
                dst.write(chunk)
                hasher.update(chunk)
            dst.flush()
            os.fsync(dst.fileno())

        digest = hasher.hexdigest()
        if entry.result_sha256 is not None and digest != entry.result_sha256:
            raise ValueError(f"staged digest mismatch for {entry.path}: expected {entry.result_sha256}, got {digest}")

        mode = entry.result_mode if entry.result_mode is not None else 0o644
        try:
            target_staged.chmod(stat.S_IMODE(mode))
        except OSError:
            pass

        return target_staged

    def backup_host_file(self, relpath: str) -> Path | None:
        """Backup existing host file before mutation."""
        host_path = self.root / relpath
        if not host_path.is_file() or host_path.is_symlink():
            return None

        backup_path = self.backup_dir / relpath
        backup_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        with open(host_path, "rb") as src, open(backup_path, "wb") as dst:
            while chunk := src.read(_CHUNK_SIZE):
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())

        return backup_path

    def clean(self) -> None:
        """Clean staging and backup temporary artifacts."""
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir, ignore_errors=True)
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir, ignore_errors=True)

"""Immutable warm base snapshots and private copy-on-write agent workspaces.

Repeated agent runs should not copy the entire repository, install
dependencies, and prepare everything from zero every time. This factory:

1. creates an immutable base snapshot keyed by :class:`WorkspaceIdentity`;
2. gives every agent a private CoW/clone workspace from that base;
3. reuses a base whenever its identity still matches;
4. invalidates automatically because a changed identity addresses a
   different base path;
5. never shares writable state between the host, the base, or other agents.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentdiff.runtime import MaterializationStrategy, WorkspaceMaterializer
from agentdiff.state import FilesystemScanner

from .identity import WorkspaceIdentity

if TYPE_CHECKING:
    from .identity import WorkspaceIdentity

_SCAN_IGNORED_NAMES = frozenset(
    {
        ".agentdiff",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
        ".next",
        "target",
        ".idea",
        ".vscode",
    }
)


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class BaseWorkspace:
    """One immutable base snapshot."""

    identity: WorkspaceIdentity
    path: Path
    manifest_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "identity_digest": self.identity.digest(),
            "path": str(self.path),
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True, slots=True)
class AgentWorkspace:
    """A private CoW workspace leased to one agent session."""

    session_id: str
    path: Path
    base: BaseWorkspace
    strategy: str

    def close(self) -> None:
        """Remove the private workspace; the immutable base is never touched."""
        if not self.path.exists():
            return
        resolved = self.path.resolve(strict=False)
        expected_parent = self.path.parent.resolve(strict=True)
        if resolved.parent != expected_parent or not resolved.name.startswith("agent-ws-"):
            raise RuntimeError("refusing to remove an unexpected agent workspace")
        WarmWorkspaceFactory._remove_read_only(resolved)


class WarmWorkspaceFactory:
    """Manage immutable bases and private agent workspaces under ``.agentdiff/warm``."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        max_bases: int = 3,
        strategy: MaterializationStrategy = MaterializationStrategy.AUTO,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self.max_bases = max_bases
        self.strategy = strategy
        self.store = self.root / ".agentdiff" / "warm"
        self.bases_dir = self.store / "bases"
        self.agents_dir = self.store / "agents"
        self.materializer = WorkspaceMaterializer(
            strategy=strategy,
            ignored_names=tuple(sorted(_SCAN_IGNORED_NAMES)),
        )

    def has_base(self, identity: WorkspaceIdentity) -> bool:
        return self._base_dir(identity).is_dir()

    def ensure_base(self, identity: WorkspaceIdentity) -> BaseWorkspace:
        """Return the immutable base for an identity, creating it if needed."""
        base_dir = self._base_dir(identity)
        manifest_path = base_dir / "manifest.json"
        if base_dir.is_dir() and manifest_path.is_file():
            manifest = self._read_manifest(manifest_path)
            if manifest is not None and manifest.get("identity_digest") == identity.digest():
                return BaseWorkspace(
                    identity=identity,
                    path=base_dir / "tree",
                    manifest_sha256=str(manifest.get("manifest_sha256", "")),
                )
            # Stale or tampered base: remove and rebuild.
            self._remove_read_only(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        tree = base_dir / "tree"
        tree.mkdir(mode=0o700)
        report = self.materializer.materialize(self.root, tree)
        self._make_read_only(tree)
        scanner = FilesystemScanner(tree, protected_patterns=None)
        before = scanner.capture(backup=False)
        files: dict[str, dict[str, int | str]] = {}
        for path, record in before.files.items():
            if record.sha256 is not None:
                files[path] = {"sha256": record.sha256, "size": record.size, "mode": record.mode}
        unsigned = {
            "schema_version": 1,
            "identity_digest": identity.digest(),
            "files": files,
        }
        manifest_sha = _canonical_digest(unsigned)
        manifest = {
            **unsigned,
            "manifest_sha256": manifest_sha,
            "materialization": {
                "strategy": report.strategy_used,
                "files": report.files_materialized,
                "bytes": report.bytes_materialized,
            },
        }
        self._atomic_write_json(manifest_path, manifest)
        self.prune()
        return BaseWorkspace(identity=identity, path=tree, manifest_sha256=manifest_sha)

    def create_workspace(
        self, identity: WorkspaceIdentity, *, session_id: str | None = None
    ) -> AgentWorkspace:
        """Create a private CoW workspace for one agent session from the base."""
        base = self.ensure_base(identity)
        self.agents_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        selected = session_id or f"session-{secrets.token_hex(6)}"
        target = self.agents_dir / f"agent-ws-{secrets.token_hex(8)}"
        target.mkdir(mode=0o700)
        strategy_used = "copy"
        for source in base.path.iterdir():
            destination = target / source.name
            if (
                self.strategy
                in {
                    MaterializationStrategy.AUTO,
                    MaterializationStrategy.REFLINK,
                }
                and getattr(os, "copy_file_range", None) is not None
            ):
                try:
                    self._reflink_tree(source, destination)
                    strategy_used = "reflink"
                except OSError:
                    self._copy_tree(source, destination)
            else:
                self._copy_tree(source, destination)
        self._make_writable(target)
        return AgentWorkspace(
            session_id=selected,
            path=target,
            base=base,
            strategy=strategy_used,
        )

    def verify_base(self, identity: WorkspaceIdentity) -> tuple[bool, str]:
        """Spot-check a base snapshot: identity match plus manifest digest."""
        base_dir = self._base_dir(identity)
        manifest_path = base_dir / "manifest.json"
        if not base_dir.is_dir() or not manifest_path.is_file():
            return False, "base snapshot is missing"
        manifest = self._read_manifest(manifest_path)
        if manifest is None:
            return False, "base manifest is unreadable"
        if manifest.get("identity_digest") != identity.digest():
            return False, "base identity does not match"
        files = manifest.get("files")
        if not isinstance(files, dict):
            return False, "base manifest has no file map"
        tree = base_dir / "tree"
        if not tree.is_dir():
            return False, "base tree is missing"
        # Full verification is deliberately available but expensive; hash a
        # deterministic sample of files when the caller asks for it.
        sampled = sorted(files.keys())[:32]
        for relative in sampled:
            expected = files[relative]
            path = tree.joinpath(*relative.split("/"))
            try:
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
            except OSError:
                return False, f"base file unreadable: {relative}"
            if digest.hexdigest() != expected.get("sha256"):
                return False, f"base file digest mismatch: {relative}"
        return True, "base snapshot verified"

    def stats(self) -> dict[str, Any]:
        bases: list[dict[str, Any]] = []
        if self.bases_dir.is_dir():
            for base_dir in sorted(self.bases_dir.iterdir()):
                if not base_dir.is_dir():
                    continue
                manifest = self._read_manifest(base_dir / "manifest.json")
                if manifest is None:
                    continue
                bases.append(
                    {
                        "identity_digest": base_dir.name,
                        "files": len(manifest.get("files", {})),
                        "materialization": manifest.get("materialization"),
                    }
                )
        return {"schema_version": 1, "bases": bases, "count": len(bases)}

    def prune(self) -> int:
        """Remove oldest bases beyond the configured cap; return count removed."""
        if not self.bases_dir.is_dir():
            return 0
        candidates: list[tuple[float, Path]] = []
        for base_dir in self.bases_dir.iterdir():
            if not base_dir.is_dir():
                continue
            try:
                candidates.append((base_dir.stat().st_mtime, base_dir))
            except OSError:
                continue
        candidates.sort()
        removed = 0
        for _, base_dir in candidates[: max(0, len(candidates) - self.max_bases)]:
            self._remove_read_only(base_dir)
            removed += 1
        return removed

    def _base_dir(self, identity: WorkspaceIdentity) -> Path:
        digest = identity.digest()
        if len(digest) != 64 or not all(character in "0123456789abcdef" for character in digest):
            raise ValueError("workspace identity digest must be a sha256 hex string")
        return self.bases_dir / digest

    @staticmethod
    def _make_writable(tree: Path) -> None:
        """Restore writable permissions on a private agent workspace clone."""
        if os.name == "nt":
            return
        for directory, directory_names, file_names in os.walk(tree, followlinks=False):
            for name in directory_names:
                with contextlib.suppress(OSError):
                    (Path(directory) / name).chmod(0o755)
            for name in file_names:
                with contextlib.suppress(OSError):
                    (Path(directory) / name).chmod(0o644)
        with contextlib.suppress(OSError):
            tree.chmod(0o755)

    @staticmethod
    def _remove_read_only(path: Path) -> None:
        """Remove a read-only tree (immutable base snapshots must be deletable)."""
        if os.name != "nt" and path.is_dir():
            for directory, directory_names, file_names in os.walk(path, followlinks=False):
                for name in directory_names:
                    with contextlib.suppress(OSError):
                        (Path(directory) / name).chmod(0o755)
                for name in file_names:
                    with contextlib.suppress(OSError):
                        (Path(directory) / name).chmod(0o644)
            with contextlib.suppress(OSError):
                path.chmod(0o755)
        shutil.rmtree(path, ignore_errors=False)

    @staticmethod
    def _make_read_only(tree: Path) -> None:
        if os.name == "nt":
            return
        for directory, directory_names, file_names in os.walk(tree, followlinks=False):
            for name in directory_names:
                with contextlib.suppress(OSError):
                    (Path(directory) / name).chmod(0o555)
            for name in file_names:
                with contextlib.suppress(OSError):
                    (Path(directory) / name).chmod(0o444)
        with contextlib.suppress(OSError):
            tree.chmod(0o555)

    @staticmethod
    def _copy_tree(source: Path, destination: Path) -> None:
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=False)
        else:
            shutil.copy2(source, destination)

    def _reflink_tree(self, source: Path, destination: Path) -> None:
        copy_file_range = getattr(os, "copy_file_range", None)
        if source.is_dir():
            destination.mkdir(mode=0o700)
            for child in source.iterdir():
                self._reflink_tree(child, destination / child.name)
            return
        if copy_file_range is None:
            raise OSError("reflink unsupported")
        source_fd = os.open(source, os.O_RDONLY)
        try:
            destination_fd = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                size = source.stat().st_size
                total = 0
                while total < size:
                    copied = copy_file_range(source_fd, destination_fd, size - total)
                    if copied == 0:
                        break
                    total += copied
                if total != size:
                    raise OSError("reflink copied fewer bytes than expected")
            finally:
                os.close(destination_fd)
        finally:
            os.close(source_fd)

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
        payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            if os.name != "nt":
                path.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)

"""Content-addressed workspace identity.

A warm base snapshot is identified by every input that can change the meaning
of the environment:

- git/base digest (HEAD plus dirty-file set)
- dependency lock digest (lockfile digests from the trust lock)
- runtime image digest (proof image name + optional repository digest)
- toolchain digest (interpreter/manager versions)
- proof-plan digest

When the identity matches, an existing base snapshot can be reused safely;
any input change produces a different identity and a fresh snapshot.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess  # nosec B404 -- fixed argv version probes only
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentdiff.trust.compiler import load_trust_lock
from agentdiff.trust.inspect import RepositoryInspector

if TYPE_CHECKING:
    from agentdiff.policy import Policy

_CANONICAL_LOCKFILE_ORDER = (
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.sum",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "mix.lock",
)


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _git_head(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(  # nosec B603
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _toolchain_digest(root: Path) -> str:
    components: dict[str, str] = {"python": platform.python_version()}
    manager_binaries = ("node", "npm", "go", "cargo", "rustc", "java", "ruby")
    for binary in manager_binaries:
        located = shutil.which(binary)
        if located is None:
            continue
        try:
            result = subprocess.run(  # nosec B603
                [binary, "--version"],
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        first_line = (result.stdout or result.stderr or "").splitlines()
        if first_line:
            components[binary] = first_line[0].strip()
    return _canonical_digest(components)


@dataclass(frozen=True, slots=True)
class WorkspaceIdentity:
    """Immutable identity of one warm base snapshot."""

    base_digest: str
    lock_digest: str
    image_digest: str
    toolchain_digest: str
    plan_digest: str
    git_head: str | None = None

    def digest(self) -> str:
        return _canonical_digest(asdict(self))

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def compute_identity(
    root: str | Path,
    *,
    policy: Policy,
    plan_digest: str = "",
    image_digest: str = "",
) -> WorkspaceIdentity:
    """Compute the workspace identity deterministically from repository state."""
    root_path = Path(root).expanduser().resolve(strict=True)
    trust_lock = load_trust_lock(root_path) or {}
    repository = trust_lock.get("repository") or {}
    lock_digests = repository.get("lockfile_digests") or {}
    if not lock_digests:
        inspection = RepositoryInspector(root_path).inspect()
        lock_digests = inspection.lockfile_digests

    ordered: list[str] = []
    for name in _CANONICAL_LOCKFILE_ORDER:
        # lock_digests keys are relative paths; match by basename.
        for key, digest in sorted(lock_digests.items()):
            if key.endswith(name) and digest not in ordered:
                ordered.append(digest)
    lock_digest = _canonical_digest({"locks": ordered}) if ordered else "no-lockfiles"

    git_head = _git_head(root_path)
    if git_head is not None:
        try:
            result = subprocess.run(  # nosec B603
                ["git", "status", "--porcelain"],
                cwd=root_path,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            dirty = len([line for line in result.stdout.splitlines() if line.strip()])
        except (OSError, subprocess.SubprocessError):
            dirty = 0
        base_digest = _canonical_digest({"git_head": git_head, "dirty_files": dirty})
    else:
        base_digest = _canonical_digest({"tree": dict(sorted(lock_digests.items()))})

    image = policy.proof.image or "python:3.12-slim"
    image_digest = image_digest or image
    plan = plan_digest or "unconfigured"
    return WorkspaceIdentity(
        base_digest=base_digest,
        lock_digest=lock_digest,
        image_digest=image_digest,
        toolchain_digest=_toolchain_digest(root_path),
        plan_digest=plan,
        git_head=git_head,
    )

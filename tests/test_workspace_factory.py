"""Tests for the trusted warm workspace factory (system 5)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff.policy import load_policy
from agentdiff.workspace import WarmWorkspaceFactory, compute_identity


def _repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "auth.py").write_text("def login(): return True\n", encoding="utf-8")
    (root / "uv.lock").write_text("lock-v1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")


def _policy() -> object:
    return load_policy(
        {
            "version": 2,
            "filesystem": {"allow_write": ["**"], "default": "allow"},
            "proof": {"image": "python:3.12-slim", "tests": [["pytest", "-q"]]},
        }
    )


def test_identity_changes_when_locks_change(tmp_path: Path) -> None:
    _repo(tmp_path)
    policy = _policy()
    first = compute_identity(tmp_path, policy=policy)
    (tmp_path / "uv.lock").write_text("lock-v2\n", encoding="utf-8")
    second = compute_identity(tmp_path, policy=policy)
    assert first.digest() != second.digest()
    assert first.lock_digest != second.lock_digest


def test_warm_base_created_once_and_reused(tmp_path: Path) -> None:
    _repo(tmp_path)
    policy = _policy()
    factory = WarmWorkspaceFactory(tmp_path)
    identity = compute_identity(tmp_path, policy=policy)

    assert not factory.has_base(identity)
    base = factory.ensure_base(identity)
    assert base.path.is_dir()
    assert (base.path / "src" / "auth.py").is_file()
    assert not (base.path / ".git").exists()
    assert not (base.path / ".agentdiff").exists()
    assert factory.has_base(identity)

    reused = factory.ensure_base(identity)
    assert reused.path == base.path
    ok, reason = factory.verify_base(identity)
    assert ok, reason


def test_agent_workspace_is_private_and_isolated(tmp_path: Path) -> None:
    _repo(tmp_path)
    policy = _policy()
    factory = WarmWorkspaceFactory(tmp_path)
    identity = compute_identity(tmp_path, policy=policy)
    workspace = factory.create_workspace(identity, session_id="sess-1")
    try:
        assert workspace.path.is_dir()
        assert workspace.session_id == "sess-1"
        # Writes inside the agent workspace must not touch the base or the host.
        target = workspace.path / "src" / "auth.py"
        target.write_text("def login(): return False\n", encoding="utf-8")
        assert (
            (workspace.base.path / "src" / "auth.py")
            .read_text(encoding="utf-8")
            .startswith("def login(): return True")
        )
        assert (
            (tmp_path / "src" / "auth.py")
            .read_text(encoding="utf-8")
            .startswith("def login(): return True")
        )
    finally:
        workspace.close()
    assert not workspace.path.exists()
    # The immutable base survives workspace cleanup.
    assert factory.has_base(identity)


def test_stale_base_is_rebuilt(tmp_path: Path) -> None:
    _repo(tmp_path)
    policy = _policy()
    factory = WarmWorkspaceFactory(tmp_path)
    identity = compute_identity(tmp_path, policy=policy)
    base = factory.ensure_base(identity)
    manifest_path = factory.bases_dir / identity.digest() / "manifest.json"
    manifest_path.write_text('{"identity_digest": "stale"}', encoding="utf-8")
    rebuilt = factory.ensure_base(identity)
    assert rebuilt.path == base.path
    ok, reason = factory.verify_base(identity)
    assert ok, reason


def test_prune_removes_oldest_bases(tmp_path: Path) -> None:
    _repo(tmp_path)
    policy = _policy()
    factory = WarmWorkspaceFactory(tmp_path, max_bases=1)
    first = compute_identity(tmp_path, policy=policy)
    factory.ensure_base(first)
    (tmp_path / "uv.lock").write_text("lock-v2\n", encoding="utf-8")
    second = compute_identity(tmp_path, policy=policy)
    factory.ensure_base(second)
    assert factory.has_base(first) or factory.has_base(second)
    stats = factory.stats()
    assert stats["count"] <= 1

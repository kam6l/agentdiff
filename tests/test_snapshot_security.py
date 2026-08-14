"""Snapshot privacy regression tests."""

import hashlib
from pathlib import Path

import psutil
import pytest

from agentdiff.diff_engine import DiffEngine


def test_environment_snapshot_excludes_secret_values_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENTDIFF_PUBLIC_SETTING", "visible")
    monkeypatch.setenv("AGENTDIFF_PRIVATE_TOKEN", "do-not-serialize")

    engine = DiffEngine(
        watch_paths=[str(tmp_path)],
        capture_processes=False,
        capture_ports=False,
    )
    _, environment = engine.snapshot()

    fingerprint = environment.env_vars["AGENTDIFF_PUBLIC_SETTING"]
    assert fingerprint.startswith("sha256:")
    assert fingerprint != "visible"
    assert "AGENTDIFF_PRIVATE_TOKEN" not in environment.env_vars
    assert "visible" not in str(environment.to_dict())
    assert "do-not-serialize" not in str(environment.to_dict())


def test_filesystem_snapshot_does_not_follow_file_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside-secret", encoding="utf-8")
    link = root / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")

    engine = DiffEngine(
        watch_paths=[str(root)],
        capture_env_vars=False,
        capture_processes=False,
        capture_ports=False,
    )
    filesystem, _ = engine.snapshot()

    outside_hash = hashlib.sha256(b"outside-secret").hexdigest()
    assert str(link) not in filesystem.file_hashes
    assert outside_hash not in filesystem.file_hashes.values()


def test_port_collection_tolerates_permission_denied(tmp_path: Path, monkeypatch) -> None:
    def deny_connections(*_args, **_kwargs):
        raise psutil.AccessDenied(pid=1)

    monkeypatch.setattr(psutil, "net_connections", deny_connections)
    engine = DiffEngine(
        watch_paths=[str(tmp_path)],
        capture_env_vars=False,
        capture_processes=False,
        capture_ports=True,
    )

    _, environment = engine.snapshot()

    assert environment.open_ports == set()

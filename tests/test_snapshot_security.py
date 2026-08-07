"""Snapshot privacy regression tests."""

from pathlib import Path

import psutil

from agentdiff import DiffEngine


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

    assert environment.env_vars["AGENTDIFF_PUBLIC_SETTING"] == "visible"
    assert "AGENTDIFF_PRIVATE_TOKEN" not in environment.env_vars
    assert "do-not-serialize" not in str(environment.to_dict())


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

"""Snapshot privacy regression tests."""

from pathlib import Path

from agentdiff import DiffEngine


def test_environment_snapshot_excludes_secret_values_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENTDIFF_PUBLIC_SETTING", "visible")
    monkeypatch.setenv("AGENTDIFF_PRIVATE_TOKEN", "do-not-serialize")

    engine = DiffEngine(watch_paths=[str(tmp_path)])
    _, environment = engine.snapshot()

    assert environment.env_vars["AGENTDIFF_PUBLIC_SETTING"] == "visible"
    assert "AGENTDIFF_PRIVATE_TOKEN" not in environment.env_vars
    assert "do-not-serialize" not in str(environment.to_dict())

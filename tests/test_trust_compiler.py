"""Tests for the Repository Trust Compiler (system 2)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff.trust import RepoImpactGraph, RepositoryInspector, TrustCompiler
from agentdiff.trust.inspect import inspection_to_policy


def _python_repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "auth.py").write_text("def login(): return True\n")
    (root / "src" / "app.py").write_text(
        "from src.auth import login\n\ndef main():\n    return login()\n"
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_auth.py").write_text(
        "from src.auth import login\n\ndef test_login():\n    assert login() is True\n"
    )
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'demo'\n[tool.pytest.ini_options]\n", encoding="utf-8"
    )
    (root / "uv.lock").write_text("lock-v1\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=x\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# repo rules\n", encoding="utf-8")


def test_inspection_detects_languages_managers_and_test_tooling(tmp_path: Path) -> None:
    _python_repo(tmp_path)
    inspection = RepositoryInspector(tmp_path).inspect()
    assert inspection.languages.primary == "python"
    assert "uv" in inspection.package_managers.managers
    assert "pytest" in inspection.toolchain.test_tools
    assert inspection.toolchain.test_commands
    assert ".env" in inspection.security_paths
    assert "AGENTS.md" in inspection.agent_configs
    assert inspection.git_head is None  # no git repo in tmp fixture
    assert inspection.lockfile_digests.get("uv.lock") is not None


def test_inspection_policy_is_conservative(tmp_path: Path) -> None:
    _python_repo(tmp_path)
    inspection = RepositoryInspector(tmp_path).inspect()
    policy = inspection_to_policy(inspection)
    assert policy["version"] == 2
    assert ".env" in policy["filesystem"]["deny"]
    assert "src/**" in policy["filesystem"]["allow_write"]
    assert "pyproject.toml" in policy["filesystem"]["review"]
    assert policy["proof"]["tests"]


def test_impact_graph_maps_changes_to_tests(tmp_path: Path) -> None:
    _python_repo(tmp_path)
    graph = RepoImpactGraph.from_inspection(tmp_path)
    affected = graph.affected(["src/auth.py"])
    assert "src.auth" in affected.modules
    assert "src.app" in affected.modules
    assert "tests.test_auth" in affected.tests


def test_compiler_writes_canonical_trust_configuration(tmp_path: Path) -> None:
    _python_repo(tmp_path)
    TrustCompiler(tmp_path).compile()
    assert (tmp_path / "agentdiff.yaml").is_file()
    assert (tmp_path / ".agentdiff" / "trust.lock").is_file()
    assert (tmp_path / ".agentdiff" / "repo-graph.json").is_file()
    assert (tmp_path / ".agentdiff" / "proof-plan.json").is_file()
    assert (tmp_path / ".agentdiff" / "adapters" / "agent-instructions.md").is_file()
    assert (tmp_path / ".agentdiff" / "adapters" / "CLAUDE.md").is_file()
    lock = json.loads((tmp_path / ".agentdiff" / "trust.lock").read_text(encoding="utf-8"))
    assert lock["schema_version"] == 1
    assert lock["policy_sha256"]
    assert lock["graph_sha256"]
    assert lock["repository"]["lockfile_digests"]["uv.lock"]


def test_compiler_is_idempotent_and_force_rewrites(tmp_path: Path) -> None:
    _python_repo(tmp_path)
    first = TrustCompiler(tmp_path).compile()
    with pytest.raises(FileExistsError):
        TrustCompiler(tmp_path).compile()
    second = TrustCompiler(tmp_path).compile(force=True)
    assert first.policy_sha256 == second.policy_sha256
    assert first.graph_sha256 == second.graph_sha256


def test_compiler_dry_run_writes_nothing(tmp_path: Path) -> None:
    _python_repo(tmp_path)
    report = TrustCompiler(tmp_path).compile(dry_run=True)
    assert report.written == ()
    assert not (tmp_path / "agentdiff.yaml").exists()


def test_compiler_honors_policy_overrides(tmp_path: Path) -> None:
    _python_repo(tmp_path)
    report = TrustCompiler(tmp_path, policy_overrides={"limits": {"files_changed": 7}}).compile()
    policy = (tmp_path / "agentdiff.yaml").read_text(encoding="utf-8")
    assert "files_changed: 7" in policy
    assert report.policy_sha256

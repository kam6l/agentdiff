"""Tests for impact-aware proof planning and the content-addressed proof cache (system 4)."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff.impact.cache import (
    ProofCache,
    ProofCacheEntry,
    ProofCacheKey,
    ProofCachePhase,
)
from agentdiff.impact.impact import ImpactEngine, build_proof_cache_key, classify_risk
from agentdiff.policy import load_policy
from agentdiff.proof import ProofEngine, ProofVerdict
from agentdiff.transaction import AgentRunTransaction

from .fake_proof import fake_env_factory


def test_classify_risk_high_risk_paths() -> None:
    assert classify_risk("src/app.py") == "targeted"
    assert classify_risk("uv.lock") == "full"
    assert classify_risk("package.json") == "full"
    assert classify_risk(".github/workflows/ci.yml") == "full"
    assert classify_risk("Dockerfile") == "full"
    assert classify_risk(".env") == "full"
    assert classify_risk("tests/test_auth.py") == "targeted"


def _impact_engine(root: Path) -> ImpactEngine:
    from agentdiff.trust import RepoImpactGraph

    graph = RepoImpactGraph.from_inspection(root)
    proof_plan = {
        "full": {
            "setup": [],
            "build": [],
            "tests": [["uv", "run", "pytest", "-q"]],
        },
        "targeted": {"static": [["uv", "run", "pytest", "-q", "tests/"]]},
        "primary_manager": "uv",
    }
    return ImpactEngine(root, graph=graph, proof_plan=proof_plan)


def _repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "auth.py").write_text("def login(): return True\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_auth.py").write_text(
        "from src.auth import login\n\ndef test_login():\n    assert login() is True\n"
    )
    (root / "uv.lock").write_text("lock-v1\n", encoding="utf-8")


def test_impact_plan_targeted_for_source_change(tmp_path: Path) -> None:
    _repo(tmp_path)
    plan = _impact_engine(tmp_path).plan(["src/auth.py"])
    assert plan.level == "targeted"
    assert "src.auth" in plan.modules
    assert "tests/test_auth.py" in plan.tests
    assert plan.test_commands


def test_impact_plan_full_for_dependency_change(tmp_path: Path) -> None:
    _repo(tmp_path)
    plan = _impact_engine(tmp_path).plan(["uv.lock"])
    assert plan.level == "full"
    assert "uv.lock" in plan.triggers
    assert plan.test_commands == (("uv", "run", "pytest", "-q"),)


def test_impact_plan_is_deterministic(tmp_path: Path) -> None:
    _repo(tmp_path)
    engine = _impact_engine(tmp_path)
    first = engine.plan(["src/auth.py", "src/__init__.py"])
    second = engine.plan(["src/__init__.py", "src/auth.py"])
    assert first.plan_digest == second.plan_digest


def test_proof_cache_store_lookup_and_invalidation(tmp_path: Path) -> None:
    cache = ProofCache(tmp_path)
    key = ProofCacheKey(
        base_digest="a" * 64,
        patch_digest="b" * 64,
        lock_digest="c" * 64,
        image_digest="python:3.12-slim",
        plan_digest="d" * 64,
        target="targeted",
    )
    entry = ProofCacheEntry(
        key=key,
        verdict="PROVEN",
        promotion="ALLOWED",
        phases=(
            ProofCachePhase(
                phase="tests",
                returncode=0,
                output_sha256="e" * 64,
                duration_seconds=0.1,
                tests_passed=1,
                tests_total=1,
            ),
        ),
        cached_from_run="run-abc",
        created_at="2026-01-01T00:00:00Z",
    )
    assert cache.lookup(key) is None
    cache.store(key, entry)
    hit = cache.lookup(key)
    assert hit is not None
    assert hit.verdict == "PROVEN"
    assert hit.cached_from_run == "run-abc"

    # Any changed input is a miss.
    changed = ProofCacheKey(
        base_digest="a" * 64,
        patch_digest="f" * 64,
        lock_digest="c" * 64,
        image_digest="python:3.12-slim",
        plan_digest="d" * 64,
        target="targeted",
    )
    assert cache.lookup(changed) is None
    assert cache.stats()["count"] == 1


def test_proof_cache_tamper_detection(tmp_path: Path) -> None:
    cache = ProofCache(tmp_path)
    key = ProofCacheKey(
        base_digest="a" * 64,
        patch_digest="b" * 64,
        lock_digest="c" * 64,
        image_digest="python:3.12-slim",
        plan_digest="d" * 64,
        target="full",
    )
    cache.store(
        key,
        ProofCacheEntry(
            key=key,
            verdict="PROVEN",
            promotion="ALLOWED",
            phases=(),
            cached_from_run="run-1",
        ),
    )
    entry_dir = cache.directory / key.digest()
    entry_path = entry_dir / "entry.json"
    tampered = entry_path.read_text(encoding="utf-8").replace(
        '"verdict": "PROVEN"', '"verdict": "NOT_PROVEN"'
    )
    entry_path.write_text(tampered, encoding="utf-8")
    assert cache.lookup(key) is None  # integrity manifest no longer matches


def test_proof_engine_cache_integration_skips_identical_runs(tmp_path: Path) -> None:
    policy = load_policy(
        {
            "version": 2,
            "filesystem": {"allow_write": ["**"], "default": "allow"},
            "process": {"allow": ["python*"], "default": "deny"},
            "network": {"mode": "off"},
            "proof": {
                "image": "python:3.12-slim",
                "network": False,
                "setup": [],
                "build": [["python", "-m", "compileall", "-q", "."]],
                "tests": [
                    [
                        "python",
                        "-c",
                        "import pathlib; assert pathlib.Path('v.txt').read_text() == '2'",
                    ]
                ],
            },
        }
    )
    (tmp_path / "v.txt").write_text("1", encoding="utf-8")

    def run_agent() -> str:
        result = AgentRunTransaction(
            root=tmp_path,
            policy=policy,
            task="cache integration",
        ).run([sys.executable, "-c", "from pathlib import Path; Path('v.txt').write_text('2')"])
        assert result.status == "passed"
        return result.run_id

    cache = ProofCache(tmp_path)
    runner, calls = _counting_runner()
    run_id = run_agent()
    first = ProofEngine(
        tmp_path, run_id, cache=cache, environment_factory=fake_env_factory(runner)
    ).prove()
    assert first.verdict is ProofVerdict.PROVEN
    assert not first.cache_hit
    first_calls = len(calls)

    # A second identical run (same base, same patch) is served from the cache.
    (tmp_path / "v.txt").write_text("1", encoding="utf-8")
    run_id2 = run_agent()
    second = ProofEngine(
        tmp_path, run_id2, cache=cache, environment_factory=fake_env_factory(runner)
    ).prove()
    assert second.verdict is ProofVerdict.PROVEN
    assert second.cache_hit
    assert second.cached_from_run == run_id
    assert len(calls) == first_calls  # the fake clean room was not re-invoked


def test_build_proof_cache_key_uses_trust_lock(tmp_path: Path) -> None:
    from agentdiff.trust import TrustCompiler

    _repo(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    TrustCompiler(tmp_path).compile()
    key = build_proof_cache_key(
        root=tmp_path,
        base_digest="b" * 64,
        patch_digest="p" * 64,
        image_digest="python:3.12-slim",
        plan_digest="d" * 64,
        target="full",
    )
    assert key.lock_digest != "no-trust-lock"
    assert key.digest()


def _counting_runner():
    calls: list[int] = []

    def runner(phase: str, command: tuple[str, ...]):
        del phase, command
        calls.append(1)
        return (0, (1, 1))

    return runner, calls

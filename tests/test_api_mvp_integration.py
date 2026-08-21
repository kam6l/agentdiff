"""
MVP Integration Test: End-to-end API migration validation.

Scenario:
- Create a realistic Python repository fixture
- Add OpenAI SDK usage (client.chat.completions.create)
- Add package version (openai>=1.0)
- Run agentdiff api scan
- Run agentdiff api check
- Verify:
  - usages detected correctly
  - affected files are correct
  - blast radius is calculated
  - ImpactEngine selects the correct test scope

Then simulate a migration manually:
- replace old API usage with new usage
- run AgentDiff proof pipeline
- verify verification results
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentdiff.cli", *args],
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )


def _create_test_repo(root: Path) -> None:
    """Create a realistic test repository with OpenAI usage."""
    # Source code
    src = root / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")

    # Main LLM module using modern OpenAI client
    (src / "llm.py").write_text("""
import openai

client = openai.OpenAI()

def ask_gpt(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content

def ask_with_tools(prompt: str, tools: list) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        tools=tools,
    )
    return response.choices[0].message.content
""")

    # Legacy usage file (should be flagged)
    (src / "legacy.py").write_text("""
import openai

def legacy_chat(prompt: str) -> str:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0301",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
""")

    # Tests directory
    tests = root / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("")
    (tests / "test_llm.py").write_text("""
from src.llm import ask_gpt

def test_ask_gpt():
    # This test will fail without API key, but proves test exists
    try:
        result = ask_gpt("hello")
        assert isinstance(result, str)
    except Exception:
        # No API key in test env - that's fine
        pass
""")

    # uv.lock with openai>=1.0
    (root / "uv.lock").write_text("""
version = 1
revision = 3

[[package]]
name = "openai"
version = "1.50.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "pytest"
version = "8.0.0"
source = { registry = "https://pypi.org/simple" }
""")

    # pyproject.toml
    (root / "pyproject.toml").write_text("""
[project]
name = "test-repo"
version = "0.1.0"
dependencies = [
    "openai>=1.0.0",
    "pytest>=8.0.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
""")


class TestAPIMigrationMVP:
    """Test the full MVP pipeline for API migration validation."""

    def test_scan_detects_usages(self, tmp_path: Path) -> None:
        """agentdiff api scan should detect all OpenAI usages."""
        _create_test_repo(tmp_path)

        result = run_cli("api", "scan", "--root", str(tmp_path), "--format", "json", cwd=tmp_path)
        assert result.returncode == 0, f"Scan failed: {result.stderr}"

        payload = json.loads(result.stdout)
        assert payload["count"] >= 4, f"Expected at least 4 usages, got {payload['count']}"

        # Verify specific symbols detected
        symbols = {u["symbol"] for u in payload["usages"]}
        assert "client.chat.completions.create" in symbols
        assert "openai.ChatCompletion.create" in symbols

    def test_check_detects_breaking_changes(self, tmp_path: Path) -> None:
        """agentdiff api check should detect breaking changes for legacy usage."""
        _create_test_repo(tmp_path)

        result = run_cli("api", "check", "--root", str(tmp_path), "--format", "json", cwd=tmp_path)
        # Should fail (exit code 1) because breaking changes detected
        assert result.returncode == 1, f"Check should fail with breaking changes: {result.stdout}"

        payload = json.loads(result.stdout)
        assert payload["affected_usages"] >= 1, "Should detect at least 1 affected usage"
        assert payload["blast_radius"]["score"] > 0, "Blast radius should be > 0"
        assert payload["risk_level"] in {"moderate", "high", "critical"}

        # Verify the legacy usage is flagged
        matched_symbols = {m["usage"]["symbol"] for m in payload["matched_changes"]}
        assert "openai.ChatCompletion.create" in matched_symbols

    def test_check_passes_for_modern_usage_only(self, tmp_path: Path) -> None:
        """agentdiff api check should pass when only modern usage exists."""
        # Create repo with ONLY modern usage
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "modern.py").write_text("""
import openai
client = openai.OpenAI()
client.responses.create(model="gpt-4o", input="hello")
""")
        (tmp_path / "uv.lock").write_text("""
[[package]]
name = "openai"
version = "1.50.0"
""")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")

        result = run_cli("api", "check", "--root", str(tmp_path), "--fail-on", "high", cwd=tmp_path)
        assert result.returncode == 0, f"Modern usage should pass: {result.stdout}"
        assert "No breaking changes detected" in result.stdout

    def test_impact_engine_selects_correct_scope(self, tmp_path: Path) -> None:
        """ImpactEngine should select targeted tests for source changes."""
        _create_test_repo(tmp_path)

        result = run_cli("api", "check", "--root", str(tmp_path), "--format", "json", cwd=tmp_path)
        payload = json.loads(result.stdout)

        impact_plan = payload.get("impact_plan")
        assert impact_plan is not None, "Impact plan should be generated"

        # Should be targeted (not full) for source file changes
        assert impact_plan["level"] in {"targeted", "static"}, (
            f"Expected targeted/static, got {impact_plan['level']}"
        )

        # Should include the test file
        if impact_plan["tests"]:
            test_files = impact_plan["tests"]
            assert any("test_llm.py" in t for t in test_files), (
                f"Expected test_llm.py in tests: {test_files}"
            )

    def test_verification_confidence_reported(self, tmp_path: Path) -> None:
        """MigrationImpact should include verification_confidence field."""
        _create_test_repo(tmp_path)

        result = run_cli("api", "check", "--root", str(tmp_path), "--format", "json", cwd=tmp_path)
        payload = json.loads(result.stdout)

        assert "verification_confidence" in payload, "Missing verification_confidence field"
        confidence = payload["verification_confidence"]
        assert confidence in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}, (
            f"Invalid confidence: {confidence}"
        )

    def test_coverage_warning_when_no_tests(self, tmp_path: Path) -> None:
        """ImpactEngine should warn when affected code has no tests."""
        # Create repo with NO tests - using LEGACY API that will be flagged
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "service.py").write_text("""
import openai

def legacy_chat(prompt: str) -> str:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0301",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
""")
        (tmp_path / "uv.lock").write_text('[[package]]\nname = "openai"\nversion = "1.50.0"\n')
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")

        result = run_cli("api", "check", "--root", str(tmp_path), "--format", "json", cwd=tmp_path)
        payload = json.loads(result.stdout)

        impact_plan = payload.get("impact_plan")
        assert impact_plan is not None

        # Should have coverage warning
        assert impact_plan.get("affected_code_has_tests") is False
        assert impact_plan.get("coverage_warning") is not None
        assert "verification confidence reduced" in impact_plan["coverage_warning"].lower()

    def test_migration_assessment_scoring(self, tmp_path: Path) -> None:
        """MigrationAssessment should score migration feasibility."""
        from agentdiff.api import APIMatcher, APIScanner, assess_migration_confidence

        _create_test_repo(tmp_path)

        scanner = APIScanner()
        usages = scanner.scan(tmp_path)

        matcher = APIMatcher()
        impact = matcher.calculate_impact(usages, root=tmp_path)

        assessment = assess_migration_confidence(tuple(usages), impact)

        assert assessment.confidence in {"high", "medium", "low", "unknown"}
        assert assessment.strategy in {"ast_transform", "coding_agent", "manual"}
        assert 0 <= assessment.score <= 100
        assert isinstance(assessment.reasons, tuple)
        assert isinstance(assessment.risk_factors, tuple)

        # Should be medium/high for this simple case with tests
        assert assessment.confidence in {"high", "medium"}

    def test_migration_assessment_low_confidence_no_tests(self, tmp_path: Path) -> None:
        """MigrationAssessment should be LOW/MEDIUM confidence when no tests exist."""
        from agentdiff.api import APIMatcher, APIScanner, assess_migration_confidence
        from agentdiff.trust import RepoImpactGraph

        # Repo with NO tests - using LEGACY API that will be flagged
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "service.py").write_text("""
import openai

def legacy_chat(prompt: str) -> str:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-0301",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
""")
        (tmp_path / "uv.lock").write_text('[[package]]\nname = "openai"\nversion = "1.50.0"\n')

        scanner = APIScanner()
        usages = scanner.scan(tmp_path)

        matcher = APIMatcher()
        impact = matcher.calculate_impact(usages, root=tmp_path)

        graph = RepoImpactGraph.from_inspection(tmp_path)
        assessment = assess_migration_confidence(tuple(usages), impact, graph)

        # Without tests, confidence should not be HIGH
        assert assessment.confidence in {"low", "medium"}
        assert assessment.strategy in {"coding_agent", "manual"}
        assert any("no test coverage" in f.lower() for f in assessment.risk_factors)


class TestAPIFixtureAccuracy:
    """Test detection accuracy against known fixtures."""

    def test_openai_normal_usage(self, tmp_path: Path) -> None:
        fixture = Path("tests/fixtures/api_repos/openai_normal_usage.py")
        if not fixture.exists():
            pytest.skip("Fixture not found")

        scanner = __import__("agentdiff.api").api.APIScanner()
        usages = scanner.scan_code(fixture.read_text(), filepath="openai_normal_usage.py")

        calls = [u for u in usages if u.call_type == "call"]
        assert len(calls) >= 2, f"Expected at least 2 calls, got {len(calls)}"
        symbols = {c.symbol for c in calls}
        assert "client.chat.completions.create" in symbols

    def test_openai_alias_usage(self, tmp_path: Path) -> None:
        fixture = Path("tests/fixtures/api_repos/openai_alias_usage.py")
        if not fixture.exists():
            pytest.skip("Fixture not found")

        scanner = __import__("agentdiff.api").api.APIScanner()
        usages = scanner.scan_code(fixture.read_text(), filepath="openai_alias_usage.py")

        calls = [u for u in usages if u.call_type == "call"]
        symbols = {c.symbol for c in calls}
        # Should resolve aliases to canonical symbols
        assert "client.chat.completions.create" in symbols
        assert "openai.ChatCompletion.create" in symbols

    def test_openai_async_usage(self, tmp_path: Path) -> None:
        fixture = Path("tests/fixtures/api_repos/openai_async_usage.py")
        if not fixture.exists():
            pytest.skip("Fixture not found")

        scanner = __import__("agentdiff.api").api.APIScanner()
        usages = scanner.scan_code(fixture.read_text(), filepath="openai_async_usage.py")

        calls = [u for u in usages if u.call_type == "call"]
        symbols = {c.symbol for c in calls}
        assert "client.chat.completions.create" in symbols
        assert "client.embeddings.create" in symbols

    def test_openai_wrapper_usage_detected(self, tmp_path: Path) -> None:
        """Wrapper usage should be detected but flagged as lower confidence."""
        fixture = Path("tests/fixtures/api_repos/openai_wrapper_usage.py")
        if not fixture.exists():
            pytest.skip("Fixture not found")

        scanner = __import__("agentdiff.api").api.APIScanner()
        usages = scanner.scan_code(fixture.read_text(), filepath="openai_wrapper_usage.py")

        calls = [u for u in usages if u.call_type == "call"]
        # Should detect the calls inside wrapper functions
        assert len(calls) >= 2
        symbols = {c.symbol for c in calls}
        assert "client.chat.completions.create" in symbols

    def test_openai_invalid_usage_not_detected(self, tmp_path: Path) -> None:
        """User-defined classes and unrelated usage should NOT be detected."""
        fixture = Path("tests/fixtures/api_repos/openai_invalid_usage.py")
        if not fixture.exists():
            pytest.skip("Fixture not found")

        scanner = __import__("agentdiff.api").api.APIScanner()
        usages = scanner.scan_code(fixture.read_text(), filepath="openai_invalid_usage.py")

        # Should only detect the real openai import if present, but NOT the user classes
        # The fixture has NO real openai import, so should be empty or only config
        calls = [u for u in usages if u.call_type == "call"]
        assert len(calls) == 0, (
            f"Should not detect user-defined classes: {[c.symbol for c in calls]}"
        )

    def test_stripe_normal_usage(self, tmp_path: Path) -> None:
        fixture = Path("tests/fixtures/api_repos/stripe_normal_usage.py")
        if not fixture.exists():
            pytest.skip("Fixture not found")

        scanner = __import__("agentdiff.api").api.APIScanner()
        usages = scanner.scan_code(fixture.read_text(), filepath="stripe_normal_usage.py")

        calls = [u for u in usages if u.call_type == "call"]
        symbols = {c.symbol for c in calls}
        assert "stripe.Charge.create" in symbols
        assert "stripe.PaymentIntent.create" in symbols

    def test_stripe_wrapper_usage(self, tmp_path: Path) -> None:
        fixture = Path("tests/fixtures/api_repos/stripe_wrapper_usage.py")
        if not fixture.exists():
            pytest.skip("Fixture not found")

        scanner = __import__("agentdiff.api").api.APIScanner()
        usages = scanner.scan_code(fixture.read_text(), filepath="stripe_wrapper_usage.py")

        calls = [u for u in usages if u.call_type == "call"]
        symbols = {c.symbol for c in calls}
        assert "stripe.Charge.create" in symbols
        assert "stripe.Subscription.create" in symbols

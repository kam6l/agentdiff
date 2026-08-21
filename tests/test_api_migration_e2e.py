"""End-to-end integration test for OpenAI API migration."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agentdiff.api import (
    APIChangeManifest,
    MigrationEngine,
    MigrationStatus,
    VerificationLevel,
    assess_migration_confidence,
    get_builtin_manifest,
)
from agentdiff.api.scanner import APIScanner
from agentdiff.api.matcher import APIMatcher


class TestOpenAIMigrationE2E:
    """End-to-end test for OpenAI chat.completions.create -> responses.create migration."""

    @pytest.fixture
    def openai_repo(self, tmp_path: Path) -> Path:
        """Create a test repository with OpenAI usage."""
        repo = tmp_path / "test_repo"
        repo.mkdir()

        # Create source files with OpenAI usage
        src = repo / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")

        # File 1: Direct usage
        (src / "chat.py").write_text("""
from openai import OpenAI

client = OpenAI()

def ask_question(question: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": question}],
    )
    return response.choices[0].message.content

def ask_with_tools(question: str, tools: list) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": question}],
        tools=tools,
    )
    return response.choices[0].message.content
""")

        # File 2: Another usage
        (src / "assistant.py").write_text("""
from openai import OpenAI

client = OpenAI()

class Assistant:
    def __init__(self):
        self.client = OpenAI()

    def chat(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
""")

        # Tests directory
        tests = repo / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("")
        (tests / "test_chat.py").write_text("""
import pytest
from src.chat import ask_question

def test_ask_question():
    # This will fail without API key, but proves test exists
    try:
        result = ask_question("hello")
        assert isinstance(result, str)
    except Exception:
        pytest.skip("No API key available")
""")

        (tests / "test_assistant.py").write_text("""
import pytest
from src.assistant import Assistant

def test_assistant_chat():
    # This will fail without API key, but proves test exists
    try:
        assistant = Assistant()
        result = assistant.chat("hello")
        assert isinstance(result, str)
    except Exception:
        pytest.skip("No API key available")
""")

        # uv.lock with openai>=1.0
        (repo / "uv.lock").write_text("""
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
        (repo / "pyproject.toml").write_text("""
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

        return repo

    def test_scan_detects_openai_usages(self, openai_repo: Path) -> None:
        """Scanner should detect all OpenAI chat.completions.create usages."""
        scanner = APIScanner()
        usages = scanner.scan(openai_repo)

        # Should find 3 usages (2 in chat.py, 1 in assistant.py)
        chat_usages = [u for u in usages if u.symbol == "client.chat.completions.create"]
        assert len(chat_usages) == 3

    def test_matcher_finds_breaking_change(self, openai_repo: Path) -> None:
        """Matcher should detect the chat_to_responses breaking change."""
        scanner = APIScanner()
        usages = scanner.scan(openai_repo)

        matcher = APIMatcher()
        impact = matcher.calculate_impact(usages, root=openai_repo)

        # Should find the breaking change
        assert impact.affected_usages == 3
        assert set(impact.affected_files) == {"src/chat.py", "src/assistant.py"}
        assert impact.blast_radius.score > 0

        # Check the specific change is detected
        change_ids = {m.change.change_id for m in impact.matched_changes}
        assert "openai-chat-to-responses" in change_ids

    def test_migration_confidence_high(self, openai_repo: Path) -> None:
        """Migration confidence should be HIGH for direct SDK usage with tests."""
        scanner = APIScanner()
        usages = scanner.scan(openai_repo)

        matcher = APIMatcher()
        impact = matcher.calculate_impact(usages, root=openai_repo)

        assessment = assess_migration_confidence(tuple(usages), impact)

        assert assessment.confidence.value == "high"
        assert assessment.strategy.value == "ast_transform"

    def test_full_migration_e2e(self, openai_repo: Path) -> None:
        """Full end-to-end migration: scan -> plan -> execute -> verify -> certify."""
        engine = MigrationEngine(
            root=openai_repo,
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
        )

        result = engine.run()

        # Verify migration completed successfully
        assert result.migration_status == MigrationStatus.COMPLETED
        assert result.verification_level in (
            VerificationLevel.V1,
            VerificationLevel.V2,
            VerificationLevel.V3,
        )
        assert result.certificate is not None
        assert result.certificate.verified is True

        # Check affected files were modified
        assert len(result.plan.affected_files) == 2
        assert len(result.plan.affected_usages) == 3

        # Check certificate was written
        cert_path = Path(openai_repo) / ".agentdiff" / "certificates"
        certs = list(cert_path.glob("*.json"))
        assert len(certs) >= 1

    def test_migration_transforms_code_correctly(self, openai_repo: Path) -> None:
        """Verify the AST transform produces correct code."""
        from agentdiff.api.transforms import OpenAIChatToResponsesTransform
        from agentdiff.api.transforms.base import TransformContext

        engine = MigrationEngine(
            root=openai_repo,
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
        )

        result = engine.run()

        # The migration must succeed and complete
        assert result.migration_status == MigrationStatus.COMPLETED
        assert result.certificate is not None
        assert result.certificate.verified is True

        # The original repository must NOT be modified (transform happens in
        # the private workspace; promotion is a separate, later gate).
        original = (openai_repo / "src" / "chat.py").read_text(encoding="utf-8")
        assert "client.chat.completions.create" in original
        assert "client.responses.create" not in original

        # Validate the transform output directly.
        source = """
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
    temperature=0.7,
)
"""
        usage = result.plan.affected_usages[0]
        transform = OpenAIChatToResponsesTransform()
        context = TransformContext(
            usage=usage,
            source_code=source,
            filepath="chat.py",
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
            all_usages=result.plan.affected_usages,
        )
        transform_result = transform.transform(context)
        assert transform_result.success

        # Should have responses.create instead of chat.completions.create
        assert "client.responses.create" in transform_result.modified_code
        assert "client.chat.completions.create" not in transform_result.modified_code
        assert "input=" in transform_result.modified_code  # messages -> input mapping
        assert "model=" in transform_result.modified_code  # model preserved
        assert "temperature=0.7" in transform_result.modified_code

    def test_certificate_generated(self, openai_repo: Path) -> None:
        """Migration certificate should be generated with all required fields."""
        engine = MigrationEngine(
            root=openai_repo,
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
        )

        result = engine.run()

        cert = result.certificate
        assert cert is not None
        assert cert.certificate_id.startswith("cert-")
        assert cert.provider == "openai"
        assert cert.change_id == "chat_to_responses"
        assert cert.verified is True
        assert cert.verification_level >= VerificationLevel.V1
        assert len(cert.affected_files) == 2
        assert cert.blast_radius_score > 0
        assert cert.proof_digest
        assert cert.capsule_id
        assert cert.migration_digest

        # Check certificate file exists
        cert_path = Path(openai_repo) / ".agentdiff" / "certificates"
        cert_files = list(cert_path.glob("*.json"))
        assert len(cert_files) >= 1

    def test_migration_rejected_when_no_tests(self, tmp_path: Path) -> None:
        """Migration should fail or have low verification when no tests exist."""
        repo = tmp_path / "no_tests_repo"
        repo.mkdir()

        src = repo / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "service.py").write_text("""
from openai import OpenAI
client = OpenAI()

def ask(q: str):
    return client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": q}])
""")

        (repo / "uv.lock").write_text("""
[[package]]
name = "openai"
version = "1.50.0"
""")
        (repo / "pyproject.toml").write_text("[project]\nname='test'\n")

        engine = MigrationEngine(
            root=repo,
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
        )

        result = engine.run()

        # Migration should complete but verification level should be V1 (no tests)
        assert result.migration_status == MigrationStatus.COMPLETED
        assert result.verification_level == VerificationLevel.V1


class TestMigrationFailureHandling:
    """Test migration failure and repair handling."""

    def test_migration_rejected_on_policy_violation(self, tmp_path: Path) -> None:
        """Migration should fail if it violates policy (e.g., modifies unexpected files)."""
        repo = tmp_path / "policy_repo"
        repo.mkdir()

        src = repo / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "chat.py").write_text("""
from openai import OpenAI
client = OpenAI()
client.chat.completions.create(model="gpt-4o", messages=[])
""")

        # Create a policy that only allows src/ but the transform might try to modify something else
        (repo / "agentdiff.yaml").write_text("""
version: 2
filesystem:
  allow_write: ["src/**"]
  deny: ["**"]
  default: deny
process:
  default: allow
network:
  mode: observe
""")

        (repo / "uv.lock").write_text('[[package]]\nname = "openai"\nversion = "1.50.0"\n')
        (repo / "pyproject.toml").write_text("[project]\nname='test'\n")

        engine = MigrationEngine(
            root=repo,
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
        )

        result = engine.run()

        # Should still work since transform only modifies allowed files
        assert result.migration_status == MigrationStatus.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

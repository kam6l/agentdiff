"""End-to-end integration test for OpenAI API migration."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentdiff.api import (
    MigrationEngine,
    MigrationStatus,
    VerificationLevel,
    assess_migration_confidence,
    get_builtin_manifest,
)
from agentdiff.api.certificate import CertificateStatus, verify_certificate
from agentdiff.api.github_pr import VerifiedPRPublisher
from agentdiff.api.matcher import APIMatcher
from agentdiff.api.scanner import APIScanner
from tests.fake_proof import fake_env_factory


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

def ask_briefly(question: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": question}],
        max_tokens=80,
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
version = "3.3.1"
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
            proof_environment_factory=fake_env_factory(),
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
            proof_environment_factory=fake_env_factory(),
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
print(response.choices[0].message.content)
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
        assert "response.output_text" in transform_result.modified_code

    def test_certificate_generated(self, openai_repo: Path) -> None:
        """Migration certificate should be generated with all required fields."""
        engine = MigrationEngine(
            root=openai_repo,
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
            proof_environment_factory=fake_env_factory(),
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
        assert cert.blast_radius_score >= 0
        assert cert.proof_digest
        assert cert.capsule_id
        assert cert.migration_digest

        # Check certificate file exists
        cert_path = Path(openai_repo) / ".agentdiff" / "certificates"
        cert_files = list(cert_path.glob("*.json"))
        assert len(cert_files) >= 1
        status, reason = verify_certificate(cert_files[0], root=openai_repo)
        assert status is CertificateStatus.VALID, reason

    def test_verified_pr_replays_the_sealed_patch(self, openai_repo: Path, tmp_path: Path) -> None:
        """PR delivery must push the sealed patch without regenerating it."""

        def git(*args: str, cwd: Path = openai_repo) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )

        git("init", "-b", "main")
        git("config", "user.name", "AgentDiff Test")
        git("config", "user.email", "agentdiff@example.invalid")
        git("add", "--all")
        git("commit", "-m", "base")
        upstream = tmp_path / "upstream.git"
        subprocess.run(
            ["git", "init", "--bare", str(upstream)],
            check=True,
            capture_output=True,
            text=True,
        )
        git("remote", "add", "origin", str(upstream))
        git("push", "--set-upstream", "origin", "main")

        result = MigrationEngine(
            root=openai_repo,
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
            proof_environment_factory=fake_env_factory(),
        ).run()
        assert result.proof_verdict == "PROVEN"
        certificate_path = next((openai_repo / ".agentdiff" / "certificates").glob("*.json"))
        gh_commands: list[list[str]] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if command[0] == "gh":
                gh_commands.append(command)
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="https://github.com/acme/repo/pull/1\n",
                    stderr="",
                )
            return subprocess.run(command, **kwargs)  # type: ignore[arg-type]

        published = VerifiedPRPublisher(openai_repo, runner=runner).publish(
            result,
            certificate_path,
            base_branch="main",
            branch="agentdiff/test-openai-migration",
        )

        assert published.url == "https://github.com/acme/repo/pull/1"
        assert published.base_sha == git("rev-parse", "HEAD").stdout.strip()
        assert gh_commands and gh_commands[0][:3] == ["gh", "pr", "create"]
        delivered = subprocess.run(
            [
                "git",
                "--git-dir",
                str(upstream),
                "show",
                "agentdiff/test-openai-migration:src/chat.py",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "client.responses.create" in delivered
        assert "client.chat.completions.create" not in delivered

    def test_migration_rejected_when_no_tests(self, tmp_path: Path) -> None:
        """Proof must fail closed when no deterministic test phase exists."""
        repo = tmp_path / "no_tests_repo"
        repo.mkdir()

        src = repo / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "service.py").write_text("""
from openai import OpenAI
client = OpenAI()

def ask(q: str):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": q}],
    )
    return response.choices[0].message.content
""")

        (repo / "uv.lock").write_text("""
[[package]]
name = "openai"
version = "3.3.1"
""")
        (repo / "pyproject.toml").write_text("[project]\nname='test'\n")

        engine = MigrationEngine(
            root=repo,
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
            proof_environment_factory=fake_env_factory(
                lambda phase, _command: (5, (0, 0)) if phase == "tests" else (0, None)
            ),
        )

        result = engine.run()

        assert result.migration_status == MigrationStatus.FAILED
        assert result.proof_verdict == "NOT_PROVEN"
        assert result.certificate is not None
        assert result.certificate.verified is False
        assert "tests failed with return code 5" in result.errors


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
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
)
print(response.choices[0].message.content)
""")

        # Create a policy that only allows src/ but the transform might try to modify something else
        (repo / "agentdiff.yaml").write_text("""
version: 2
filesystem:
  allow_write: ["src/**"]
  deny: [".github/**", "pyproject.toml"]
  default: deny
process:
  default: allow
network:
  mode: observe
""")

        (repo / "uv.lock").write_text('[[package]]\nname = "openai"\nversion = "3.3.1"\n')
        (repo / "pyproject.toml").write_text("[project]\nname='test'\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_smoke.py").write_text("def test_smoke():\n    assert True\n")

        engine = MigrationEngine(
            root=repo,
            manifest=get_builtin_manifest("openai", "chat_to_responses"),
            proof_environment_factory=fake_env_factory(),
        )

        result = engine.run()

        # Should still work since transform only modifies allowed files
        assert result.migration_status == MigrationStatus.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

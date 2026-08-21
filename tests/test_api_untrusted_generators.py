"""End-to-end rejection tests for untrusted migration workers."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from agentdiff.api import MigrationEngine, get_builtin_manifest
from agentdiff.api.generation_runtime import PrivateGenerationRuntime
from agentdiff.api.generators import CustomCommandGenerator
from agentdiff.runtime import RuntimeControlLevel
from tests.fake_proof import fake_env_factory

if TYPE_CHECKING:
    from pathlib import Path


def _repository(tmp_path: Path) -> Path:
    source = tmp_path / "src"
    source.mkdir()
    (source / "app.py").write_text(
        """from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
)
print(response.choices[0].message.content)
""",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_smoke.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    return tmp_path


def test_successful_worker_that_changes_nothing_is_not_proven(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        generator=CustomCommandGenerator((sys.executable, "-c", "pass")),
        proof_environment_factory=fake_env_factory(),
    )

    result = engine.run()

    assert result.proof_verdict == "NOT_PROVEN"
    assert result.certificate is not None
    assert result.certificate.verified is False
    assert result.errors[0] == "EXPECTED FILE NOT MODIFIED: src/app.py"


def test_unexpected_workflow_change_is_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    command = (
        sys.executable,
        "-c",
        "from pathlib import Path; p=Path('.github/workflows/deploy.yml'); "
        "p.parent.mkdir(parents=True); p.write_text('unsafe: true\\n')",
    )
    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        generator=CustomCommandGenerator(command),
        proof_environment_factory=fake_env_factory(),
    )

    result = engine.run()

    assert result.proof_verdict == "NOT_PROVEN"
    assert result.certificate is not None
    assert result.certificate.policy_result == "DENY"
    assert result.certificate.verified is False
    assert result.unexpected_files == (".github/workflows/deploy.yml",)
    assert any(error.startswith("UNEXPECTED FILE MODIFICATION") for error in result.errors)
    assert not (root / ".github" / "workflows" / "deploy.yml").exists()


def test_private_generation_is_observation_not_an_os_sandbox(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    generator = CustomCommandGenerator((sys.executable, "-c", "pass"))
    engine = MigrationEngine(
        root,
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        generator=generator,
    )
    usages, impact = engine.scan_and_match()
    runtime = PrivateGenerationRuntime(engine.create_plan(usages, impact), generator)
    runtime.configure_source(root)

    result = runtime.run((generator.command_label,))
    runtime.close()

    host_capability = next(
        capability for capability in result.capabilities if capability.boundary == "host_repository"
    )
    assert result.enforcement == "private_workspace_observation"
    assert host_capability.control is RuntimeControlLevel.UNCONTROLLED
    assert "not an OS security boundary" in host_capability.mechanism

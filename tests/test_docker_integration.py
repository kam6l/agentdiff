"""Capability-gated real Docker trust-pipeline integration test."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agentdiff.api import MigrationEngine, MigrationStatus, VerificationLevel, get_builtin_manifest
from agentdiff.api.certificate import CertificateStatus, verify_certificate
from agentdiff.policy import load_policy
from agentdiff.promotion import PromotionEngine
from agentdiff.proof import ProofEngine, ProofVerdict
from agentdiff.runtime import DockerRuntime
from agentdiff.transaction import AgentRunTransaction

if TYPE_CHECKING:
    from collections.abc import Sequence


class DiagnosticDockerRuntime(DockerRuntime):
    """Surface daemon errors in the capability-gated CI test only."""

    def _docker_call(
        self,
        argv: Sequence[str],
        *,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        result = super()._docker_call(argv, capture_output=capture_output)
        if result.returncode != 0:
            operation = argv[1] if len(argv) > 1 else "unknown"
            print(f"Docker {operation} failed: {(result.stderr or result.stdout).strip()}")
        return result


def _docker_available() -> bool:
    executable = shutil.which("docker")
    if executable is None:
        return False
    result = subprocess.run(
        [executable, "info", "--format", "{{.ServerVersion}}"],
        shell=False,
        check=False,
        capture_output=True,
        timeout=5,
    )
    return result.returncode == 0


pytestmark = pytest.mark.skipif(
    os.environ.get("AGENTDIFF_DOCKER_TESTS") != "1" or not _docker_available(),
    reason="real Docker tests require AGENTDIFF_DOCKER_TESTS=1 and a running daemon",
)


def test_real_docker_run_prove_promote_keeps_host_untouched_until_gate(
    tmp_path: Path,
) -> None:
    target = tmp_path / "value.txt"
    target.write_text("base", encoding="utf-8")
    policy = load_policy(
        {
            "version": 2,
            "filesystem": {"allow_write": ["**"], "default": "allow"},
            "process": {"allow": ["python"], "default": "deny"},
            "network": {"mode": "off"},
            "proof": {
                "image": "python:3.12-slim",
                "network": False,
                "setup": [["python", "--version"]],
                "build": [["python", "-m", "compileall", "-q", "."]],
                "tests": [
                    [
                        "python",
                        "-c",
                        "from pathlib import Path; assert Path('value.txt').read_text() == 'agent'",
                    ]
                ],
            },
        }
    )
    runtime = DiagnosticDockerRuntime(tmp_path, image="python:3.12-slim")

    result = AgentRunTransaction(
        root=tmp_path,
        policy=policy,
        runtime=runtime,
        task="real Docker integration",
    ).run(
        [
            "python",
            "-c",
            "from pathlib import Path; Path('value.txt').write_text('agent')",
        ]
    )

    assert result.status == "passed", json.dumps(result.to_dict(), indent=2)
    assert target.read_text(encoding="utf-8") == "base"
    proof = ProofEngine(tmp_path, result.run_id).prove(timeout_seconds=120)
    assert proof.verdict is ProofVerdict.PROVEN
    promotion = PromotionEngine(tmp_path, result.run_id).promote(safe_only=True)
    assert promotion.status == "PROMOTED"
    assert target.read_text(encoding="utf-8") == "agent"


def test_real_docker_openai_migration_proves_and_verifies_certificate(tmp_path: Path) -> None:
    """The launch-wedge migration must earn PROVEN in the real container backend."""
    fixture = Path(__file__).parents[1] / "demos" / "openai-success"
    repository = tmp_path / "openai-success"
    shutil.copytree(fixture, repository)
    subprocess.run(["git", "init", "-b", "main"], cwd=repository, check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=AgentDiff CI",
            "-c",
            "user.email=ci@agentdiff.dev",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    original = (repository / "src" / "app.py").read_text(encoding="utf-8")

    result = MigrationEngine(
        repository,
        policy_path=repository / "agentdiff.yaml",
        manifest=get_builtin_manifest("openai", "chat_to_responses"),
        proof_timeout_seconds=180,
    ).run()

    assert result.migration_status is MigrationStatus.COMPLETED, result.errors
    assert result.proof_verdict == "PROVEN"
    assert result.verification_level is VerificationLevel.V3
    assert result.unexpected_files == ()
    assert result.certificate is not None
    assert result.certificate.verified is True
    assert result.certificate.git_base_sha not in {"", "unknown", "UNCOMMITTED"}
    assert (repository / "src" / "app.py").read_text(encoding="utf-8") == original

    certificate_path = (
        repository / ".agentdiff" / "certificates" / (f"{result.certificate.certificate_id}.json")
    )
    verification = verify_certificate(certificate_path, root=repository)
    assert verification.status is CertificateStatus.VALID, verification.reasons

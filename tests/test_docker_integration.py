"""Capability-gated real Docker trust-pipeline integration test."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


from agentdiff.policy import load_policy
from agentdiff.promotion import PromotionEngine
from agentdiff.proof import ProofEngine, ProofVerdict
from agentdiff.runtime import DockerRuntime
from agentdiff.transaction import AgentRunTransaction


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
    runtime = DockerRuntime(tmp_path, image="python:3.12-slim")

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

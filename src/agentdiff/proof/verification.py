"""Deterministic proof-plan discovery and bounded test-result parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from agentdiff.policy import Policy


@dataclass(frozen=True, slots=True)
class VerificationPlan:
    image: str
    network: bool
    setup: tuple[tuple[str, ...], ...]
    build: tuple[tuple[str, ...], ...]
    tests: tuple[tuple[str, ...], ...]
    source: str


def select_verification_plan(root: Path, policy: Policy) -> VerificationPlan:
    """Use explicit schema-v2 argv or conservative manifest-based defaults."""

    configured = bool(policy.proof.setup or policy.proof.build or policy.proof.tests)
    if configured:
        return VerificationPlan(
            image=policy.proof.image or "python:3.12-slim",
            network=policy.proof.network,
            setup=policy.proof.setup,
            build=policy.proof.build,
            tests=policy.proof.tests,
            source="policy",
        )
    if (root / "uv.lock").is_file():
        return VerificationPlan(
            image=policy.proof.image or "ghcr.io/astral-sh/uv:python3.12-bookworm-slim",
            network=policy.proof.network,
            setup=(("uv", "sync", "--frozen", "--no-cache"),),
            build=(("uv", "build"),),
            tests=(("uv", "run", "pytest", "-q"),),
            source="auto:uv",
        )
    if (root / "pyproject.toml").is_file():
        python = ".agentdiff-proof/venv/bin/python"
        return VerificationPlan(
            image=policy.proof.image or "python:3.12-slim",
            network=policy.proof.network,
            setup=(
                ("python", "-m", "venv", ".agentdiff-proof/venv"),
                (python, "-m", "pip", "install", "--no-cache-dir", "-e", "."),
            ),
            build=((python, "-m", "compileall", "-q", "src"),),
            tests=((python, "-m", "pytest", "-q"),),
            source="auto:python",
        )
    if (root / "package-lock.json").is_file():
        return VerificationPlan(
            image=policy.proof.image or "node:22-slim",
            network=policy.proof.network,
            setup=(("npm", "ci"),),
            build=(("npm", "run", "build", "--if-present"),),
            tests=(("npm", "test"),),
            source="auto:npm",
        )
    return VerificationPlan(
        image=policy.proof.image or "python:3.12-slim",
        network=policy.proof.network,
        setup=(),
        build=(),
        tests=(),
        source="unconfigured",
    )


def parse_test_counts(output: str) -> tuple[int | None, int | None]:
    """Parse common pytest/npm summaries for reporting only, never verdict logic."""

    passed = re.search(r"(?i)(\d+)\s+passed", output)
    failed = re.search(r"(?i)(\d+)\s+failed", output)
    if passed:
        passed_count = int(passed.group(1))
        failed_count = int(failed.group(1)) if failed else 0
        return passed_count, passed_count + failed_count
    return None, None

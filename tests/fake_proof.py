"""Deterministic fake clean-room proof environment for unit tests.

``ProofEngine`` accepts an ``environment_factory``; tests inject this fake so
the full proof/promotion/repair pipeline can be exercised without a Docker
daemon. The fake never decides anything itself — it simply reports a
programmed return code per phase, which is what a deterministic clean room
would produce for the test fixture.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from pathlib import Path

from agentdiff.proof import ProofPhaseResult

Runner = Callable[[str, tuple[str, ...]], tuple[int, tuple[int, int] | None]]


class FakeProofEnvironment:
    """One fake clean-room container with a scripted per-phase outcome."""

    def __init__(
        self,
        *,
        workspace: Path,
        image: str,
        network: bool,
        runner: Runner | None = None,
    ) -> None:
        self.workspace = workspace
        self.image = image
        self.network = network
        self.runner = runner
        self.closed = False

    def start(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "backend": "fake",
            "image": self.image,
            "network": "bridge" if self.network else "none",
            "clean_environment": True,
            "isolation_limit": "fake environment for tests",
        }

    def run_phase(
        self,
        phase: str,
        command: list[str] | tuple[str, ...],
        *,
        timeout_seconds: float,
    ) -> ProofPhaseResult:
        del timeout_seconds
        returncode = 0
        tests: tuple[int, int] | None = (1, 1)
        if self.runner is not None:
            outcome = self.runner(phase, tuple(command))
            returncode = outcome[0]
            tests = outcome[1] if len(outcome) > 1 else (1, 1)
        return ProofPhaseResult(
            phase=phase,
            command=tuple(command),
            status="PASS" if returncode == 0 else "FAIL",
            returncode=returncode,
            duration_seconds=0.01,
            output_sha256="0" * 64,
            output_bytes=0,
            tests_passed=tests[0] if tests else None,
            tests_total=tests[1] if tests else None,
            detail="fake environment",
        )

    def close(self) -> None:
        self.closed = True


def fake_env_factory(runner: Runner | None = None) -> Callable[..., FakeProofEnvironment]:
    """Return an environment factory for :class:`ProofEngine`."""

    def factory(*, workspace: Path, image: str, network: bool) -> FakeProofEnvironment:
        return FakeProofEnvironment(
            workspace=workspace,
            image=image,
            network=network,
            runner=runner,
        )

    return factory


def counting_runner(fail_first: int = 1) -> tuple[Runner, list[int]]:
    """Runner that fails the first ``fail_first`` test phases, then passes."""
    calls: list[int] = []

    def runner(phase: str, command: tuple[str, ...]) -> tuple[int, tuple[int, int] | None]:
        calls.append(1)
        if len(calls) <= fail_first:
            return (1, (0, 1))
        return (0, (1, 1))

    return runner, calls

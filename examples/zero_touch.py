"""Zero-touch AgentDiff automation (programmatic API).

This example shows the same pipeline ``agentdiff wrap`` runs on the command
line, as a Python API: warm workspace -> observed transaction -> clean-room
proof -> bounded repair -> promotion.

The example uses a deterministic fake proof environment so it runs without a
Docker daemon. Replace ``environment_factory`` with
``agentdiff.proof.environment.DockerProofEnvironment`` (the default) for real
clean-room proof.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agentdiff.policy import load_policy
from agentdiff.promotion import PromotionEngine
from agentdiff.proof import ProofEngine, ProofPhaseResult, ProofVerdict
from agentdiff.repair import RepairLoop
from agentdiff.sidecar import Notification, Notifier
from agentdiff.transaction import AgentRunTransaction
from agentdiff.workspace import WarmWorkspaceFactory, compute_identity


class _FakeProofEnvironment:
    """Deterministic stand-in for the Docker clean room (no daemon needed)."""

    def __init__(self, *, workspace: Path, image: str, network: bool) -> None:
        del workspace, image, network

    def start(self) -> dict[str, object]:
        return {"schema_version": 1, "backend": "fake", "clean_environment": True}

    def run_phase(
        self, phase: str, command: list[str], *, timeout_seconds: float
    ) -> ProofPhaseResult:
        del timeout_seconds
        return ProofPhaseResult(
            phase=phase,
            command=tuple(command),
            status="PASS",
            returncode=0,
            duration_seconds=0.01,
            output_sha256="0" * 64,
            tests_passed=1,
            tests_total=1,
        )

    def close(self) -> None:
        return None


def _fake_env_factory(*, workspace: Path, image: str, network: bool) -> _FakeProofEnvironment:
    return _FakeProofEnvironment(workspace=workspace, image=image, network=network)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agentdiff-zero-touch-") as temporary:
        root = Path(temporary)
        (root / "value.txt").write_text("base", encoding="utf-8")
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
                            "from pathlib import Path; "
                            "assert Path('value.txt').read_text() == 'fixed'",
                        ]
                    ],
                },
            }
        )

        notifier = Notifier(root, echo=True)
        factory = WarmWorkspaceFactory(root)
        identity = compute_identity(root, policy=policy)
        workspace = factory.create_workspace(identity)

        def base_preparer(destination: Path) -> None:
            from agentdiff.sidecar.adapters import _copy_writable

            _copy_writable(workspace.base.path, destination)

        try:
            # 1. The agent runs in a private warm workspace.
            result = AgentRunTransaction(
                root=workspace.path,
                policy=policy,
                task="fix the value",
            ).run(
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('value.txt').write_text('fixed')",
                ]
            )

            # 2. Clean-room proof (fake environment here; use the Docker
            #    environment factory for real clean-room proof).
            proof = ProofEngine(
                workspace.path,
                result.run_id,
                environment_factory=_fake_env_factory,
                base_preparer=base_preparer,
            ).prove()
            if proof.verdict is not ProofVerdict.PROVEN:
                # 3. Bounded repair until proof passes or scope changes.
                outcome = RepairLoop(
                    workspace.path,
                    result.run_id,
                    policy=policy,
                    base_preparer=base_preparer,
                    repair_command_builder=None,  # packet written for the agent
                ).run()
                notifier.notify(
                    Notification(
                        kind="human" if outcome.status == "NEEDS_HUMAN" else "retry",
                        title=f"Repair outcome: {outcome.status}",
                        message=outcome.human_reason,
                        run_id=result.run_id,
                    )
                )
                return 0

            # 4. Promote the proven change to the host repository.
            promotion = PromotionEngine(
                root,
                result.run_id,
                store_root=workspace.path,
            ).promote(safe_only=True)
            print(f"Promotion: {promotion.status}")
            assert (root / "value.txt").read_text(encoding="utf-8") == "fixed"
            return 0
        finally:
            workspace.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""Private workspace runtime for untrusted migration generators."""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from agentdiff.runtime import (
    CleanupReport,
    RuntimeCapability,
    RuntimeControlLevel,
    RuntimeResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from agentdiff.api.generators import GenerationResult, MigrationGenerator
    from agentdiff.api.models import MigrationPlan
    from agentdiff.runtime import OwnedProcess


class PrivateGenerationRuntime:
    """Run a generator against a private copy and expose only its observed result."""

    def __init__(self, plan: MigrationPlan, generator: MigrationGenerator) -> None:
        self.plan = plan
        self.generator = generator
        self._source_dir: Path | None = None
        self._temporary_root: Path | None = None
        self.generation_result: GenerationResult | None = None

    def configure_source(self, source_dir: str | Path) -> None:
        unresolved = Path(source_dir)
        if unresolved.is_symlink():
            raise ValueError("generation source snapshot must be a real directory")
        candidate = unresolved.resolve(strict=True)
        if not candidate.is_dir():
            raise ValueError("generation source snapshot must be a real directory")
        self._source_dir = candidate

    def configure_safety(self, controller: Any) -> None:
        del controller

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        stdin: int | IO[Any] | None = None,
        stdout: int | IO[Any] | None = None,
        stderr: int | IO[Any] | None = None,
    ) -> RuntimeResult:
        del stdin, stdout, stderr
        command = tuple(argv)
        if command != (self.generator.command_label,):
            raise ValueError("generation runtime command does not match the configured worker")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self._source_dir is None:
            raise RuntimeError("generation runtime requires a sealed source snapshot")
        if self._temporary_root is not None:
            raise RuntimeError("generation runtime can run only once")

        started = time.monotonic()
        temporary_root = Path(tempfile.mkdtemp(prefix="agentdiff-generation-"))
        workspace = temporary_root / "workspace"
        workspace.mkdir(mode=0o700)
        shutil.copytree(self._source_dir, workspace, dirs_exist_ok=True, symlinks=False)
        self._temporary_root = temporary_root
        self.generation_result = self.generator.generate(self.plan, workspace)
        duration = time.monotonic() - started
        timed_out = timeout_seconds is not None and duration > timeout_seconds
        returncode = 124 if timed_out else self.generation_result.returncode
        return RuntimeResult(
            argv=command,
            cwd=str(workspace),
            returncode=returncode,
            timed_out=timed_out,
            duration_seconds=duration,
            backend="agentdiff-private-generation",
            enforcement="private_workspace_observation",
            observation_root=str(workspace),
            capabilities=(
                RuntimeCapability(
                    "host_repository",
                    RuntimeControlLevel.UNCONTROLLED,
                    "the generator runs with host process permissions; the private working "
                    "directory is not an OS security boundary",
                ),
                RuntimeCapability(
                    "patch_trust",
                    RuntimeControlLevel.OBSERVED,
                    "all generated mutations are captured as untrusted evidence",
                ),
            ),
        )

    def cleanup(
        self,
        processes: Iterable[OwnedProcess],
        *,
        grace_period_seconds: float = 1.0,
    ) -> CleanupReport:
        del processes, grace_period_seconds
        return CleanupReport()

    def close(self) -> None:
        if self._temporary_root is None:
            return
        resolved = self._temporary_root.resolve(strict=False)
        expected_parent = Path(tempfile.gettempdir()).resolve(strict=True)
        if resolved.parent != expected_parent or not resolved.name.startswith(
            "agentdiff-generation-"
        ):
            raise RuntimeError("refusing to remove an unexpected generation workspace")
        shutil.rmtree(resolved, ignore_errors=False)
        self._temporary_root = None

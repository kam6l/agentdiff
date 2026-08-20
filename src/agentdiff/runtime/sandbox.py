"""Anthropic Sandbox Runtime adapter with AgentDiff observation evidence."""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from .base import RuntimeCapabilities, RuntimeControlLevel
from .local import LocalRuntime

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .base import CleanupReport, OwnedProcess, RuntimeResult


class SandboxRuntime:
    """Run argv through a preinstalled Anthropic ``srt`` executable.

    AgentDiff still performs its own process and port observation around the
    wrapper. Enforcement claims are scoped to the external Sandbox Runtime;
    this adapter does not reimplement or silently emulate its OS controls.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        executable: str | os.PathLike[str] = "srt",
        settings: str | os.PathLike[str] | None = None,
        observe_ports: bool = True,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        candidate = os.fspath(executable)
        located = shutil.which(candidate)
        if located is None:
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                raise FileNotFoundError(f"Sandbox Runtime executable not found: {candidate}")
            located = str(path.resolve(strict=True))
        self.executable = Path(located).resolve(strict=True)
        if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
            raise PermissionError(
                f"Sandbox Runtime executable is not executable: {self.executable}"
            )
        self.settings: Path | None = None
        if settings is not None:
            configured = Path(settings).expanduser().resolve(strict=True)
            if not configured.is_file():
                raise FileNotFoundError(f"Sandbox Runtime settings are not a file: {configured}")
            self.settings = configured
        self._local = LocalRuntime(
            self.root,
            observe_ports=observe_ports,
            poll_interval_seconds=poll_interval_seconds,
        )

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Report only guarantees this adapter actually provides.

        Isolation is delegated to the external Sandbox Runtime; AgentDiff
        itself observes the host around the wrapper and does not reimplement
        or silently emulate the external OS controls.
        """
        return RuntimeCapabilities(
            backend="anthropic-sandbox-runtime",
            filesystem=RuntimeControlLevel.OBSERVED,
            host_repository=RuntimeControlLevel.OBSERVED,
            network=RuntimeControlLevel.OBSERVED,
            processes=RuntimeControlLevel.OBSERVED,
            resources=RuntimeControlLevel.UNCONTROLLED,
            privileges=RuntimeControlLevel.UNCONTROLLED,
            private_workspace=False,
            supports_live_safety=True,
            supports_source_snapshot=False,
        )

    def configure_source(self, source_dir: str | os.PathLike[str]) -> None:
        """The Sandbox Runtime executes on the host root; no source copy is used."""

    def configure_safety(self, controller: Any) -> None:
        self._local.configure_safety(controller)

    def close(self) -> None:
        self._local.close()

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        stdin: int | IO[Any] | None = None,
        stdout: int | IO[Any] | None = None,
        stderr: int | IO[Any] | None = None,
    ) -> RuntimeResult:
        command = tuple(argv)
        if not command:
            raise ValueError("argv must contain an executable")
        if not all(isinstance(argument, str) for argument in command):
            raise TypeError("every argv item must be a string")
        prefix = [str(self.executable)]
        if self.settings is not None:
            prefix.extend(("--settings", str(self.settings)))
        wrapped = (*prefix, *command)
        result = self._local.run(
            wrapped,
            timeout_seconds=timeout_seconds,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )
        return replace(
            result,
            argv=command,
            backend="anthropic-sandbox-runtime",
            # This proves delegation through the configured executable, not
            # which OS controls its version, platform, and settings applied.
            enforcement="external_sandbox_requested",
            wrapper_argv=wrapped,
        )

    def cleanup(
        self,
        processes: Iterable[OwnedProcess],
        *,
        grace_period_seconds: float = 1.0,
    ) -> CleanupReport:
        return self._local.cleanup(
            processes,
            grace_period_seconds=grace_period_seconds,
        )

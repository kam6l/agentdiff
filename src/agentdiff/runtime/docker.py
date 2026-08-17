"""Docker-backed private writable workspace runtime.

Docker is treated as a capability-bearing container boundary, not a virtual
machine. The host repository is never mounted into the container. AgentDiff
mounts only a private copy, drops Linux capabilities, disables networking by
default, and records the exact requested controls. Effective isolation still
depends on the Docker daemon, kernel, platform, and administrator policy.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess  # nosec B404 -- exact Docker CLI argv is the backend contract
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from .base import (
    CleanupReport,
    OwnedProcess,
    RuntimeCapabilities,
    RuntimeCapability,
    RuntimeControlLevel,
    RuntimeResult,
)
from .local import LocalRuntime
from .materialize import WorkspaceMaterializer

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class DockerRuntime:
    """Execute exact argv in an ephemeral, resource-bounded Docker container."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        image: str = "python:3.12-slim",
        executable: str | os.PathLike[str] = "docker",
        cpus: float = 1.0,
        memory: str = "512m",
        pids_limit: int = 64,
        network: str = "none",
        environment_allowlist: Sequence[str] = (),
        poll_interval_seconds: float = 0.1,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        located = shutil.which(os.fspath(executable))
        if located is None:
            candidate = Path(executable).expanduser()
            if not candidate.is_absolute() or not candidate.is_file():
                raise FileNotFoundError(f"Docker executable not found: {executable}")
            located = str(candidate.resolve(strict=True))
        if not image or any(character in image for character in "\r\n\x00"):
            raise ValueError("Docker image must be a non-empty single-line value")
        if cpus <= 0:
            raise ValueError("cpus must be greater than zero")
        if pids_limit <= 0:
            raise ValueError("pids_limit must be greater than zero")
        if network not in {"none", "bridge"}:
            raise ValueError("Docker network must be none or bridge")
        names = tuple(dict.fromkeys(environment_allowlist))
        if any(not _ENV_NAME.fullmatch(name) for name in names):
            raise ValueError("invalid environment allowlist name")
        self.executable = str(Path(located).resolve(strict=True))
        self.image = image
        self.cpus = cpus
        self.memory = memory
        self.pids_limit = pids_limit
        self.network = network
        self.environment_allowlist = names
        self.poll_interval_seconds = poll_interval_seconds
        self._source_dir: Path | None = None
        self._workspace: Path | None = None
        self._temporary_root: Path | None = None
        self._safety_controller: Any | None = None
        self._container_id: str | None = None
        self._materialization_report: Any | None = None

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Explicit capability metadata available before any execution."""
        network_level = (
            RuntimeControlLevel.BLOCKED if self.network == "none" else RuntimeControlLevel.SANDBOXED
        )
        return RuntimeCapabilities(
            backend="docker",
            filesystem=RuntimeControlLevel.SANDBOXED,
            host_repository=RuntimeControlLevel.SANDBOXED,
            network=network_level,
            processes=RuntimeControlLevel.SANDBOXED,
            resources=RuntimeControlLevel.SANDBOXED,
            privileges=RuntimeControlLevel.SANDBOXED,
            private_workspace=True,
            supports_live_safety=True,
            supports_source_snapshot=True,
        )

    def configure_source(self, source_dir: str | Path) -> None:
        """Use the transaction's sealed pre-run source copy as container input."""

        candidate = Path(source_dir).resolve(strict=True)
        if not candidate.is_dir() or candidate.is_symlink():
            raise ValueError("Docker source snapshot must be a real directory")
        self._source_dir = candidate

    def configure_safety(self, controller: Any) -> None:
        self._safety_controller = controller

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
            raise ValueError("argv must not be empty")
        if not all(isinstance(argument, str) for argument in command):
            raise TypeError("every argv item must be a string")
        if self._workspace is not None:
            raise RuntimeError("a DockerRuntime instance can run only once")
        if self._source_dir is None:
            raise RuntimeError("DockerRuntime requires a transaction source snapshot")

        temporary_root = Path(tempfile.mkdtemp(prefix="agentdiff-docker-"))
        workspace = temporary_root / "workspace"
        workspace.mkdir(mode=0o700)
        # Materialize the private writable source copy through the validated
        # WorkspaceMaterializer instead of a raw copytree: modes are preserved
        # and unsafe entries are rejected, never silently followed or dropped.
        materialized = WorkspaceMaterializer().materialize(self._source_dir, workspace)
        self._materialization_report = materialized
        self._temporary_root = temporary_root
        self._workspace = workspace
        container_name = f"agentdiff-{secrets.token_hex(8)}"
        user = self._container_user()
        config = self._runtime_config(user)
        create_argv = self._create_argv(container_name, workspace, user, command)
        container_id: str | None = None
        try:
            created = self._docker_call(create_argv, capture_output=True)
            if created.returncode != 0:
                message = (created.stderr or created.stdout or "docker create failed").strip()
                raise OSError(message)
            container_id = created.stdout.strip()
            if not container_id or any(character.isspace() for character in container_id):
                raise OSError("Docker returned an invalid container id")
            self._container_id = container_id
            local = LocalRuntime(
                workspace,
                observe_ports=False,
                poll_interval_seconds=self.poll_interval_seconds,
                safety_controller=self._safety_controller,
            )
            attached = local.run(
                [self.executable, "start", "--attach", container_id],
                timeout_seconds=timeout_seconds,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
            )
            image_digest = self._image_digest()
            return replace(
                attached,
                argv=command,
                cwd="/workspace",
                backend="docker",
                enforcement="isolated_private_workspace",
                wrapper_argv=tuple(create_argv),
                capabilities=self._capabilities(),
                safety=(
                    self._safety_controller.report.to_dict()
                    if self._safety_controller is not None
                    else None
                ),
                container_id=container_id,
                image=self.image,
                image_digest=image_digest,
                runtime_config=config,
                observation_root=str(workspace),
            )
        finally:
            if container_id is not None:
                self._docker_call(
                    [self.executable, "rm", "--force", "--volumes", container_id],
                    capture_output=True,
                )

    def close(self) -> None:
        """Destroy the private host-side workspace after evidence collection."""

        if self._temporary_root is not None:
            resolved = self._temporary_root.resolve(strict=False)
            expected_parent = Path(tempfile.gettempdir()).resolve(strict=True)
            if resolved.parent != expected_parent or not resolved.name.startswith(
                "agentdiff-docker-"
            ):
                raise RuntimeError("refusing to remove an unexpected Docker workspace")
            shutil.rmtree(resolved, ignore_errors=False)
            self._temporary_root = None
            self._workspace = None

    def cleanup(
        self,
        processes: Iterable[OwnedProcess],
        *,
        grace_period_seconds: float = 1.0,
    ) -> CleanupReport:
        """Clean only host-side Docker CLI process identities."""

        root = self._workspace or self.root
        return LocalRuntime(root, observe_ports=False).cleanup(
            processes,
            grace_period_seconds=grace_period_seconds,
        )

    def _create_argv(
        self,
        name: str,
        workspace: Path,
        user: str,
        command: tuple[str, ...],
    ) -> list[str]:
        mount = f"type=bind,src={workspace},dst=/workspace,rw"
        argv = [
            self.executable,
            "create",
            "--pull",
            "missing",
            "--name",
            name,
            "--workdir",
            "/workspace",
            "--user",
            user,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--network",
            self.network,
            "--cpus",
            str(self.cpus),
            "--memory",
            self.memory,
            "--pids-limit",
            str(self.pids_limit),
            "--stop-timeout",
            "2",
            "--init",
            "--mount",
            mount,
            "--env",
            "HOME=/tmp",
        ]
        for name in self.environment_allowlist:
            argv.extend(("--env", name))
        argv.append(self.image)
        argv.extend(command)
        return argv

    def _runtime_config(self, user: str) -> dict[str, Any]:
        config: dict[str, Any] = {
            "schema_version": 1,
            "image": self.image,
            "user": user,
            "read_only_rootfs": True,
            "private_workspace": True,
            "host_repository_mounted": False,
            "docker_socket_mounted": False,
            "cap_drop": ["ALL"],
            "no_new_privileges": True,
            "network": self.network,
            "cpus": self.cpus,
            "memory": self.memory,
            "pids_limit": self.pids_limit,
            "environment_allowlist": list(self.environment_allowlist),
            "ephemeral_container": True,
            "capabilities": self.capabilities.to_dict(),
        }
        if self._materialization_report is not None:
            report = self._materialization_report
            config["materialization"] = {
                "strategy_used": report.strategy_used,
                "files_materialized": report.files_materialized,
                "bytes_materialized": report.bytes_materialized,
                "duration_seconds": report.duration_seconds,
            }
        return config

    def _docker_call(
        self,
        argv: Sequence[str],
        *,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # nosec B603
            list(argv),
            shell=False,
            check=False,
            capture_output=capture_output,
            text=True,
            env=self._docker_environment(),
        )

    def _docker_environment(self) -> dict[str, str]:
        allowed = {
            name: os.environ[name] for name in self.environment_allowlist if name in os.environ
        }
        for required in ("PATH", "SystemRoot", "TEMP", "TMP"):
            if required in os.environ:
                allowed.setdefault(required, os.environ[required])
        return allowed

    def _image_digest(self) -> str | None:
        inspected = self._docker_call(
            [
                self.executable,
                "image",
                "inspect",
                "--format",
                "{{json .RepoDigests}}",
                self.image,
            ],
            capture_output=True,
        )
        if inspected.returncode != 0:
            return None
        value = inspected.stdout.strip()
        return value or None

    @staticmethod
    def _container_user() -> str:
        getuid = getattr(os, "getuid", None)
        getgid = getattr(os, "getgid", None)
        if getuid is not None and getgid is not None:
            uid = int(getuid())
            gid = int(getgid())
            if uid != 0:
                return f"{uid}:{gid}"
        return "65532:65532"

    def _capabilities(self) -> tuple[RuntimeCapability, ...]:
        network_level = (
            RuntimeControlLevel.BLOCKED if self.network == "none" else RuntimeControlLevel.SANDBOXED
        )
        return (
            RuntimeCapability(
                "host_repository",
                RuntimeControlLevel.SANDBOXED,
                "the container receives only a private copy; the host repository is not mounted",
            ),
            RuntimeCapability(
                "filesystem_mutations",
                RuntimeControlLevel.SANDBOXED,
                "writes remain inside the private bind-mounted workspace",
            ),
            RuntimeCapability(
                "network",
                network_level,
                "Docker network mode is explicit; none is the default",
            ),
            RuntimeCapability(
                "processes",
                RuntimeControlLevel.SANDBOXED,
                "Docker PID namespace plus a configured pids limit",
            ),
            RuntimeCapability(
                "resources",
                RuntimeControlLevel.BLOCKED,
                "Docker CPU, memory, PID, and duration limits are requested",
            ),
            RuntimeCapability(
                "privileges",
                RuntimeControlLevel.BLOCKED,
                "non-root user, cap-drop ALL, and no-new-privileges are requested",
            ),
            RuntimeCapability(
                "container_boundary",
                RuntimeControlLevel.SANDBOXED,
                "container isolation is not a VM boundary and depends on the Docker daemon/kernel",
            ),
        )

"""Fail-closed runtimes for migration generators."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Protocol, runtime_checkable

from agentdiff.api.generators import (
    CustomCommandGenerator,
    DeterministicASTGenerator,
    GenerationResult,
)
from agentdiff.runtime import (
    CleanupReport,
    DockerLifecycleError,
    DockerRuntime,
    RuntimeCapability,
    RuntimeControlLevel,
    RuntimeResult,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from agentdiff.api.models import MigrationPlan
    from agentdiff.runtime import OwnedProcess


@runtime_checkable
class GeneratorRuntime(Protocol):
    """Runtime contract used by the migration transaction."""

    backend: str
    enforcement: str
    generation_result: GenerationResult | None

    @property
    def command_argv(self) -> tuple[str, ...]:
        """Return the one exact argv sequence this runtime accepts."""
        ...

    def configure_source(self, source_dir: str | Path) -> None:
        """Configure the transaction's sealed source snapshot."""
        ...

    def configure_safety(self, controller: Any) -> None:
        """Configure live safety observation where supported."""
        ...

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        stdin: int | IO[Any] | None = None,
        stdout: int | IO[Any] | None = None,
        stderr: int | IO[Any] | None = None,
    ) -> RuntimeResult:
        """Run the configured generator and return runtime evidence."""
        ...

    def cleanup(
        self,
        processes: Iterable[OwnedProcess],
        *,
        grace_period_seconds: float = 1.0,
    ) -> CleanupReport:
        """Clean up runtime-owned process identities."""
        ...

    def close(self) -> None:
        """Destroy private runtime state."""
        ...


class PrivateGenerationRuntime:
    """Run only AgentDiff's trusted deterministic generator in process."""

    backend = "agentdiff-private-generation"
    enforcement = "private_workspace_observation"

    def __init__(self, plan: MigrationPlan, generator: DeterministicASTGenerator) -> None:
        if type(generator) is not DeterministicASTGenerator:
            raise TypeError("PrivateGenerationRuntime accepts only DeterministicASTGenerator")
        self.plan = plan
        self.generator = generator
        self._source_dir: Path | None = None
        self._temporary_root: Path | None = None
        self.generation_result: GenerationResult | None = None

    @property
    def command_argv(self) -> tuple[str, ...]:
        """Return the synthetic command used for deterministic policy evidence."""

        return (self.generator.command_label,)

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
        if command != self.command_argv:
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


class _BoundedOutputCapture:
    """Drain one binary pipe while retaining at most a fixed number of bytes."""

    def __init__(self, limit_bytes: int) -> None:
        read_fd, write_fd = os.pipe()
        self.reader = os.fdopen(read_fd, "rb", buffering=0)
        self.writer = os.fdopen(write_fd, "wb", buffering=0)
        self.limit_bytes = limit_bytes
        self.captured = bytearray()
        self.total_bytes = 0
        self.digest = hashlib.sha256()
        self.complete = False
        self._thread = threading.Thread(target=self._drain, daemon=True)

    @property
    def limited(self) -> bool:
        return self.total_bytes > self.limit_bytes

    def start(self) -> None:
        self._thread.start()

    def finish(self) -> None:
        self.writer.close()
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            self.reader.close()
            self._thread.join(timeout=1.0)
            raise OSError("Docker generator output capture did not close")
        if not self.complete:
            raise OSError("Docker generator output capture did not close")

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_bytes": self.total_bytes,
            "captured_bytes": len(self.captured),
            "sha256": self.digest.hexdigest(),
            "limited": self.limited,
            "complete": self.complete,
        }

    def _drain(self) -> None:
        try:
            with self.reader:
                while chunk := self.reader.read(64 * 1024):
                    self.total_bytes += len(chunk)
                    self.digest.update(chunk)
                    remaining = self.limit_bytes - len(self.captured)
                    if remaining > 0:
                        self.captured.extend(chunk[:remaining])
            self.complete = True
        except OSError:
            return


class DockerGeneratorRuntime:
    """Run an exact-argv generator in a hardened private Docker workspace."""

    backend = "docker"
    enforcement = "isolated_private_workspace"

    def __init__(
        self,
        root: str | Path,
        plan: MigrationPlan,
        generator: CustomCommandGenerator,
        *,
        image: str = "python:3.12-slim",
        output_limit_bytes_per_stream: int = 1_000_000,
        execution_timeout_seconds: float = 900.0,
        control_timeout_seconds: float = 120.0,
        docker_runtime_factory: Callable[..., DockerRuntime] = DockerRuntime,
    ) -> None:
        if not isinstance(generator, CustomCommandGenerator):
            raise TypeError("DockerGeneratorRuntime requires a CustomCommandGenerator")
        if (
            not image
            or image.startswith("-")
            or any(character in image for character in "\r\n\x00")
        ):
            raise ValueError(
                "generator image must be a non-empty single-line value and cannot be an option"
            )
        if output_limit_bytes_per_stream <= 0:
            raise ValueError("output_limit_bytes_per_stream must be greater than zero")
        if execution_timeout_seconds <= 0:
            raise ValueError("execution_timeout_seconds must be greater than zero")
        if control_timeout_seconds <= 0:
            raise ValueError("control_timeout_seconds must be greater than zero")
        self.root = Path(root).expanduser().resolve(strict=True)
        self.image = image
        self.output_limit_bytes_per_stream = output_limit_bytes_per_stream
        self.execution_timeout_seconds = float(execution_timeout_seconds)
        self.control_timeout_seconds = float(control_timeout_seconds)
        self.plan = plan
        self.generator = generator
        self.generation_result: GenerationResult | None = None
        self._runtime = docker_runtime_factory(
            self.root,
            image=image,
            network="none",
            environment_allowlist=(),
            control_timeout_seconds=self.control_timeout_seconds,
        )

    @property
    def command_argv(self) -> tuple[str, ...]:
        """Return the user-supplied argv without shell parsing or rewriting."""

        return self.generator.argv

    def configure_source(self, source_dir: str | Path) -> None:
        self._runtime.configure_source(source_dir)

    def configure_safety(self, controller: Any) -> None:
        self._runtime.configure_safety(controller)

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
        if command != self.command_argv:
            raise ValueError("generation runtime command does not match the configured argv")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if stdout is not None or stderr is not None:
            raise ValueError("Docker generator output redirection is not supported")
        effective_timeout = (
            self.execution_timeout_seconds
            if timeout_seconds is None
            else min(timeout_seconds, self.execution_timeout_seconds)
        )
        stdout_capture = _BoundedOutputCapture(self.output_limit_bytes_per_stream)
        stderr_capture = _BoundedOutputCapture(self.output_limit_bytes_per_stream)
        stdout_capture.start()
        stderr_capture.start()
        try:
            try:
                result = self._runtime.run(
                    command,
                    timeout_seconds=effective_timeout,
                    stdin=stdin,
                    stdout=stdout_capture.writer,
                    stderr=stderr_capture.writer,
                )
            finally:
                try:
                    stdout_capture.finish()
                finally:
                    stderr_capture.finish()
        except DockerLifecycleError as error:
            self.generation_result = GenerationResult(
                success=False,
                generator=self.generator.name,
                strategy=self.generator.strategy,
                errors=(f"Docker generator {error.stage} timed out",),
                returncode=124,
            )
            raise
        except OSError:
            self.generation_result = GenerationResult(
                success=False,
                generator=self.generator.name,
                strategy=self.generator.strategy,
                errors=("Docker generator runtime failed",),
                returncode=1,
            )
            raise

        output_limited = stdout_capture.limited or stderr_capture.limited
        runtime_config = {
            **(result.runtime_config or {}),
            "generator_execution_timeout_seconds": effective_timeout,
            "generator_output": {
                "limit_bytes_per_stream": self.output_limit_bytes_per_stream,
                "limited": output_limited,
                "stdout": stdout_capture.to_dict(),
                "stderr": stderr_capture.to_dict(),
            },
        }
        result = replace(result, runtime_config=runtime_config)
        if output_limited and not result.timed_out:
            result = replace(result, returncode=125)
        self._validate_isolation(result, command)
        errors: tuple[str, ...]
        if result.timed_out:
            errors = ("Docker generator start/attach timed out",)
        elif output_limited:
            errors = ("Docker generator output exceeded the safety limit",)
        elif result.returncode != 0:
            errors = (f"custom generator exited with status {result.returncode}",)
        else:
            errors = ()
        self.generation_result = GenerationResult(
            success=result.returncode == 0 and not result.timed_out,
            generator=self.generator.name,
            strategy=self.generator.strategy,
            errors=errors,
            returncode=result.returncode,
        )
        return result

    def cleanup(
        self,
        processes: Iterable[OwnedProcess],
        *,
        grace_period_seconds: float = 1.0,
    ) -> CleanupReport:
        return self._runtime.cleanup(
            processes,
            grace_period_seconds=grace_period_seconds,
        )

    def close(self) -> None:
        self._runtime.close()

    def _validate_isolation(
        self,
        result: RuntimeResult,
        command: tuple[str, ...],
    ) -> None:
        config = result.runtime_config or {}
        user = str(config.get("user", ""))
        cap_drop = config.get("cap_drop")
        cap_drop_all = cap_drop == ["ALL"]
        observation_root: Path | None = None
        if result.observation_root is not None:
            try:
                observation_root = Path(result.observation_root).resolve(strict=True)
            except OSError:
                observation_root = None
        wrapper = result.wrapper_argv or ()
        image_index = len(wrapper) - len(command) - 1
        docker_options = wrapper[:image_index] if image_index >= 0 else ()
        mount = f"type=bind,src={result.observation_root},dst=/workspace"

        def has_pair(flag: str, value: str) -> bool:
            return any(
                docker_options[index : index + 2] == (flag, value)
                for index in range(len(docker_options) - 1)
            )

        environment_values = tuple(
            docker_options[index + 1]
            for index, argument in enumerate(docker_options[:-1])
            if argument == "--env"
        )
        non_root_user = user.split(":", maxsplit=1)[0] not in {"", "0", "root"}
        output_evidence_valid = self._valid_output_evidence(config.get("generator_output"))

        isolated = (
            result.argv == command
            and result.backend == "docker"
            and result.enforcement == "isolated_private_workspace"
            and result.image == self.image
            and observation_root is not None
            and observation_root != self.root
            and self.root not in observation_root.parents
            and observation_root not in self.root.parents
            and config.get("private_workspace") is True
            and config.get("host_repository_mounted") is False
            and config.get("docker_socket_mounted") is False
            and config.get("read_only_rootfs") is True
            and config.get("no_new_privileges") is True
            and config.get("network") == "none"
            and config.get("ephemeral_container") is True
            and config.get("control_timeout_seconds") == self.control_timeout_seconds
            and isinstance(config.get("generator_execution_timeout_seconds"), (int, float))
            and float(config["generator_execution_timeout_seconds"]) > 0
            and float(config["generator_execution_timeout_seconds"])
            <= self.execution_timeout_seconds
            and output_evidence_valid
            and config.get("environment_allowlist") == []
            and isinstance(config.get("cpus"), (int, float))
            and float(config["cpus"]) > 0
            and isinstance(config.get("memory"), str)
            and bool(config["memory"])
            and isinstance(config.get("pids_limit"), int)
            and int(config["pids_limit"]) > 0
            and cap_drop_all
            and non_root_user
            and image_index >= 0
            and wrapper[image_index] == self.image
            and "--read-only" in docker_options
            and has_pair("--user", user)
            and has_pair("--cap-drop", "ALL")
            and has_pair("--security-opt", "no-new-privileges")
            and has_pair("--network", "none")
            and has_pair("--mount", mount)
            and has_pair("--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m")
            and has_pair("--cpus", str(config["cpus"]))
            and has_pair("--memory", str(config["memory"]))
            and has_pair("--pids-limit", str(config["pids_limit"]))
            and environment_values == ("HOME=/tmp",)
            and docker_options.count("--mount") == 1
            and "--volume" not in docker_options
            and "-v" not in docker_options
            and "--privileged" not in docker_options
            and "--cap-add" not in docker_options
            and "docker.sock" not in " ".join(docker_options)
            and tuple(wrapper[-len(command) :]) == command
        )
        if not isolated:
            raise OSError("Docker generator runtime did not enforce the required isolation")

    def _valid_output_evidence(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        if value.get("limit_bytes_per_stream") != self.output_limit_bytes_per_stream:
            return False
        streams: list[dict[str, Any]] = []
        for name in ("stdout", "stderr"):
            stream = value.get(name)
            if not isinstance(stream, dict):
                return False
            total = stream.get("total_bytes")
            captured = stream.get("captured_bytes")
            digest = stream.get("sha256")
            limited = stream.get("limited")
            complete = stream.get("complete")
            if (
                type(total) is not int
                or type(captured) is not int
                or total < 0
                or captured < 0
                or captured > self.output_limit_bytes_per_stream
                or captured > total
                or not isinstance(digest, str)
                or len(digest) != 64
                or type(limited) is not bool
                or limited is not (total > self.output_limit_bytes_per_stream)
                or complete is not True
            ):
                return False
            streams.append(stream)
        return value.get("limited") is any(stream["limited"] for stream in streams)

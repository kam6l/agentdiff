"""Ephemeral Docker clean-room environment used by proof."""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import subprocess  # nosec B404 -- exact Docker CLI argv only
import threading
import time
from pathlib import Path
from typing import Any, Sequence

from .models import ProofPhaseResult
from .verification import parse_test_counts

_MAX_OUTPUT_BYTES = 4 * 1024 * 1024


class DockerProofEnvironment:
    """One persistent, non-root verification container with a private workspace."""

    def __init__(
        self,
        *,
        workspace: Path,
        image: str,
        network: bool,
        executable: str = "docker",
    ) -> None:
        located = shutil.which(executable)
        if located is None:
            raise FileNotFoundError("Docker executable not found")
        self.executable = str(Path(located).resolve(strict=True))
        self.workspace = workspace.resolve(strict=True)
        self.image = image
        self.network = network
        self.container_id: str | None = None
        self.image_digest: str | None = None
        self.name = f"agentdiff-proof-{secrets.token_hex(8)}"

    def start(self) -> dict[str, Any]:
        user = self._container_user()
        mount = f"type=bind,src={self.workspace},dst=/workspace,rw"
        argv = [
            self.executable,
            "create",
            "--pull",
            "missing",
            "--name",
            self.name,
            "--workdir",
            "/workspace",
            "--user",
            user,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=128m",  # nosec B108
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--network",
            "bridge" if self.network else "none",
            "--cpus",
            "1.0",
            "--memory",
            "1g",
            "--pids-limit",
            "128",
            "--init",
            "--mount",
            mount,
            "--env",
            "HOME=/tmp",
            "--entrypoint",
            "sleep",
            self.image,
            "infinity",
        ]
        created = self._call(argv)
        if created.returncode != 0:
            raise OSError((created.stderr or created.stdout or "docker create failed").strip())
        container_id = created.stdout.strip()
        if not container_id or any(character.isspace() for character in container_id):
            raise OSError("Docker returned an invalid proof container id")
        self.container_id = container_id
        started = self._call([self.executable, "start", container_id])
        if started.returncode != 0:
            raise OSError((started.stderr or started.stdout or "docker start failed").strip())
        inspected = self._call(
            [
                self.executable,
                "image",
                "inspect",
                "--format",
                "{{json .RepoDigests}}",
                self.image,
            ]
        )
        self.image_digest = inspected.stdout.strip() if inspected.returncode == 0 else None
        return {
            "schema_version": 1,
            "backend": "docker",
            "image": self.image,
            "image_digest": self.image_digest,
            "network": "bridge" if self.network else "none",
            "user": user,
            "host_repository_mounted": False,
            "docker_socket_mounted": False,
            "private_workspace": True,
            "read_only_rootfs": True,
            "cap_drop": ["ALL"],
            "no_new_privileges": True,
            "environment_inheritance": "none",
            "clean_environment": True,
            "isolation_limit": "Docker containers share the host kernel",
        }

    def run_phase(
        self,
        phase: str,
        command: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> ProofPhaseResult:
        if self.container_id is None:
            raise RuntimeError("proof environment is not running")
        started = time.monotonic()
        process = subprocess.Popen(  # nosec B603
            [self.executable, "exec", self.container_id, *command],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=self._environment(),
        )
        if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
            raise RuntimeError("proof output pipe is unavailable")
        digest = hashlib.sha256()
        bounded = bytearray()
        output_bytes = 0
        output_limit_reached = threading.Event()

        def drain_output() -> None:
            nonlocal output_bytes
            if process.stdout is not None:
                with process.stdout:
                    while chunk := process.stdout.read(64 * 1024):
                        digest.update(chunk)
                        output_bytes += len(chunk)
                        remaining = _MAX_OUTPUT_BYTES - len(bounded)
                        if remaining > 0:
                            bounded.extend(chunk[:remaining])
                        if output_bytes > _MAX_OUTPUT_BYTES:
                            output_limit_reached.set()

        reader = threading.Thread(target=drain_output, daemon=True)
        reader.start()
        timed_out = False
        while process.poll() is None:
            if time.monotonic() - started >= timeout_seconds:
                timed_out = True
                process.kill()
                break
            if output_limit_reached.is_set():
                process.kill()
                break
            time.sleep(0.01)
        process.wait()
        reader.join(timeout=2.0)
        if reader.is_alive():
            process.stdout.close()
            reader.join(timeout=1.0)
        output_limited = output_limit_reached.is_set()
        if timed_out:
            returncode = 124
            detail = "verification phase timed out"
        elif output_limited:
            returncode = 125
            detail = "verification output exceeded the safety limit"
        else:
            returncode = int(process.returncode)
            detail = ""
        return self._phase_result(
            phase,
            command,
            status="PASS" if returncode == 0 else "FAIL",
            returncode=returncode,
            duration=time.monotonic() - started,
            output_sha256=digest.hexdigest(),
            output_bytes=output_bytes,
            bounded_output=bytes(bounded),
            detail=detail,
        )

    def close(self) -> None:
        if self.container_id is not None:
            self._call([self.executable, "rm", "--force", "--volumes", self.container_id])
            self.container_id = None

    def _phase_result(
        self,
        phase: str,
        command: Sequence[str],
        *,
        status: str,
        returncode: int,
        duration: float,
        output_sha256: str,
        output_bytes: int,
        bounded_output: bytes,
        detail: str,
    ) -> ProofPhaseResult:
        text = bounded_output.decode("utf-8", "replace")
        tests_passed, tests_total = parse_test_counts(text) if phase == "tests" else (None, None)
        return ProofPhaseResult(
            phase=phase,
            command=tuple(command),
            status=status,
            returncode=returncode,
            duration_seconds=duration,
            output_sha256=output_sha256,
            output_bytes=output_bytes,
            tests_passed=tests_passed,
            tests_total=tests_total,
            detail=(
                f"{detail}; output truncated"
                if detail and output_bytes > len(bounded_output)
                else detail
            ),
        )

    def _call(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # nosec B603
            list(argv),
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            env=self._environment(),
        )

    @staticmethod
    def _environment() -> dict[str, str]:
        return {
            name: os.environ[name]
            for name in ("PATH", "SystemRoot", "TEMP", "TMP")
            if name in os.environ
        }

    @staticmethod
    def _container_user() -> str:
        getuid = getattr(os, "getuid", None)
        getgid = getattr(os, "getgid", None)
        if getuid is not None and getgid is not None and int(getuid()) != 0:
            return f"{int(getuid())}:{int(getgid())}"
        return "65532:65532"

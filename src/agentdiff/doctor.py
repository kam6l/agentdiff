"""Truthful capability report for the current AgentDiff runtime."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CapabilityStatus(str, Enum):
    """Support level used by the doctor capability matrix."""

    YES = "yes"
    PARTIAL = "partial"
    NO = "no"


@dataclass(frozen=True)
class Capability:
    """One capability claim and the limitation that qualifies it."""

    name: str
    status: CapabilityStatus
    detail: str
    detected: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible capability data."""
        return {
            "status": self.status.value,
            "detail": self.detail,
            "detected": self.detected,
        }


@dataclass(frozen=True)
class DoctorReport:
    """Versioned, JSON-serializable runtime capability report."""

    platform: str
    python: str
    executable: str
    capabilities: tuple[Capability, ...]
    nofollow_open_supported: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the matrix plus stable compatibility summary fields."""
        matrix = {capability.name: capability.to_dict() for capability in self.capabilities}
        process_supported = matrix["process_ownership"]["status"] == CapabilityStatus.YES.value
        port_status = str(matrix["listening_port_observation"]["status"])
        docker_detected = bool(matrix["docker_backend"]["detected"])
        srt_detected = bool(matrix["anthropic_sandbox_runtime"]["detected"])
        return {
            "schema_version": 1,
            "platform": self.platform,
            "python": self.python,
            "local_runtime": True,
            "shell_execution": False,
            "process_identity": "pid_and_create_time" if process_supported else "unavailable",
            "process_tree_observation": process_supported,
            "process_cleanup": process_supported,
            "listening_port_observation": port_status,
            "listening_port_observation_scope": "machine_wide",
            "network_observation": False,
            "network_enforcement": False,
            "filesystem_observation": True,
            "filesystem_enforcement": False,
            "filesystem_policy_evaluation": "post_run",
            "conflict_checked_rollback": True,
            "rollback_scope": "regular_files_with_verified_backups",
            "nofollow_open_supported": self.nofollow_open_supported,
            "sandboxed": False,
            "docker_cli_detected": docker_detected,
            "docker_backend": False,
            "sandbox_runtime_cli_detected": srt_detected,
            "enforcement_backends": ["anthropic-sandbox-runtime"] if srt_detected else [],
            "mcp_interception": False,
            "remote_backends": [],
            "executable": self.executable,
            "capabilities": matrix,
        }


def collect_doctor_report() -> DoctorReport:
    """Detect local prerequisites without claiming unimplemented controls."""
    psutil_available = importlib.util.find_spec("psutil") is not None
    docker_detected = shutil.which("docker") is not None
    srt_detected = shutil.which("srt") is not None
    posix_session = os.name == "posix"
    capabilities = (
        Capability(
            name="local_runtime",
            status=CapabilityStatus.YES,
            detail="direct host subprocess execution with argv; not a sandbox",
        ),
        Capability(
            name="filesystem_observation",
            status=CapabilityStatus.YES,
            detail="project-root before/after manifests for the local runtime",
        ),
        Capability(
            name="filesystem_rollback",
            status=CapabilityStatus.YES,
            detail="conflict-checked recovery for eligible regular files with verified backups",
        ),
        Capability(
            name="process_ownership",
            status=CapabilityStatus.YES if psutil_available else CapabilityStatus.NO,
            detail=(
                "best-effort child-tree PID and creation-time evidence via psutil"
                if psutil_available
                else "psutil is unavailable"
            ),
        ),
        Capability(
            name="process_cleanup",
            status=CapabilityStatus.YES if psutil_available else CapabilityStatus.NO,
            detail=(
                "signals only observed PID and exact creation-time matches"
                if psutil_available
                else "psutil is unavailable"
            ),
        ),
        Capability(
            name="listening_port_observation",
            status=CapabilityStatus.PARTIAL if psutil_available else CapabilityStatus.NO,
            detail=(
                "machine-wide point-in-time listening-port diff; permissions may limit data; "
                "no causal ownership"
                if psutil_available
                else "psutil is unavailable"
            ),
        ),
        Capability(
            name="network_observation",
            status=CapabilityStatus.NO,
            detail="no packet, flow, DNS, or per-process network activity observation",
        ),
        Capability(
            name="network_enforcement",
            status=CapabilityStatus.NO,
            detail="the local runtime does not block or filter network access",
        ),
        Capability(
            name="sandbox",
            status=CapabilityStatus.NO,
            detail="commands execute directly on the host",
        ),
        Capability(
            name="docker_backend",
            status=CapabilityStatus.NO,
            detail="Docker CLI detection only; no Docker runtime backend is implemented",
            detected=docker_detected,
        ),
        Capability(
            name="anthropic_sandbox_runtime",
            status=CapabilityStatus.PARTIAL if srt_detected else CapabilityStatus.NO,
            detail=(
                "CLI detected; the optional adapter requests external sandbox controls whose "
                "effective guarantees depend on the runtime version, OS, and settings"
                if srt_detected
                else "CLI not detected; --runtime srt is unavailable"
            ),
            detected=srt_detected,
        ),
        Capability(
            name="mcp_interception",
            status=CapabilityStatus.NO,
            detail="no MCP proxy or protocol interception is implemented",
        ),
        Capability(
            name="dedicated_process_session",
            status=CapabilityStatus.YES if posix_session else CapabilityStatus.NO,
            detail=(
                "POSIX children start in a new session"
                if posix_session
                else "no dedicated Windows process group is configured"
            ),
        ),
    )
    return DoctorReport(
        platform=platform.system().lower(),
        python=platform.python_version(),
        executable=sys.executable,
        capabilities=capabilities,
        nofollow_open_supported=hasattr(os, "O_NOFOLLOW"),
    )


def doctor_report() -> dict[str, Any]:
    """Return a JSON-compatible doctor report for CLI callers."""
    return collect_doctor_report().to_dict()

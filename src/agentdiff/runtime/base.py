"""Runtime backend contracts and serializable execution evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import IO, TYPE_CHECKING, Any, Protocol, runtime_checkable

from agentdiff.redaction import redact_argv

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


@dataclass(frozen=True)
class OwnedProcess:
    """PID identity observed in the launched process tree.

    A PID alone is not an identity because operating systems reuse PIDs. ``create_time``
    must match before a cleanup implementation may signal the process.
    """

    pid: int
    create_time: float
    parent_pid: int | None
    relation: str

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible process evidence."""
        return {
            "pid": self.pid,
            "create_time": self.create_time,
            "parent_pid": self.parent_pid,
            "relation": self.relation,
        }


@dataclass(frozen=True)
class CleanupOutcome:
    """Cleanup decision for one recorded process identity."""

    process: OwnedProcess
    action: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible cleanup decision."""
        return {
            "process": self.process.to_dict(),
            "action": self.action,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CleanupReport:
    """Conservative cleanup decisions for recorded process identities."""

    outcomes: tuple[CleanupOutcome, ...] = ()

    @property
    def targeted(self) -> int:
        """Number of matching process identities that received a signal."""
        return sum(
            outcome.action in {"terminated", "killed", "still_running"} for outcome in self.outcomes
        )

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-compatible cleanup evidence."""
        return {
            "targeted": self.targeted,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }


@dataclass(frozen=True)
class PortEndpoint:
    """One machine-wide listening endpoint seen in a point-in-time snapshot."""

    host: str
    port: int
    pid: int | None

    def to_dict(self) -> dict[str, Any]:
        return {"host": self.host, "port": self.port, "pid": self.pid}


@dataclass(frozen=True)
class PortObservation:
    """Honest host-wide port delta without causal ownership claims."""

    opened: tuple[PortEndpoint, ...] = ()
    closed: tuple[PortEndpoint, ...] = ()
    scope: str = "machine_wide"
    level: str = "observation"
    ownership_attributed: bool = False
    enforced: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "opened": [item.to_dict() for item in self.opened],
            "closed": [item.to_dict() for item in self.closed],
            "scope": self.scope,
            "level": self.level,
            "ownership_attributed": self.ownership_attributed,
            "enforced": self.enforced,
            "error": self.error,
        }


@dataclass(frozen=True)
class RuntimeResult:
    """Outcome of one runtime invocation.

    ``returncode`` is the child status for completed runs and the conventional
    timeout status ``124`` when ``timed_out`` is true.
    """

    argv: tuple[str, ...]
    cwd: str
    returncode: int
    timed_out: bool
    duration_seconds: float
    owned_processes: tuple[OwnedProcess, ...] = ()
    cleanup: CleanupReport | None = None
    port_observation: PortObservation = PortObservation()
    backend: str = "local-observe"
    enforcement: str = "observation"
    wrapper_argv: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return versioned, JSON-compatible runtime evidence."""
        return {
            "schema_version": 1,
            "argv": redact_argv(self.argv),
            "cwd": self.cwd,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "duration_seconds": self.duration_seconds,
            "owned_processes": [process.to_dict() for process in self.owned_processes],
            "cleanup": self.cleanup.to_dict() if self.cleanup is not None else None,
            "port_observation": self.port_observation.to_dict(),
            "backend": self.backend,
            "enforcement": self.enforcement,
            "wrapper_argv": (
                redact_argv(self.wrapper_argv) if self.wrapper_argv is not None else None
            ),
        }


@runtime_checkable
class RuntimeBackend(Protocol):
    """Execution backend implemented by local and future isolated runtimes."""

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        stdin: int | IO[Any] | None = None,
        stdout: int | IO[Any] | None = None,
        stderr: int | IO[Any] | None = None,
    ) -> RuntimeResult:
        """Execute an argv sequence and return runtime evidence."""
        ...

    def cleanup(
        self,
        processes: Iterable[OwnedProcess],
        *,
        grace_period_seconds: float = 1.0,
    ) -> CleanupReport:
        """Clean up only process identities proven to belong to a prior run."""
        ...

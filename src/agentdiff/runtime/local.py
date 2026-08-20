"""Local subprocess runtime backend."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import time
from contextlib import suppress
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import psutil

from .base import (
    CleanupOutcome,
    CleanupReport,
    OwnedProcess,
    PortEndpoint,
    PortObservation,
    RuntimeResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from agentdiff.safety import SafetyController

_TIMEOUT_RETURN_CODE = 124


class LocalRuntime:
    """Run a command directly on the host without shell interpretation."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        poll_interval_seconds: float = 0.02,
        observe_ports: bool = True,
        safety_controller: SafetyController | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")
        self.poll_interval_seconds = poll_interval_seconds
        self.observe_ports = observe_ports
        self._safety_controller = safety_controller

    def configure_safety(self, controller: SafetyController) -> None:
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
        """Run exactly ``argv`` with the project root as the working directory."""
        command = tuple(argv)
        if not command:
            raise ValueError("argv must not be empty")
        if not all(isinstance(argument, str) for argument in command):
            raise TypeError("every argv item must be a string")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        before_ports, before_port_error = self._snapshot_ports()
        started = time.monotonic()
        # The argv sequence is passed without shell interpretation.
        process = subprocess.Popen(  # nosec B603
            command,
            cwd=self.root,
            shell=False,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name == "posix",
        )
        owned: dict[tuple[int, float], OwnedProcess] = {}
        deadline = started + timeout_seconds if timeout_seconds is not None else None
        try:
            return self._monitor_process(
                process,
                command,
                owned,
                started=started,
                deadline=deadline,
                before_ports=before_ports,
                before_port_error=before_port_error,
            )
        except BaseException:
            # Cancellation and observation failures must not strand the direct
            # child. Preserve whatever identities are available, then fall
            # back to the Popen handle if evidence cleanup itself fails.
            with suppress(BaseException):
                self._observe_execution_domain(process.pid, owned)
            with suppress(BaseException):
                self.cleanup(tuple(owned.values()), grace_period_seconds=0.5)
            self._stop_direct_process(process)
            raise

    def _monitor_process(
        self,
        process: subprocess.Popen[Any],
        command: tuple[str, ...],
        owned: dict[tuple[int, float], OwnedProcess],
        *,
        started: float,
        deadline: float | None,
        before_ports: set[PortEndpoint],
        before_port_error: str | None,
    ) -> RuntimeResult:
        self._observe_process_tree(process.pid, owned)

        while True:
            returncode = process.poll()
            if returncode is not None:
                self._observe_execution_domain(process.pid, owned)
                after_ports, after_port_error = self._snapshot_ports()
                evidence = tuple(owned.values())
                cleanup = self.cleanup(evidence)
                return RuntimeResult(
                    argv=command,
                    cwd=str(self.root),
                    returncode=returncode,
                    timed_out=False,
                    duration_seconds=time.monotonic() - started,
                    owned_processes=evidence,
                    cleanup=cleanup,
                    safety=(
                        self._safety_controller.report.to_dict()
                        if self._safety_controller is not None
                        else None
                    ),
                    port_observation=self._port_observation(
                        before_ports,
                        after_ports,
                        before_port_error,
                        after_port_error,
                    ),
                )
            self._observe_process_tree(process.pid, owned)

            now = time.monotonic()
            elapsed = now - started

            if self._safety_controller is not None and self._safety_controller.observe(
                root=self.root,
                duration_seconds=elapsed,
                processes_spawned=len(owned),
                runtime_active=True,
            ):
                evidence = tuple(owned.values())
                self.cleanup(evidence, grace_period_seconds=0.2)
                self._stop_direct_process(process)
                after_ports, after_port_error = self._snapshot_ports()
                return RuntimeResult(
                    argv=command,
                    cwd=str(self.root),
                    returncode=125,
                    timed_out=False,
                    duration_seconds=elapsed,
                    owned_processes=evidence,
                    cleanup=self.cleanup(evidence),
                    safety=self._safety_controller.report.to_dict(),
                    port_observation=self._port_observation(
                        before_ports,
                        after_ports,
                        before_port_error,
                        after_port_error,
                    ),
                )

            if deadline is not None and now >= deadline:
                # Preserve the identities as evidence before cleanup changes process state.
                evidence = tuple(owned.values())
                after_ports, after_port_error = self._snapshot_ports()
                cleanup = self.cleanup(evidence)
                with suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=1.0)
                return RuntimeResult(
                    argv=command,
                    cwd=str(self.root),
                    returncode=_TIMEOUT_RETURN_CODE,
                    timed_out=True,
                    duration_seconds=elapsed,
                    owned_processes=evidence,
                    cleanup=cleanup,
                    safety=(
                        self._safety_controller.report.to_dict()
                        if self._safety_controller is not None
                        else None
                    ),
                    port_observation=self._port_observation(
                        before_ports,
                        after_ports,
                        before_port_error,
                        after_port_error,
                    ),
                )

            time.sleep(self.poll_interval_seconds)

    def _observe_process_tree(
        self,
        root_pid: int,
        owned: dict[tuple[int, float], OwnedProcess],
    ) -> None:
        try:
            root_process = psutil.Process(root_pid)
            root_created = root_process.create_time()
            owned.setdefault(
                (root_pid, root_created),
                OwnedProcess(
                    pid=root_pid,
                    create_time=root_created,
                    parent_pid=None,
                    relation="root",
                ),
            )
            for child in root_process.children(recursive=True):
                with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                    child_pid = child.pid
                    child_created = child.create_time()
                    parent = child.parent()
                    parent_pid = parent.pid if parent is not None else None
                    owned.setdefault(
                        (child_pid, child_created),
                        OwnedProcess(
                            pid=child_pid,
                            create_time=child_created,
                            parent_pid=parent_pid,
                            relation="descendant",
                        ),
                    )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def _observe_execution_domain(
        self,
        root_pid: int,
        owned: dict[tuple[int, float], OwnedProcess],
    ) -> None:
        self._observe_process_tree(root_pid, owned)
        for process in psutil.process_iter(["pid", "create_time", "ppid"]):
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                pid = int(process.info["pid"])
                parent_pid = process.info.get("ppid")
                create_time = float(process.info["create_time"])
                matching_parent = parent_pid is not None and any(
                    owned_pid == parent_pid and create_time >= owned_created
                    for owned_pid, owned_created in owned
                )
                matching_session = False
                if os.name == "posix" and hasattr(os, "getsid"):
                    with suppress(OSError):
                        matching_session = os.getsid(pid) == root_pid
                if matching_parent or matching_session:
                    owned.setdefault(
                        (pid, create_time),
                        OwnedProcess(
                            pid=pid,
                            create_time=create_time,
                            parent_pid=parent_pid,
                            relation="reparented_descendant",
                        ),
                    )

    def cleanup(
        self,
        processes: Iterable[OwnedProcess],
        *,
        grace_period_seconds: float = 1.0,
    ) -> CleanupReport:
        """Terminate and reap matching process identities.

        A process is signaled ONLY if ``create_time`` matches the observed identity.
        """
        targets = list(processes)
        outcomes: list[CleanupOutcome] = []
        signaled: list[tuple[OwnedProcess, Any]] = []

        for identity in targets:
            try:
                candidate = psutil.Process(identity.pid)
            except psutil.NoSuchProcess:
                outcomes.append(CleanupOutcome(identity, "already_exited"))
                continue
            except psutil.AccessDenied:
                outcomes.append(CleanupOutcome(identity, "access_denied"))
                continue

            try:
                candidate_created = candidate.create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                outcomes.append(CleanupOutcome(identity, "already_exited"))
                continue

            if candidate_created != identity.create_time:
                outcomes.append(
                    CleanupOutcome(
                        identity,
                        "pid_reused",
                        detail="create_time does not match recorded process identity",
                    )
                )
                continue

            try:
                candidate.terminate()
            except psutil.NoSuchProcess:
                outcomes.append(CleanupOutcome(identity, "already_exited"))
                continue
            except psutil.AccessDenied:
                outcomes.append(CleanupOutcome(identity, "access_denied"))
                continue

            signaled.append((identity, candidate))

        if signaled:
            wait_fn = getattr(psutil, "wait_procs", None)
            alive: list[Any] = []
            if wait_fn is not None:
                _gone, alive = wait_fn([proc for _, proc in signaled], timeout=grace_period_seconds)
            else:
                deadline = time.monotonic() + max(0.0, grace_period_seconds)
                while time.monotonic() < deadline:
                    alive = [
                        p
                        for _, p in signaled
                        if (p.is_running() if hasattr(p, "is_running") else True)
                    ]
                    if not alive:
                        break
                    time.sleep(self.poll_interval_seconds)

            alive_set = set(alive)
            for identity, proc in signaled:
                if proc in alive_set:
                    with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                        proc.kill()
                    outcomes.append(CleanupOutcome(identity, "still_running"))
                else:
                    outcomes.append(CleanupOutcome(identity, "terminated"))

        return CleanupReport(outcomes=tuple(outcomes))

    def _snapshot_ports(self) -> tuple[set[PortEndpoint], str | None]:
        if not self.observe_ports:
            return set(), None
        endpoints: set[PortEndpoint] = set()
        try:
            for connection in psutil.net_connections(kind="inet"):
                if connection.status != psutil.CONN_LISTEN or not connection.laddr:
                    continue
                laddr = connection.laddr
                if isinstance(laddr, tuple):
                    host = str(laddr[0])
                    port = int(laddr[1])
                elif hasattr(laddr, "ip"):
                    host = str(laddr.ip)
                    port = int(laddr.port)
                else:
                    continue
                endpoints.add(
                    PortEndpoint(
                        host=host,
                        port=port,
                        pid=connection.pid,
                    )
                )
            return endpoints, None
        except (psutil.AccessDenied, PermissionError) as error:
            return set(), f"permission denied: {error}"
        except OSError as error:
            return set(), f"network observation unavailable: {error}"

    def _port_observation(
        self,
        before: set[PortEndpoint],
        after: set[PortEndpoint],
        before_error: str | None,
        after_error: str | None,
    ) -> PortObservation:
        if not self.observe_ports:
            return PortObservation()
        error: str | None = None
        if before_error:
            error = f"before snapshot error: {before_error}"
        elif after_error:
            error = f"after snapshot error: {after_error}"
        if error is not None:
            return PortObservation(opened=(), closed=(), error=error)
        opened = tuple(sorted(after - before, key=lambda item: (item.host, item.port)))
        closed = tuple(sorted(before - after, key=lambda item: (item.host, item.port)))
        return PortObservation(
            opened=opened,
            closed=closed,
            error=error,
        )

    def _stop_direct_process(self, process: subprocess.Popen[Any]) -> None:
        with suppress(OSError):
            process.terminate()
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=0.5)
        with suppress(OSError):
            process.kill()
        with suppress(OSError):
            process.wait(timeout=0.5)

    def close(self) -> None:
        """Release any resources held by the runtime."""
        pass



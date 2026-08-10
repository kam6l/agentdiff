"""Local subprocess runtime backend."""

from __future__ import annotations

import os
import socket
import subprocess
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

_TIMEOUT_RETURN_CODE = 124


class LocalRuntime:
    """Run a command directly on the host without shell interpretation."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        poll_interval_seconds: float = 0.02,
        observe_ports: bool = True,
    ) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")
        self.poll_interval_seconds = poll_interval_seconds
        self.observe_ports = observe_ports

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
        process = subprocess.Popen(
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
                    port_observation=self._port_observation(
                        before_ports,
                        after_ports,
                        before_port_error,
                        after_port_error,
                    ),
                )
            self._observe_process_tree(process.pid, owned)

            now = time.monotonic()
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
                    duration_seconds=time.monotonic() - started,
                    owned_processes=evidence,
                    cleanup=cleanup,
                    port_observation=self._port_observation(
                        before_ports,
                        after_ports,
                        before_port_error,
                        after_port_error,
                    ),
                )

            sleep_seconds = self.poll_interval_seconds
            if deadline is not None:
                sleep_seconds = min(sleep_seconds, max(0.0, deadline - now))
            time.sleep(sleep_seconds)

    @staticmethod
    def _stop_direct_process(process: subprocess.Popen[Any]) -> None:
        if process.poll() is not None:
            return
        with suppress(OSError):
            process.terminate()
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            with suppress(OSError):
                process.kill()
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=0.5)

    def cleanup(
        self,
        processes: Iterable[OwnedProcess],
        *,
        grace_period_seconds: float = 1.0,
    ) -> CleanupReport:
        """Terminate only PIDs whose current creation time matches recorded evidence."""
        if grace_period_seconds < 0:
            raise ValueError("grace_period_seconds must not be negative")

        unique = {(record.pid, record.create_time): record for record in processes}
        records = sorted(unique.values(), key=lambda item: item.relation == "direct")
        outcomes: dict[tuple[int, float], CleanupOutcome] = {}
        signaled: list[tuple[OwnedProcess, psutil.Process]] = []

        for record in records:
            key = (record.pid, record.create_time)
            try:
                current = psutil.Process(record.pid)
                if not self._creation_time_matches(current, record.create_time):
                    outcomes[key] = CleanupOutcome(
                        process=record,
                        action="pid_reused",
                        detail="current process creation time does not match recorded evidence",
                    )
                    continue
                current.terminate()
            except psutil.NoSuchProcess:
                outcomes[key] = CleanupOutcome(process=record, action="already_exited")
            except psutil.AccessDenied as error:
                outcomes[key] = CleanupOutcome(
                    process=record,
                    action="access_denied",
                    detail=str(error),
                )
            else:
                outcomes[key] = CleanupOutcome(process=record, action="terminated")
                signaled.append((record, current))

        if signaled:
            _, alive = psutil.wait_procs(
                [current for _, current in signaled],
                timeout=grace_period_seconds,
            )
            alive_pids = {current.pid for current in alive}
            force_signaled: list[tuple[OwnedProcess, psutil.Process]] = []
            for record, current in signaled:
                if current.pid not in alive_pids:
                    continue
                key = (record.pid, record.create_time)
                try:
                    if not self._creation_time_matches(current, record.create_time):
                        outcomes[key] = CleanupOutcome(
                            process=record,
                            action="pid_reused",
                            detail="process identity changed before forceful cleanup",
                        )
                        continue
                    current.kill()
                except psutil.NoSuchProcess:
                    continue
                except psutil.AccessDenied as error:
                    outcomes[key] = CleanupOutcome(
                        process=record,
                        action="access_denied",
                        detail=str(error),
                    )
                else:
                    outcomes[key] = CleanupOutcome(process=record, action="killed")
                    force_signaled.append((record, current))

            if force_signaled:
                _, still_alive = psutil.wait_procs(
                    [current for _, current in force_signaled],
                    timeout=grace_period_seconds,
                )
                still_alive_pids = {current.pid for current in still_alive}
                for record, current in force_signaled:
                    if current.pid not in still_alive_pids:
                        continue
                    key = (record.pid, record.create_time)
                    try:
                        identity_matches = self._creation_time_matches(
                            current,
                            record.create_time,
                        )
                    except psutil.NoSuchProcess:
                        continue
                    except psutil.AccessDenied as error:
                        outcomes[key] = CleanupOutcome(
                            process=record,
                            action="access_denied",
                            detail=f"could not verify exit after kill: {error}",
                        )
                    else:
                        outcomes[key] = CleanupOutcome(
                            process=record,
                            action="still_running" if identity_matches else "pid_reused",
                            detail=(
                                "process remained alive after kill"
                                if identity_matches
                                else "process identity changed after forceful cleanup"
                            ),
                        )

        return CleanupReport(
            outcomes=tuple(outcomes[(item.pid, item.create_time)] for item in records)
        )

    def _observe_execution_domain(
        self,
        root_pid: int,
        owned: dict[tuple[int, float], OwnedProcess],
    ) -> None:
        self._observe_process_tree(root_pid, owned)
        self._observe_process_session(root_pid, owned)

    @staticmethod
    def _observe_process_session(
        session_id: int,
        owned: dict[tuple[int, float], OwnedProcess],
    ) -> None:
        """Find reparented POSIX children that remain in the dedicated session."""

        if os.name != "posix":
            return
        for process in psutil.process_iter():
            try:
                if os.getsid(process.pid) != session_id:
                    continue
                create_time = process.create_time()
                parent_pid = process.ppid()
            except (OSError, psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            record = OwnedProcess(
                pid=process.pid,
                create_time=create_time,
                parent_pid=parent_pid,
                relation="direct" if process.pid == session_id else "descendant",
            )
            owned[(record.pid, record.create_time)] = record

    @staticmethod
    def _observe_process_tree(
        root_pid: int,
        owned: dict[tuple[int, float], OwnedProcess],
    ) -> None:
        try:
            root = psutil.Process(root_pid)
            root_create_time = root.create_time()
            direct_records = [item for item in owned.values() if item.relation == "direct"]
            if direct_records and root_create_time != direct_records[0].create_time:
                return
            observed = [
                (root, "direct"),
                *((child, "descendant") for child in root.children(recursive=True)),
            ]
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return

        for process, relation in observed:
            try:
                create_time = process.create_time()
                parent_pid = process.ppid()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            record = OwnedProcess(
                pid=process.pid,
                create_time=create_time,
                parent_pid=parent_pid,
                relation=relation,
            )
            owned[(record.pid, record.create_time)] = record

    @staticmethod
    def _creation_time_matches(process: psutil.Process, expected: float) -> bool:
        return process.create_time() == expected

    def _snapshot_ports(self) -> tuple[set[PortEndpoint], str | None]:
        if not self.observe_ports:
            return set(), None
        try:
            connections = psutil.net_connections(kind="inet")
        except (OSError, psutil.Error) as error:
            return set(), f"{type(error).__name__}: {error}"

        endpoints: set[PortEndpoint] = set()
        for connection in connections:
            if (
                connection.status != psutil.CONN_LISTEN
                or connection.type != socket.SOCK_STREAM
                or connection.family not in {socket.AF_INET, socket.AF_INET6}
                or not connection.laddr
            ):
                continue
            host = getattr(connection.laddr, "ip", connection.laddr[0])
            port = getattr(connection.laddr, "port", connection.laddr[1])
            endpoints.add(PortEndpoint(host=str(host), port=int(port), pid=connection.pid))
        return endpoints, None

    @staticmethod
    def _port_observation(
        before: set[PortEndpoint],
        after: set[PortEndpoint],
        before_error: str | None,
        after_error: str | None,
    ) -> PortObservation:
        errors = [
            f"before snapshot: {before_error}" if before_error else "",
            f"after snapshot: {after_error}" if after_error else "",
        ]
        error = "; ".join(item for item in errors if item) or None
        if error is not None:
            # A set difference against a failed snapshot would invent machine-wide
            # opens or closes. Preserve the collection error without inferring a delta.
            return PortObservation(error=error)

        def key(item: PortEndpoint) -> tuple[str, int, int]:
            return (item.host, item.port, item.pid if item.pid is not None else -1)

        return PortObservation(
            opened=tuple(sorted(after - before, key=key)),
            closed=tuple(sorted(before - after, key=key)),
            error=error,
        )

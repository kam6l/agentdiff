"""Client for the local AgentDiff sidecar daemon."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess  # nosec B404 -- fixed argv spawn of the local daemon
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_MAX_BODY_BYTES = 4 * 1024 * 1024


class SidecarError(RuntimeError):
    """Raised when the sidecar is unreachable or rejects a request."""


class SidecarClient:
    """Talk to a local sidecar over 127.0.0.1 with bearer-token auth."""

    def __init__(self, root: str | os.PathLike[str], *, timeout: float = 300.0) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        self.timeout = timeout
        state_dir = self.root / ".agentdiff" / "sidecar"
        token_path = state_dir / "token"
        port_path = state_dir / "port"
        if not token_path.is_file() or not port_path.is_file():
            raise SidecarError("sidecar is not running (run `agentdiff serve` first)")
        self.token = token_path.read_text(encoding="utf-8").strip()
        try:
            self.port = int(port_path.read_text(encoding="utf-8").strip())
        except ValueError as error:
            raise SidecarError("sidecar port file is invalid") from error
        if not 0 < self.port < 65536:
            raise SidecarError("sidecar port is out of range")
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload or {}, sort_keys=True).encode("utf-8")
        if len(body) > _MAX_BODY_BYTES:
            raise SidecarError("request body exceeds the sidecar limit")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body if method == "POST" else None,
            method=method,
            headers={
                "X-AgentDiff-Token": self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:  # nosec B310
                raw = response.read(_MAX_BODY_BYTES + 1)
                if len(raw) > _MAX_BODY_BYTES:
                    raise SidecarError("sidecar response exceeds the limit")
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = ""
            with contextlib.suppress(OSError):
                detail = error.read(2048).decode("utf-8", "replace")
            raise SidecarError(f"sidecar returned {error.code}: {detail[:300]}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise SidecarError(f"sidecar unreachable: {error}") from error

    def status(self) -> dict[str, Any]:
        return self.request("GET", "/v1/status")

    def bootstrap(self, *, force: bool = False) -> dict[str, Any]:
        return self.request("POST", "/v1/bootstrap", {"force": force})

    def run(
        self, *, argv: list[str], task: str = "", policy: str = "", timeout: float = 0
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/run",
            {"argv": argv, "task": task, "policy": policy, "timeout": timeout},
        )

    def prove(
        self, *, run_id: str, timeout: float = 900.0, use_cache: bool = True
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/prove",
            {"run_id": run_id, "timeout": timeout, "use_cache": use_cache},
        )

    def repair(
        self,
        *,
        run_id: str,
        max_attempts: int = 2,
        max_runtime: float = 1800.0,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/repair",
            {"run_id": run_id, "max_attempts": max_attempts, "max_runtime": max_runtime},
        )

    def promote(
        self,
        *,
        run_id: str,
        safe_only: bool = True,
        dry_run: bool = False,
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/promote",
            {"run_id": run_id, "safe_only": safe_only, "dry_run": dry_run, "paths": paths or []},
        )

    def session_begin(self, *, task: str, agent: str = "") -> dict[str, Any]:
        return self.request("POST", "/v1/session/begin", {"task": task, "agent": agent})

    def session_event(
        self, *, session_id: str, event_type: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/session/event",
            {"session_id": session_id, "event_type": event_type, "data": data},
        )

    def session_end(self, *, session_id: str) -> dict[str, Any]:
        return self.request("POST", "/v1/session/end", {"session_id": session_id})

    def notify(
        self, *, kind: str, title: str, message: str = "", run_id: str = ""
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/v1/notify",
            {"kind": kind, "title": title, "message": message, "run_id": run_id},
        )

    def workspace_status(self) -> dict[str, Any]:
        return self.request("GET", "/v1/workspace/status")

    def cache_status(self) -> dict[str, Any]:
        return self.request("GET", "/v1/cache/status")


def ensure_sidecar(root: str | os.PathLike[str]) -> SidecarClient:
    """Return a client, starting the daemon in the background if needed."""
    resolved_root = Path(root).expanduser().resolve(strict=True)
    state_dir = resolved_root / ".agentdiff" / "sidecar"
    try:
        client = SidecarClient(resolved_root, timeout=5.0)
        client.status()
        return client
    except SidecarError:
        pass
    proc = _spawn_daemon(resolved_root)
    deadline = time.monotonic() + 20.0
    last_error: SidecarError | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log_file = state_dir / "daemon.log"
            log_content = (
                log_file.read_text(encoding="utf-8", errors="replace") if log_file.is_file() else ""
            )
            raise SidecarError(f"sidecar process exited with code {proc.returncode}: {log_content}")
        try:
            client = SidecarClient(resolved_root, timeout=5.0)
            client.status()
            return client
        except SidecarError as error:
            last_error = error
            time.sleep(0.25)
    log_text = ""
    log_file = state_dir / "daemon.log"
    if log_file.is_file():
        log_text = f" (daemon log: {log_file.read_text(encoding='utf-8', errors='replace')[-500:]})"
    raise SidecarError(f"sidecar did not start: {last_error}{log_text}")


def _spawn_daemon(root: str | os.PathLike[str]) -> subprocess.Popen[Any]:
    resolved_root = Path(root).expanduser().resolve(strict=True)
    state_dir = resolved_root / ".agentdiff" / "sidecar"
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    executable = sys.executable
    module = "agentdiff.sidecar.server"
    argv = [executable, "-u", "-m", module, "--root", str(resolved_root)]
    log_file = open(state_dir / "daemon.log", "a", encoding="utf-8")  # noqa: SIM115
    try:
        kwargs: dict[str, Any] = {
            "shell": False,
            "stdout": log_file,
            "stderr": log_file,
            "stdin": subprocess.DEVNULL,
            "close_fds": True,
        }
        env = dict(os.environ)
        src_dir = str(Path(__file__).resolve().parent.parent.parent)
        sys_paths = [str(p) for p in sys.path if p]
        if src_dir not in sys_paths:
            sys_paths.insert(0, src_dir)
        existing_pythonpath = env.get("PYTHONPATH", "")
        if existing_pythonpath:
            sys_paths.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(sys_paths)
        env["PYTHONUNBUFFERED"] = "1"
        kwargs["env"] = env
        kwargs["cwd"] = str(resolved_root)

        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        elif sys.version_info < (3, 14):
            kwargs["start_new_session"] = True
        return subprocess.Popen(argv, **kwargs)  # nosec B603
    finally:
        log_file.close()

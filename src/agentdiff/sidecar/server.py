"""Local zero-touch AgentDiff sidecar daemon.

A small HTTP daemon bound to 127.0.0.1 with a per-repository bearer token.
It receives lifecycle/tool events from agent adapters and manages transactions,
evidence, policy, sandbox selection, proof, retries, promotion, and
notifications — so normal agent use becomes:

    agentdiff init          # or: agentdiff bootstrap
    codex                   # the agent runs; AgentDiff handles the rest

There is no hosted service: all state stays under ``<root>/.agentdiff``.
"""

from __future__ import annotations

import argparse
import contextlib
import hmac
import json
import os
import secrets
import subprocess  # nosec B404 -- fixed daemon re-exec argv
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from agentdiff import __version__
from agentdiff.impact.cache import ProofCache
from agentdiff.integrations import MCPPolicyHook
from agentdiff.policy import load_policy, load_policy_file
from agentdiff.promotion import PromotionEngine
from agentdiff.proof import ProofEngine
from agentdiff.repair import RepairLoop
from agentdiff.transaction import AgentRunTransaction
from agentdiff.trust import TrustCompiler

from .notify import Notification, Notifier

_MAX_BODY_BYTES = 4 * 1024 * 1024
_TOKEN_BYTES = 32

_ROUTES: dict[str, tuple[str, str]] = {
    "/v1/status": ("GET", "status"),
    "/v1/bootstrap": ("POST", "bootstrap"),
    "/v1/run": ("POST", "run"),
    "/v1/prove": ("POST", "prove"),
    "/v1/repair": ("POST", "repair"),
    "/v1/promote": ("POST", "promote"),
    "/v1/session/begin": ("POST", "session_begin"),
    "/v1/session/event": ("POST", "session_event"),
    "/v1/session/end": ("POST", "session_end"),
    "/v1/notify": ("POST", "notify"),
    "/v1/workspace/status": ("GET", "workspace_status"),
    "/v1/cache/status": ("GET", "cache_status"),
    "/v1/stop": ("POST", "stop"),
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SidecarServer:
    """Stateful sidecar owning one repository root."""

    def __init__(self, root: str | os.PathLike[str], *, port: int = 0) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise NotADirectoryError(self.root)
        self.state_dir = self.root / ".agentdiff" / "sidecar"
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.token = self._load_or_create_token()
        self.port = port
        self._sessions: dict[str, dict[str, Any]] = {}
        self._sessions_lock = threading.Lock()
        self._stopping = threading.Event()
        self.notifier = Notifier(self.root, echo=False)

    def _load_or_create_token(self) -> str:
        token_path = self.state_dir / "token"
        if token_path.is_file():
            existing = token_path.read_text(encoding="utf-8").strip()
            if len(existing) >= 32:
                return existing
        token = secrets.token_hex(_TOKEN_BYTES)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".token.", suffix=".tmp", dir=str(self.state_dir)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(token)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, token_path)
            if os.name != "nt":
                token_path.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)
        return token

    # ---- request handlers ---------------------------------------------------

    def handle(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_on_{action}", None)
        if handler is None:
            raise ValueError(f"unknown action: {action}")
        return handler(payload)

    def _on_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return {
            "ok": True,
            "version": __version__,
            "pid": os.getpid(),
            "root": str(self.root),
            "sessions": len(self._sessions),
            "schema_version": 1,
        }

    def _on_bootstrap(self, payload: dict[str, Any]) -> dict[str, Any]:
        report = TrustCompiler(self.root).compile(force=bool(payload.get("force")))
        return {"ok": True, "report": report.to_dict()}

    def _on_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        argv = payload.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(item, str) for item in argv)
        ):
            raise ValueError("run requires a non-empty argv list of strings")
        policy = self._resolve_policy(str(payload.get("policy") or ""))
        runtime = self._resolve_runtime(policy)
        transaction = AgentRunTransaction(
            root=self.root,
            policy=policy,
            task=str(payload.get("task") or ""),
            runtime=runtime,
        )
        result = transaction.run(argv, timeout_seconds=_optional_float(payload.get("timeout")))
        return {"ok": True, "run_id": result.run_id, "result": result.to_dict()}

    def _on_prove(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "")
        cache = ProofCache(self.root) if payload.get("use_cache", True) else None
        proof = ProofEngine(
            self.root,
            run_id,
            cache=cache,
            target=str(payload.get("target") or "full"),
        ).prove(timeout_seconds=_optional_float(payload.get("timeout")) or 900.0)
        return {"ok": True, "proof": proof.to_dict()}

    def _on_repair(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "")
        loop = RepairLoop(
            self.root,
            run_id,
            max_attempts=int(payload.get("max_attempts") or 2),
            max_runtime_seconds=float(payload.get("max_runtime") or 1800.0),
            cache=ProofCache(self.root),
        )
        outcome = loop.run()
        if outcome.status == "NEEDS_AGENT":
            self.notifier.notify(
                Notification(
                    kind="human",
                    title="Repair needs an agent run",
                    message="Failure packet written; re-run with an agent command builder.",
                    run_id=run_id,
                )
            )
        return {"ok": True, "outcome": outcome.to_dict()}

    def _on_promote(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "")
        engine = PromotionEngine(self.root, run_id)
        report = engine.promote(
            dry_run=bool(payload.get("dry_run")),
            safe_only=bool(payload.get("safe_only", True)),
            paths=[str(item) for item in payload.get("paths") or []],
        )
        return {"ok": True, "report": report.to_dict()}

    def _on_session_begin(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = f"session-{secrets.token_hex(8)}"
        with self._sessions_lock:
            self._sessions[session_id] = {
                "session_id": session_id,
                "task": str(payload.get("task") or ""),
                "agent": str(payload.get("agent") or ""),
                "created_at": _utc_now_iso(),
                "events": [],
            }
        return {"ok": True, "session_id": session_id}

    def _on_session_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "")
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"unknown session: {session_id}")
            session["events"].append(
                {
                    "timestamp": _utc_now_iso(),
                    "event_type": str(payload.get("event_type") or ""),
                    "data": payload.get("data") or {},
                }
            )
        event_type = str(payload.get("event_type") or "")
        data = payload.get("data") or {}
        decision: dict[str, Any] | None = None
        if event_type == "tool_call" and isinstance(data, dict):
            policy = self._resolve_policy("")
            hook = MCPPolicyHook(policy)
            tool_decision = hook.evaluate(str(data.get("tool_name") or ""), data.get("arguments"))
            decision = tool_decision.to_dict()
        return {"ok": True, "decision": decision}

    def _on_session_end(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "")
        with self._sessions_lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                raise KeyError(f"unknown session: {session_id}")
        return {"ok": True, "session": session}

    def _on_notify(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = self.notifier.notify(
            Notification(
                kind=str(payload.get("kind") or "auto"),
                title=str(payload.get("title") or ""),
                message=str(payload.get("message") or ""),
                run_id=str(payload.get("run_id") or ""),
            )
        )
        return {"ok": True, "path": str(path)}

    def _on_workspace_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        from agentdiff.workspace import WarmWorkspaceFactory

        return {"ok": True, "stats": WarmWorkspaceFactory(self.root).stats()}

    def _on_cache_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return {"ok": True, "stats": ProofCache(self.root).stats()}

    def _on_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        self._stopping.set()
        return {"ok": True, "stopping": True}

    # ---- helpers ------------------------------------------------------------

    def _resolve_policy(self, requested: str) -> Any:
        if requested:
            return load_policy_file(requested)
        default_path = self.root / "agentdiff.yaml"
        if default_path.is_file() and not default_path.is_symlink():
            return load_policy_file(default_path)

        return load_policy(
            {
                "version": 2,
                "filesystem": {"allow_write": ["**"], "default": "allow"},
                "process": {"default": "allow"},
                "network": {"mode": "observe"},
            }
        )

    def _resolve_runtime(self, policy: Any) -> Any:
        import shutil

        from agentdiff.runtime import DockerRuntime

        backend = getattr(getattr(policy, "runtime", None), "backend", None)
        if backend == "docker" and shutil.which("docker") is not None:
            image = policy.proof.image or "python:3.12-slim"
            try:
                return DockerRuntime(self.root, image=image)
            except (OSError, TypeError, ValueError):
                pass
        return None  # local observation runtime


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return parsed if parsed > 0 else None


class _SidecarHandler(BaseHTTPRequestHandler):
    """HTTP handler with token auth and strict JSON routing."""

    server_version = f"AgentDiff/{__version__}"
    protocol_version = "HTTP/1.1"

    def _server(self) -> SidecarServer:
        return self.server.sidecar  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        route = _ROUTES.get(self.path)
        if route is None or route[0] != method:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return
        payload: dict[str, Any] = {}
        if method == "POST":
            length_header = self.headers.get("Content-Length")
            try:
                length = int(length_header or 0)
            except ValueError:
                self._send_json(400, {"ok": False, "error": "invalid content length"})
                return
            if length > _MAX_BODY_BYTES:
                self._send_json(413, {"ok": False, "error": "request body too large"})
                return
            raw = self.rfile.read(length) if length else b""
            if raw:
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._send_json(400, {"ok": False, "error": "invalid JSON body"})
                    return
                if not isinstance(parsed, dict):
                    self._send_json(400, {"ok": False, "error": "JSON body must be an object"})
                    return
                payload = parsed
        try:
            result = self._server().handle(route[1], payload)
        except (ValueError, KeyError, TypeError, PermissionError, FileNotFoundError) as error:
            self._send_json(400, {"ok": False, "error": str(error)})
            return
        except Exception as error:  # noqa: BLE001 - report daemon errors to the client
            self._send_json(500, {"ok": False, "error": f"{type(error).__name__}: {error}"})
            return
        self._send_json(200, result)

    def _authorized(self) -> bool:
        provided = self.headers.get("X-AgentDiff-Token", "")
        expected = self._server().token
        return hmac.compare_digest(provided, expected)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        # Quiet daemon logging; diagnostics live in .agentdiff/sidecar/log.
        del format, args


class _SidecarHTTPServer(HTTPServer):
    def __init__(self, address: tuple[str, int], sidecar: SidecarServer) -> None:
        self.sidecar = sidecar
        super().__init__(address, _SidecarHandler)


def serve(root: str | os.PathLike[str], *, port: int = 0, foreground: bool = True) -> None:
    sidecar = SidecarServer(root, port=port)
    if not foreground:
        _daemonize(sidecar)
        return
    httpd = _SidecarHTTPServer(("127.0.0.1", sidecar.port), sidecar)
    actual_port = int(httpd.server_address[1])
    sidecar.port = actual_port
    (sidecar.state_dir / "port").write_text(str(actual_port), encoding="utf-8")
    (sidecar.state_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
    if os.name != "nt":
        (sidecar.state_dir / "port").chmod(0o600)
        (sidecar.state_dir / "pid").chmod(0o600)
    print(f"agentdiff sidecar listening on 127.0.0.1:{actual_port} (root={sidecar.root})")
    try:
        while not sidecar._stopping.is_set():
            httpd.handle_request()
    finally:
        httpd.server_close()
        _cleanup_state(sidecar.state_dir)


def _daemonize(sidecar: SidecarServer) -> None:
    argv = [sys.executable, "-m", "agentdiff.sidecar.server", "--root", str(sidecar.root)]
    kwargs: dict[str, Any] = {
        "shell": False,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    env = dict(os.environ)
    src_dir = str(Path(__file__).resolve().parent.parent.parent)
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_dir
    kwargs["env"] = env

    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(argv, **kwargs)  # nosec B603


def _cleanup_state(state_dir: Path) -> None:
    for name in ("port", "pid"):
        with contextlib.suppress(OSError):
            (state_dir / name).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentdiff.sidecar.server")
    parser.add_argument("--root", default=".")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--daemon", action="store_true", help="detach and return immediately")
    args = parser.parse_args(argv)
    serve(args.root, port=args.port, foreground=not args.daemon)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

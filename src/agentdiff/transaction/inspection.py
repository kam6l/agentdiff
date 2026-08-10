"""Read-only run inspection and identity-safe residual process cleanup."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentdiff.runtime import CleanupReport, LocalRuntime, OwnedProcess

from .store import RunStore


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Compact, JSON-safe summary of one durable run capsule."""

    run_id: str
    created_at: str
    task: str | None
    status: str
    safety_outcome: str
    blast_radius: int
    returncode: int | None
    command: tuple[str, ...]
    integrity_ok: bool | None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["command"] = list(self.command)
        return value


class RunInspector:
    """Validate and inspect one run below the project-local run store."""

    def __init__(self, root: str | os.PathLike[str], run_id: str) -> None:
        self.store = RunStore.open(Path(root), run_id)

    def inspect(self) -> dict[str, Any]:
        """Return the principal artifacts as one versioned mapping."""

        artifacts: dict[str, Any] = {
            "schema_version": 1,
            "run_id": self.store.run_id,
            "integrity": self.store.verify_integrity().to_dict(),
        }
        for key in ("metadata", "policy", "before", "after", "runtime", "result"):
            artifacts[key] = self.store.read_json(f"{key}.json")
        for key in ("rollback-result", "cleanup-result"):
            target = self.store.run_dir / f"{key}.json"
            if target.exists() and not target.is_symlink():
                artifacts[key.replace("-", "_")] = self.store.read_json(f"{key}.json")

        metadata = artifacts["metadata"]
        result = artifacts["result"]
        if not isinstance(metadata, dict) or metadata.get("run_id") != self.store.run_id:
            raise ValueError("run metadata does not match requested run id")
        if not isinstance(result, dict) or result.get("run_id") != self.store.run_id:
            raise ValueError("run result does not match requested run id")
        return artifacts

    def summary(self) -> RunSummary:
        """Return a stable one-line summary without reading backup content."""

        metadata = self.store.read_json("metadata.json")
        result = self.store.read_json("result.json")
        runtime = self.store.read_json("runtime.json")
        if (
            not isinstance(metadata, dict)
            or not isinstance(result, dict)
            or not isinstance(runtime, dict)
        ):
            raise ValueError("run artifacts must be JSON objects")
        command = metadata.get("command", [])
        if not isinstance(command, list) or any(not isinstance(item, str) for item in command):
            raise ValueError("run command must be a list of strings")
        blast = result.get("blast_radius", {})
        if not isinstance(blast, dict):
            raise ValueError("blast_radius must be an object")
        raw_returncode = runtime.get("returncode")
        integrity = self.store.verify_integrity()
        return RunSummary(
            run_id=self.store.run_id,
            created_at=str(metadata.get("created_at", "")),
            task=str(metadata["task"]) if metadata.get("task") is not None else None,
            status=str(result.get("status", "unknown")),
            safety_outcome=str(result.get("safety_outcome", "unknown")),
            blast_radius=int(blast.get("score", 0)),
            returncode=int(raw_returncode) if raw_returncode is not None else None,
            command=tuple(command),
            integrity_ok=integrity.ok if integrity.present else None,
        )

    def cleanup(self, *, grace_period_seconds: float = 1.0) -> CleanupReport:
        """Clean only stored PID/create-time identities and persist every decision."""

        integrity = self.store.verify_integrity()
        if not integrity.present:
            raise PermissionError("sealed capsule integrity is required")
        if not integrity.ok:
            raise PermissionError("capsule integrity verification failed")
        runtime = self.store.read_json("runtime.json")
        if not isinstance(runtime, dict):
            raise ValueError("runtime artifact must be an object")
        raw_processes = runtime.get("owned_processes", [])
        if not isinstance(raw_processes, list):
            raise ValueError("owned_processes must be a list")
        processes: list[OwnedProcess] = []
        for raw in raw_processes:
            if not isinstance(raw, dict):
                raise ValueError("owned process evidence must be an object")
            process = OwnedProcess(
                pid=int(raw["pid"]),
                create_time=float(raw["create_time"]),
                parent_pid=int(raw["parent_pid"]) if raw.get("parent_pid") is not None else None,
                relation=str(raw["relation"]),
            )
            if process.pid <= 0 or process.create_time <= 0:
                raise ValueError("owned process identity must be positive")
            if process.relation not in {"direct", "descendant"}:
                raise ValueError("owned process relation is invalid")
            processes.append(process)

        report = LocalRuntime(self.store.root, observe_ports=False).cleanup(
            processes,
            grace_period_seconds=grace_period_seconds,
        )
        self.store.write_json("cleanup-result.json", report.to_dict())
        self.store.append_event(
            "cleanup_completed",
            {
                "targeted": report.targeted,
                "outcomes": len(report.outcomes),
            },
        )
        return report


def list_runs(root: str | os.PathLike[str], *, limit: int | None = None) -> list[RunSummary]:
    """List valid run capsules newest-first without following directory symlinks."""

    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")
    project_root = Path(root).expanduser().resolve(strict=True)
    agentdiff_dir = project_root / ".agentdiff"
    runs_dir = agentdiff_dir / "runs"
    if not runs_dir.exists():
        return []
    if agentdiff_dir.is_symlink() or runs_dir.is_symlink() or not runs_dir.is_dir():
        raise OSError("unsafe run-store directory")

    summaries: list[RunSummary] = []
    for entry in os.scandir(runs_dir):
        if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
            continue
        try:
            summaries.append(RunInspector(project_root, entry.name).summary())
        except (KeyError, OSError, TypeError, ValueError):
            continue
    summaries.sort(key=lambda item: (item.created_at, item.run_id), reverse=True)
    return summaries[:limit]

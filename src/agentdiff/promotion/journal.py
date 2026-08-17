"""Write-ahead promotion journal for crash-consistent multi-file promotion."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class JournalState(str, Enum):
    IDLE = "IDLE"
    PLAN_RECORDED = "PLAN_RECORDED"
    STAGED = "STAGED"
    APPLYING = "APPLYING"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass
class JournalEntry:
    path: str
    change_type: str
    base_sha256: str | None
    result_sha256: str | None
    base_mode: int | None
    result_mode: int | None
    staged_relpath: str | None = None
    backup_relpath: str | None = None
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalEntry:
        return cls(
            path=str(data["path"]),
            change_type=str(data["change_type"]),
            base_sha256=data.get("base_sha256"),
            result_sha256=data.get("result_sha256"),
            base_mode=data.get("base_mode"),
            result_mode=data.get("result_mode"),
            staged_relpath=data.get("staged_relpath"),
            backup_relpath=data.get("backup_relpath"),
            applied=bool(data.get("applied", False)),
        )


@dataclass
class PromotionJournal:
    """Crash-consistent write-ahead journal stored in .agentdiff/promotion-journal.json."""

    root: Path
    run_id: str
    patch_digest: str
    state: JournalState = JournalState.PLAN_RECORDED
    entries: list[JournalEntry] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def path(self) -> Path:
        return self.root / ".agentdiff" / "promotion-journal.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "run_id": self.run_id,
            "patch_digest": self.patch_digest,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def persist(self) -> None:
        """Atomically persist journal state with fsync."""
        self.updated_at = datetime.now(timezone.utc).isoformat()
        journal_dir = self.path.parent
        journal_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, sort_keys=True)

        fd, temp_path = tempfile.mkstemp(
            prefix="journal-",
            suffix=".tmp",
            dir=str(journal_dir),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, str(self.path))
        except BaseException:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    @classmethod
    def load(cls, root: str | Path) -> PromotionJournal | None:
        target = Path(root).resolve() / ".agentdiff" / "promotion-journal.json"
        if not target.is_file():
            return None
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            return cls(
                root=Path(root).resolve(),
                run_id=str(data["run_id"]),
                patch_digest=str(data["patch_digest"]),
                state=JournalState(data.get("state", "IDLE")),
                created_at=str(data.get("created_at", "")),
                updated_at=str(data.get("updated_at", "")),
                entries=[JournalEntry.from_dict(item) for item in data.get("entries", [])],
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def clean(self) -> None:
        """Remove completed journal file."""
        if self.path.is_file():
            import contextlib

            with contextlib.suppress(OSError):
                self.path.unlink(missing_ok=True)

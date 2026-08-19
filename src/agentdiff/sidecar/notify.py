"""Local notification sink for the zero-touch sidecar.

Notifications are appended to ``<root>/.agentdiff/notifications.jsonl`` and may
be echoed to the console. There is no hosted service: everything stays on the
developer machine.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class Notification:
    """One human-visible lifecycle notification."""

    kind: str  # auto | retry | human | error
    title: str
    message: str = ""
    run_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["created_at"] = self.created_at or _utc_now_iso()
        return value


class Notifier:
    """Append notifications to a JSONL file with strict path handling."""

    def __init__(self, root: str | os.PathLike[str], *, echo: bool = True) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        self.echo = echo
        self.path = self.root / ".agentdiff" / "notifications.jsonl"

    def notify(self, notification: Notification) -> Path:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = json.dumps(notification.to_dict(), sort_keys=True, ensure_ascii=True) + "\n"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_APPEND
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(self.path, flags, 0o600)
        try:
            os.write(descriptor, payload.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if os.name != "nt":
            self.path.chmod(0o600)
        if self.echo:
            kind = notification.kind.upper()
            print(f"[agentdiff:{kind}] {notification.title}")
            if notification.message:
                print(f"  {notification.message}")
        return self.path

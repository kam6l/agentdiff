"""Write-ahead promotion journal for crash-consistent multi-file promotion.

Crash consistency model
-----------------------

A promotion entry moves through an explicit state machine. Every state
transition that precedes a filesystem mutation is persisted and fsynced
**before** the mutation happens (write-ahead), and every post-mutation state
is persisted **after** the mutation and its verification:

    PREPARED
       ↓  (persist + fsync)
    APPLY_INTENT      ← mutation may now occur; recovery must disambiguate
       ↓  (mutate → verify)
    APPLIED
       ↓
    RECOVER_INTENT    ← recovery may now mutate; recovery disambiguates
       ↓
    RECOVERED

``AMBIGUOUS`` is a terminal fail-closed state: the journal entry's expected
base/result state cannot be distinguished from the current host state, so
automatic recovery refuses to overwrite anything.

A journal file that exists but cannot be parsed safely is **corrupt**, not
absent: promotion and recovery must fail closed instead of treating it like
"no journal".
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

_JOURNAL_SCHEMA_VERSION = 3
_LEGACY_SCHEMA_VERSION = 2
_LEGACY_CHANGE_TYPES = frozenset({"created", "modified", "deleted"})


class JournalState(str, Enum):
    """Transaction-level promotion state."""

    IDLE = "IDLE"
    PLAN_RECORDED = "PLAN_RECORDED"
    STAGED = "STAGED"
    APPLYING = "APPLYING"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECOVERY_FAILED = "RECOVERY_FAILED"


class EntryState(str, Enum):
    """Per-entry write-ahead and recovery state."""

    PREPARED = "PREPARED"
    APPLY_INTENT = "APPLY_INTENT"
    APPLIED = "APPLIED"
    RECOVER_INTENT = "RECOVER_INTENT"
    RECOVERED = "RECOVERED"
    AMBIGUOUS = "AMBIGUOUS"


class JournalLoadOutcome(str, Enum):
    """Explicit outcome of loading a promotion journal.

    ``CORRUPT_JOURNAL`` is distinct from ``NO_JOURNAL``: a corrupt journal
    must block promotion while an absent journal must not.
    """

    NO_JOURNAL = "NO_JOURNAL"
    VALID_JOURNAL = "VALID_JOURNAL"
    CORRUPT_JOURNAL = "CORRUPT_JOURNAL"


@dataclass(frozen=True, slots=True)
class JournalLoadResult:
    """Parsed journal plus its explicit load outcome."""

    outcome: JournalLoadOutcome
    journal: "PromotionJournal | None" = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome is JournalLoadOutcome.VALID_JOURNAL


@dataclass
class JournalEntry:
    """One planned filesystem mutation with write-ahead state."""

    path: str
    change_type: str
    base_sha256: str | None
    result_sha256: str | None
    base_mode: int | None
    result_mode: int | None
    state: EntryState = EntryState.PREPARED
    base_size: int | None = None
    result_size: int | None = None
    staged_relpath: str | None = None
    backup_relpath: str | None = None
    applied: bool = False

    def __post_init__(self) -> None:
        if self.applied and self.state is EntryState.PREPARED:
            self.state = EntryState.APPLIED
        elif self.state is EntryState.APPLIED:
            self.applied = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value if isinstance(self.state, EntryState) else str(self.state)
        d["applied"] = self.applied or (self.state is EntryState.APPLIED)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalEntry:
        path = data.get("path")
        change_type = data.get("change_type")
        if not isinstance(path, str) or not isinstance(change_type, str):
            raise ValueError("journal entry path/change_type must be strings")
        if change_type not in _LEGACY_CHANGE_TYPES:
            raise ValueError(f"invalid journal change type: {change_type!r}")
        # Legacy schema 2 journals only carried ``applied: bool``. Map that
        # onto the new state machine conservatively: applied=True means the
        # mutation was recorded as complete (APPLIED); applied=False means
        # the entry was never confirmed applied (PREPARED). Legacy journals
        # cannot express APPLY_INTENT, which is exactly the crash window this
        # state machine closes for new journals.
        raw_state = data.get("state")
        if raw_state is None and "applied" in data:
            raw_state = (
                EntryState.APPLIED.value if bool(data["applied"]) else EntryState.PREPARED.value
            )
        if raw_state is None:
            raw_state = EntryState.PREPARED.value
        try:
            state = EntryState(str(raw_state))
        except ValueError as error:
            raise ValueError(f"invalid journal entry state: {raw_state!r}") from error
        for key in ("base_sha256", "result_sha256", "staged_relpath", "backup_relpath"):
            value = data.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"journal entry {key} must be a string or null")
        for key in ("base_mode", "result_mode", "base_size", "result_size"):
            value = data.get(key)
            if value is not None and not isinstance(value, int):
                raise ValueError(f"journal entry {key} must be an integer or null")
        return cls(
            path=path,
            change_type=change_type,
            base_sha256=data.get("base_sha256"),
            result_sha256=data.get("result_sha256"),
            base_mode=data.get("base_mode"),
            result_mode=data.get("result_mode"),
            state=state,
            base_size=data.get("base_size"),
            result_size=data.get("result_size"),
            staged_relpath=data.get("staged_relpath"),
            backup_relpath=data.get("backup_relpath"),
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
    schema_version: int = _JOURNAL_SCHEMA_VERSION

    @property
    def path(self) -> Path:
        return self.root / ".agentdiff" / "promotion-journal.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "patch_digest": self.patch_digest,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def persist(self) -> None:
        """Atomically persist journal state with fsync of file and directory."""
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
            _fsync_directory(journal_dir)
        except BaseException:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    @classmethod
    def load(cls, root: str | Path) -> JournalLoadResult:
        """Load the promotion journal with an explicit load outcome.

        Returns ``NO_JOURNAL`` only when no journal file exists. Any journal
        file that exists but cannot be parsed and validated returns
        ``CORRUPT_JOURNAL`` with a reason. Callers must fail closed on
        ``CORRUPT_JOURNAL``.
        """
        target = Path(root).resolve() / ".agentdiff" / "promotion-journal.json"
        if not target.is_file() or target.is_symlink():
            if target.is_symlink():
                return JournalLoadResult(
                    JournalLoadOutcome.CORRUPT_JOURNAL,
                    error="promotion journal is a symlink",
                )
            return JournalLoadResult(JournalLoadOutcome.NO_JOURNAL)
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return JournalLoadResult(
                    JournalLoadOutcome.CORRUPT_JOURNAL,
                    error="promotion journal root must be an object",
                )
            schema = data.get("schema_version")
            if schema not in {_LEGACY_SCHEMA_VERSION, _JOURNAL_SCHEMA_VERSION}:
                return JournalLoadResult(
                    JournalLoadOutcome.CORRUPT_JOURNAL,
                    error=f"unsupported promotion journal schema: {schema!r}",
                )
            run_id = data.get("run_id")
            patch_digest = data.get("patch_digest")
            state_value = data.get("state")
            if not isinstance(run_id, str) or not isinstance(patch_digest, str):
                return JournalLoadResult(
                    JournalLoadOutcome.CORRUPT_JOURNAL,
                    error="promotion journal run_id/patch_digest must be strings",
                )
            try:
                state = JournalState(str(state_value))
            except (TypeError, ValueError):
                return JournalLoadResult(
                    JournalLoadOutcome.CORRUPT_JOURNAL,
                    error=f"invalid promotion journal state: {state_value!r}",
                )
            raw_entries = data.get("entries")
            if not isinstance(raw_entries, list):
                return JournalLoadResult(
                    JournalLoadOutcome.CORRUPT_JOURNAL,
                    error="promotion journal entries must be a list",
                )
            entries: list[JournalEntry] = []
            for index, item in enumerate(raw_entries):
                if not isinstance(item, dict):
                    return JournalLoadResult(
                        JournalLoadOutcome.CORRUPT_JOURNAL,
                        error=f"journal entry {index} must be an object",
                    )
                try:
                    entries.append(JournalEntry.from_dict(item))
                except (TypeError, ValueError) as error:
                    return JournalLoadResult(
                        JournalLoadOutcome.CORRUPT_JOURNAL,
                        error=f"journal entry {index} is invalid: {error}",
                    )
            created_at = data.get("created_at", "")
            updated_at = data.get("updated_at", "")
            if not isinstance(created_at, str) or not isinstance(updated_at, str):
                return JournalLoadResult(
                    JournalLoadOutcome.CORRUPT_JOURNAL,
                    error="promotion journal timestamps must be strings",
                )
            return JournalLoadResult(
                JournalLoadOutcome.VALID_JOURNAL,
                journal=cls(
                    root=Path(root).resolve(),
                    run_id=run_id,
                    patch_digest=patch_digest,
                    state=state,
                    entries=entries,
                    created_at=created_at,
                    updated_at=updated_at,
                    schema_version=schema,
                ),
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            return JournalLoadResult(
                JournalLoadOutcome.CORRUPT_JOURNAL,
                error=f"promotion journal is unreadable: {type(error).__name__}",
            )

    def clean(self) -> None:
        """Remove a completed journal file (only safe after COMMITTED/ROLLED_BACK)."""
        if self.path.is_file():
            with contextlib.suppress(OSError):
                self.path.unlink(missing_ok=True)


def _fsync_directory(directory: Path) -> None:
    """Best-effort directory fsync so the journal rename is durable."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)

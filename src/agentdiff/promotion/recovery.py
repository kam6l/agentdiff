"""Crash-recovery engine for interrupted promotion transactions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .journal import JournalState, PromotionJournal


@dataclass
class RecoveryReport:
    run_id: str
    status: str
    restored: list[str]
    cleaned: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "restored": self.restored,
            "cleaned": self.cleaned,
            "errors": self.errors,
        }


class PromotionRecovery:
    """Detect and rollback partially applied promotions using the write-ahead journal."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def check_and_recover(self) -> RecoveryReport | None:
        """Check for an interrupted journal and restore host state if needed."""
        journal = PromotionJournal.load(self.root)
        if journal is None or journal.state in {JournalState.COMMITTED, JournalState.ROLLED_BACK}:
            return None

        report = RecoveryReport(
            run_id=journal.run_id,
            status="IN_PROGRESS",
            restored=[],
            cleaned=[],
            errors=[],
        )

        if journal.state in {JournalState.APPLYING, JournalState.RECOVERY_REQUIRED}:
            for entry in journal.entries:
                if not entry.applied:
                    continue

                host_path = self.root / entry.path
                if entry.change_type == "created":
                    try:
                        if host_path.is_file():
                            host_path.unlink()
                            report.cleaned.append(entry.path)
                    except OSError as exc:
                        report.errors.append(f"failed to remove created file {entry.path}: {exc}")

                elif entry.change_type in {"modified", "deleted"} and entry.backup_relpath:
                    backup_path = self.root / entry.backup_relpath
                    if backup_path.is_file():
                        try:
                            host_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                            os.replace(str(backup_path), str(host_path))
                            report.restored.append(entry.path)
                        except OSError as exc:
                            report.errors.append(f"failed to restore {entry.path}: {exc}")

            if report.errors:
                journal.state = JournalState.RECOVERY_REQUIRED
                report.status = "RECOVERY_FAILED"
            else:
                journal.state = JournalState.ROLLED_BACK
                report.status = "RECOVERED"
            journal.persist()

        elif journal.state in {JournalState.PLAN_RECORDED, JournalState.STAGED}:
            # Safe to discard unapplied staging
            journal.clean()
            report.status = "CLEANED_UNAPPLIED"

        return report

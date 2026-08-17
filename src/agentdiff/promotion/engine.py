"""Fail-closed host promotion for proven, policy-selected patch entries."""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import tempfile
from pathlib import Path

from agentdiff.evidence import PatchBundle, PatchEntry
from agentdiff.pathing import normalize_relative_path
from agentdiff.state import FileRecord, FilesystemScanner
from agentdiff.transaction.store import RunStore

from .journal import JournalEntry, JournalState, PromotionJournal
from .lock import WorkspaceLease
from .models import (
    PromotionAction,
    PromotionConflict,
    PromotionPlan,
    PromotionPlanEntry,
    PromotionReport,
)
from .recovery import PromotionRecovery
from .staging import PromotionStager


class PromotionEngine:
    """Plan and atomically apply only unchanged-base, proven regular-file changes."""

    def __init__(self, root: str | Path, run_id: str) -> None:
        self.store = RunStore.open(root, run_id)
        self.root = self.store.root
        self.scanner = FilesystemScanner(self.root)
        self.lease = WorkspaceLease(self.root, run_id)
        self.stager = PromotionStager(self.root, run_id)

    @classmethod
    def open(cls, root: str | Path, run_id: str) -> "PromotionEngine":
        return cls(root, run_id)

    def promote(
        self,
        *,
        dry_run: bool = False,
        safe_only: bool = False,
        paths: list[str] | None = None,
    ) -> PromotionReport:
        with self.lease.hold():
            # Pre-flight: recover any stale crashed journal if present
            PromotionRecovery(self.root).check_and_recover()

            integrity = self.store.verify_integrity()
            if not integrity.ok:
                raise PermissionError("sealed capsule integrity verification failed")
            proof_integrity = self.store.verify_extension("proof")
            if not proof_integrity.ok:
                raise PermissionError("sealed proof evidence is required")
            proof = self.store.read_json_path("proof/result.json")
            if not isinstance(proof, dict) or proof.get("verdict") != "PROVEN":
                raise PermissionError("promotion is blocked until clean-room proof is PROVEN")
            bundle = PatchBundle(self.store)
            if proof.get("patch_digest") != bundle.manifest.digest:
                raise PermissionError("proof does not match the sealed patch")
            if proof.get("immutable_manifest_sha256") != self.store.immutable_manifest_sha256():
                raise PermissionError("proof does not match immutable run evidence")
            selected = self._normalize_selection(paths)
            plan = self._plan(bundle, safe_only=safe_only, selected=selected)
            self.store.write_json_path("promotion/plan.json", plan.to_dict())
            report = PromotionReport(
                run_id=self.store.run_id,
                status="CONFLICT",
                dry_run=dry_run,
                patch_digest=bundle.manifest.digest,
            )
            for entry in plan.entries:
                if entry.disposition == "conflict":
                    report.conflicts.append(PromotionConflict(entry.path, entry.reason))
                elif entry.disposition in {"skip", "already_applied"}:
                    report.skipped.append(entry.path)
            if not plan.ready:
                report.status = "CONFLICT"
                self._persist_result(report)
                return report
            if dry_run:
                report.status = "DRY_RUN_SAFE"
                report.actions.extend(
                    PromotionAction(entry.path, "would_apply", entry.change_type)
                    for entry in plan.entries
                    if entry.disposition == "ready"
                )
                self._persist_result(report)
                return report

            entries_by_path = {entry.path: entry for entry in bundle.manifest.entries}
            ready = [entry for entry in plan.entries if entry.disposition == "ready"]
            # Re-plan the entire selected set immediately before write-ahead log
            latest = self._plan(bundle, safe_only=safe_only, selected=selected)
            if not latest.ready or [item.to_dict() for item in latest.entries] != [
                item.to_dict() for item in plan.entries
            ]:
                report.status = "CONFLICT"
                report.conflicts.append(
                    PromotionConflict("<host>", "host state changed after promotion planning")
                )
                self._persist_result(report)
                return report

            # 1. Initialize staging & journal
            self.stager.prepare()
            journal = PromotionJournal(
                root=self.root,
                run_id=self.store.run_id,
                patch_digest=bundle.manifest.digest,
                state=JournalState.STAGED,
            )

            # 2. Stage all modifications and backups
            for planned in ready:
                patch_entry = entries_by_path[planned.path]
                staged_rel = None
                backup_rel = None
                if patch_entry.change_type != "deleted":
                    staged_path = self.stager.stage_entry(bundle, patch_entry)
                    staged_rel = str(staged_path.relative_to(self.root).as_posix())
                if patch_entry.change_type in {"modified", "deleted"}:
                    backup_path = self.stager.backup_host_file(patch_entry.path)
                    if backup_path is not None:
                        backup_rel = str(backup_path.relative_to(self.root).as_posix())

                journal.entries.append(
                    JournalEntry(
                        path=patch_entry.path,
                        change_type=patch_entry.change_type,
                        base_sha256=patch_entry.base_sha256,
                        result_sha256=patch_entry.result_sha256,
                        base_mode=patch_entry.base_mode,
                        result_mode=patch_entry.result_mode,
                        staged_relpath=staged_rel,
                        backup_relpath=backup_rel,
                        applied=False,
                    )
                )

            # 3. Write-ahead log journal commit
            journal.state = JournalState.APPLYING
            journal.persist()

            # 4. Atomic application phase
            for journal_entry, planned in zip(journal.entries, ready, strict=True):
                patch_entry = entries_by_path[planned.path]

                try:
                    action = self._apply_one(bundle, patch_entry)
                    journal_entry.applied = True
                    journal.persist()
                except (OSError, RuntimeError, ValueError) as error:
                    report.conflicts.append(
                        PromotionConflict(patch_entry.path, str(error) or type(error).__name__)
                    )
                    report.status = "PARTIAL_CONFLICT" if report.actions else "CONFLICT"
                    # Interrupted -> trigger recovery
                    journal.state = JournalState.RECOVERY_REQUIRED
                    journal.persist()
                    PromotionRecovery(self.root).check_and_recover()
                    break
                report.actions.append(action)
            else:
                report.status = "PROMOTED"
                journal.state = JournalState.COMMITTED
                journal.persist()
                journal.clean()
                self.stager.clean()

            self._persist_result(report)
            return report

    def _persist_result(self, report: PromotionReport) -> None:
        self.store.write_json_path("promotion/result.json", report.to_dict())
        self.store.seal_extension("promotion", ("plan.json", "result.json"))

    def _plan(
        self,
        bundle: PatchBundle,
        *,
        safe_only: bool,
        selected: set[str],
    ) -> PromotionPlan:
        entries: list[PromotionPlanEntry] = []
        manifest_paths = {entry.path for entry in bundle.manifest.entries}
        unknown = sorted(selected - manifest_paths)
        for path in unknown:
            entries.append(
                PromotionPlanEntry(path, "unknown", "unknown", "conflict", "path is not in patch")
            )
        for entry in bundle.manifest.entries:
            if selected and entry.path not in selected:
                entries.append(
                    PromotionPlanEntry(
                        entry.path,
                        entry.change_type,
                        entry.decision,
                        "skip",
                        "not selected",
                    )
                )
                continue
            if entry.decision == "deny":
                entries.append(
                    PromotionPlanEntry(
                        entry.path,
                        entry.change_type,
                        entry.decision,
                        "conflict",
                        "DENY changes are never promotable",
                    )
                )
                continue
            if safe_only and entry.decision != "allow":
                entries.append(
                    PromotionPlanEntry(
                        entry.path,
                        entry.change_type,
                        entry.decision,
                        "skip",
                        "safe-only selects ALLOW changes",
                    )
                )
                continue
            if not safe_only and entry.decision == "review" and entry.path not in selected:
                entries.append(
                    PromotionPlanEntry(
                        entry.path,
                        entry.change_type,
                        entry.decision,
                        "skip",
                        "REVIEW changes require explicit --path selection",
                    )
                )
                continue
            disposition, reason = self._entry_state(entry)
            entries.append(
                PromotionPlanEntry(
                    entry.path,
                    entry.change_type,
                    entry.decision,
                    disposition,
                    reason,
                )
            )
        applicable = [entry for entry in entries if entry.disposition == "ready"]
        conflicts = [entry for entry in entries if entry.disposition == "conflict"]
        return PromotionPlan(
            run_id=self.store.run_id,
            patch_digest=bundle.manifest.digest,
            safe_only=safe_only,
            selected_paths=tuple(sorted(selected)),
            entries=tuple(entries),
            ready=bool(applicable) and not conflicts,
        )

    def _entry_state(self, entry: PatchEntry) -> tuple[str, str]:
        if not entry.materialized:
            return "conflict", entry.reason or "patch payload is incomplete"
        try:
            target = self._resolve_target(entry.path, create_parents=False)
        except FileNotFoundError:
            target = self.root.joinpath(*entry.path.split("/"))
        except (OSError, ValueError) as error:
            return "conflict", str(error)
        current = self.scanner.capture_one(entry.path)
        if entry.change_type == "created":
            if current is None and not target.is_symlink():
                return "ready", "host path is absent as recorded"
            if self._matches_result(current, entry):
                return "already_applied", "host already equals the proven result"
            return "conflict", "host path now exists or has ambiguous state"
        if entry.change_type == "deleted" and current is None and not target.is_symlink():
            return "already_applied", "host path is already absent"
        if not self._matches_base(current, entry):
            return "conflict", "current host state differs from the recorded base"
        return "ready", "current host state equals the recorded base"

    def _apply_one(self, bundle: PatchBundle, entry: PatchEntry) -> PromotionAction:
        target = self._resolve_target(entry.path, create_parents=entry.change_type == "created")
        current = self.scanner.capture_one(entry.path)
        if entry.change_type == "deleted":
            if not self._matches_base(current, entry):
                raise RuntimeError("host changed before deletion")
            assert current is not None
            latest = target.lstat()
            if (
                not stat.S_ISREG(latest.st_mode)
                or latest.st_nlink != 1
                or latest.st_dev != current.device
                or latest.st_ino != current.inode
            ):
                raise RuntimeError("host changed before deletion")
            target.unlink()
            return PromotionAction(entry.path, "deleted", "proven deletion promoted")
        source = self.store.artifact_path(f"patch/files/{entry.path}")
        if entry.change_type == "created":
            if current is not None or target.exists() or target.is_symlink():
                raise RuntimeError("host path appeared before creation")
            self._atomic_create(source, target, entry)
            return PromotionAction(entry.path, "created", "proven file created")
        if not self._matches_base(current, entry):
            raise RuntimeError("host changed before replacement")
        assert current is not None
        self._atomic_replace(source, target, entry, current)
        return PromotionAction(entry.path, "modified", "proven file replaced")

    def _atomic_create(self, source: Path, target: Path, entry: PatchEntry) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".agentdiff-promote-", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            self._copy_payload(source, descriptor, entry)
            os.close(descriptor)
            descriptor = -1
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as error:
                raise RuntimeError("host path appeared before creation") from error
            if os.name != "nt" and entry.result_mode is not None:
                target.chmod(entry.result_mode)
        finally:
            if descriptor >= 0:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
            temporary.unlink(missing_ok=True)

    def _atomic_replace(
        self,
        source: Path,
        target: Path,
        entry: PatchEntry,
        expected: FileRecord,
    ) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".agentdiff-promote-", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            self._copy_payload(source, descriptor, entry)
            os.close(descriptor)
            descriptor = -1
            latest_record = self.scanner.capture_one(entry.path)
            latest = target.lstat()
            if (
                not self._matches_base(latest_record, entry)
                or latest_record is None
                or not stat.S_ISREG(latest.st_mode)
                or latest.st_nlink != 1
                or latest.st_dev != expected.device
                or latest.st_ino != expected.inode
            ):
                raise RuntimeError("host changed during replacement")
            os.replace(temporary, target)
            if os.name != "nt" and entry.result_mode is not None:
                target.chmod(entry.result_mode)
        finally:
            if descriptor >= 0:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _copy_payload(source: Path, descriptor: int, entry: PatchEntry) -> None:
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("patch payload is not a single-link regular file")
        digest = hashlib.sha256()
        size = 0
        with (
            source.open("rb") as input_stream,
            os.fdopen(descriptor, "wb", closefd=False) as output_stream,
        ):
            while chunk := input_stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                output_stream.write(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        if digest.hexdigest() != entry.result_sha256 or size != entry.size:
            raise RuntimeError("patch payload digest mismatch")

    def _resolve_target(self, relative: str, *, create_parents: bool) -> Path:
        normalized = normalize_relative_path(relative)
        if normalized != relative:
            raise ValueError("unsafe promotion path")
        target = self.root.joinpath(*normalized.split("/"))
        current = self.root
        for part in normalized.split("/")[:-1]:
            current /= part
            if current.exists() or current.is_symlink():
                info = current.lstat()
                if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise ValueError("unsafe promotion parent")
            elif create_parents:
                current.mkdir(mode=0o700)
            else:
                raise FileNotFoundError(current)
        return target

    @staticmethod
    def _matches_base(current: FileRecord | None, entry: PatchEntry) -> bool:
        return bool(
            current is not None
            and current.kind == "file"
            and current.link_count == 1
            and current.sha256 is not None
            and current.sha256 == entry.base_sha256
            and current.mode == entry.base_mode
        )

    @staticmethod
    def _matches_result(current: FileRecord | None, entry: PatchEntry) -> bool:
        return bool(
            current is not None
            and current.kind == "file"
            and current.link_count == 1
            and current.sha256 is not None
            and current.sha256 == entry.result_sha256
            and current.mode == entry.result_mode
        )

    @staticmethod
    def _normalize_selection(paths: list[str] | None) -> set[str]:
        selected: set[str] = set()
        for path in paths or []:
            normalized = normalize_relative_path(path)
            if normalized != path:
                raise ValueError("promotion paths must be normalized relative paths")
            selected.add(normalized)
        return selected

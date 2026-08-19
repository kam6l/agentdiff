"""Sealed base-source and resulting-patch artifacts.

Only normalized, single-link regular files are materialized. Symlinks,
hardlinks, unreadable content, and ambiguous hashes remain explicit evidence
and make clean-room proof or automatic promotion fail closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from agentdiff.pathing import normalize_relative_path

if TYPE_CHECKING:
    from agentdiff.state import FileRecord, FilesystemManifest
    from agentdiff.transaction.store import RunStore


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Result of copying the observed pre-run source into sealed evidence."""

    complete: bool
    captured: tuple[str, ...]
    files: dict[str, dict[str, int | str]]
    unsupported: dict[str, str]
    digest: str
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "complete": self.complete,
            "captured": list(self.captured),
            "files": {path: dict(value) for path, value in sorted(self.files.items())},
            "unsupported": dict(sorted(self.unsupported.items())),
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class PatchEntry:
    """One promotable mutation with both base and result identity."""

    path: str
    change_type: str
    decision: str
    base_sha256: str | None
    result_sha256: str | None
    base_mode: int | None
    result_mode: int | None
    size: int | None
    materialized: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PatchEntry":
        path = normalize_relative_path(str(value["path"]))
        change_type = str(value["change_type"])
        if change_type not in {"created", "modified", "deleted"}:
            raise ValueError("invalid patch change type")
        return cls(
            path=path,
            change_type=change_type,
            decision=str(value["decision"]),
            base_sha256=(
                str(value["base_sha256"]) if value.get("base_sha256") is not None else None
            ),
            result_sha256=(
                str(value["result_sha256"]) if value.get("result_sha256") is not None else None
            ),
            base_mode=int(value["base_mode"]) if value.get("base_mode") is not None else None,
            result_mode=(
                int(value["result_mode"]) if value.get("result_mode") is not None else None
            ),
            size=int(value["size"]) if value.get("size") is not None else None,
            materialized=bool(value["materialized"]),
            reason=str(value.get("reason", "")),
        )


@dataclass(frozen=True, slots=True)
class PatchManifest:
    """Deterministic patch boundary shared by proof and promotion."""

    run_id: str
    entries: tuple[PatchEntry, ...]
    complete: bool
    digest: str
    schema_version: int = 1

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "complete": self.complete,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def content_digest(self) -> str:
        """Run-independent digest of the exact mutation set and payloads.

        The sealed manifest digest includes the run id; the content digest
        deliberately does not, so identical patches produced by different runs
        share a proof-cache identity.
        """
        return _canonical_digest(
            {
                "schema_version": self.schema_version,
                "complete": self.complete,
                "entries": [entry.to_dict() for entry in self.entries],
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "digest": self.digest}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PatchManifest":
        raw_entries = value.get("entries")
        if not isinstance(raw_entries, list):
            raise ValueError("patch entries must be a list")
        manifest = cls(
            schema_version=int(value.get("schema_version", 0)),
            run_id=str(value["run_id"]),
            entries=tuple(
                PatchEntry.from_dict(item) for item in raw_entries if isinstance(item, dict)
            ),
            complete=bool(value["complete"]),
            digest=str(value["digest"]),
        )
        if manifest.schema_version != 1:
            raise ValueError("unsupported patch manifest schema")
        if manifest.digest != _canonical_digest(manifest.unsigned_dict()):
            raise ValueError("patch manifest digest mismatch")
        return manifest


def _eligible_regular(record: FileRecord | None) -> tuple[bool, str]:
    if record is None:
        return False, "file evidence is missing"
    if record.kind != "file":
        return False, "symlink and special-file patches are unsupported"
    if record.sha256 is None:
        return False, "content hash is unavailable"
    if record.link_count != 1:
        return False, "hardlinked files are unsupported"
    return True, "verified regular file"


def capture_source_snapshot(store: RunStore, before: FilesystemManifest) -> SourceSnapshot:
    """Copy the exact observed base files into the pre-seal capsule."""

    store.ensure_artifact_directory("source/files")
    captured: list[str] = []
    files: dict[str, dict[str, int | str]] = {}
    unsupported = dict(before.unsupported)
    for path, record in sorted(before.files.items()):
        eligible, reason = _eligible_regular(record)
        if not eligible:
            unsupported[path] = reason
            continue
        source = store.root.joinpath(*normalize_relative_path(path).split("/"))
        try:
            store.copy_artifact(
                f"source/files/{path}",
                source,
                expected_sha256=str(record.sha256),
                expected_size=record.size,
                mode=record.mode,
            )
        except (OSError, RuntimeError, ValueError) as error:
            unsupported[path] = f"source snapshot failed: {type(error).__name__}"
        else:
            captured.append(path)
            files[path] = {
                "sha256": str(record.sha256),
                "size": record.size,
                "mode": record.mode,
            }
    unsigned: dict[str, Any] = {
        "schema_version": 1,
        "complete": not unsupported,
        "captured": captured,
        "files": files,
        "unsupported": dict(sorted(unsupported.items())),
    }
    snapshot = SourceSnapshot(
        complete=not unsupported,
        captured=tuple(captured),
        files=files,
        unsupported=unsupported,
        digest=_canonical_digest(unsigned),
    )
    store.write_json_path("source/manifest.json", snapshot.to_dict())
    return snapshot


def validate_source_snapshot(store: RunStore, snapshot: SourceSnapshot) -> SourceSnapshot:
    """Revalidate pre-run source evidence after an untrusted local command."""

    valid: list[str] = []
    valid_files: dict[str, dict[str, int | str]] = {}
    unsupported = dict(snapshot.unsupported)
    for path in snapshot.captured:
        expected = snapshot.files[path]
        try:
            digest, size = store.artifact_digest(f"source/files/{path}")
        except (OSError, RuntimeError, ValueError) as error:
            unsupported[path] = f"source evidence lost: {type(error).__name__}"
            continue
        if digest != expected["sha256"] or size != expected["size"]:
            unsupported[path] = "source evidence was modified during execution"
            continue
        valid.append(path)
        valid_files[path] = expected
    unsigned: dict[str, Any] = {
        "schema_version": 1,
        "complete": snapshot.complete and len(valid) == len(snapshot.captured),
        "captured": valid,
        "files": valid_files,
        "unsupported": dict(sorted(unsupported.items())),
    }
    validated = SourceSnapshot(
        complete=bool(unsigned["complete"]) and not unsupported,
        captured=tuple(valid),
        files=valid_files,
        unsupported=unsupported,
        digest=_canonical_digest(unsigned),
    )
    store.write_json_path("source/manifest.json", validated.to_dict())
    return validated


def capture_patch(
    store: RunStore,
    *,
    changes: Iterable[Any],
    before: FilesystemManifest,
    after: FilesystemManifest,
    after_root: str | Path,
) -> PatchManifest:
    """Persist exactly the assessed mutation set and result contents."""

    store.ensure_artifact_directory("patch/files")
    result_root = Path(after_root).resolve(strict=True)
    entries: list[PatchEntry] = []
    complete = True
    for change in sorted(changes, key=lambda item: item.path):
        old = before.files.get(change.path)
        new = after.files.get(change.path)
        materialized = change.change_type == "deleted"
        reason = "deletion requires no result payload" if materialized else ""
        if change.change_type != "deleted":
            eligible, reason = _eligible_regular(new)
            materialized = eligible
            if eligible and new is not None:
                source = result_root.joinpath(*normalize_relative_path(change.path).split("/"))
                try:
                    store.copy_artifact(
                        f"patch/files/{change.path}",
                        source,
                        expected_sha256=str(new.sha256),
                        expected_size=new.size,
                        mode=new.mode,
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    materialized = False
                    reason = f"patch materialization failed: {type(error).__name__}"
        complete = complete and materialized
        entries.append(
            PatchEntry(
                path=change.path,
                change_type=change.change_type,
                decision=change.decision.action.value,
                base_sha256=old.sha256 if old is not None else None,
                result_sha256=new.sha256 if new is not None else None,
                base_mode=old.mode if old is not None else None,
                result_mode=new.mode if new is not None else None,
                size=new.size if new is not None else None,
                materialized=materialized,
                reason=reason,
            )
        )
    unsigned = {
        "schema_version": 1,
        "run_id": store.run_id,
        "complete": complete,
        "entries": [entry.to_dict() for entry in entries],
    }
    manifest = PatchManifest(
        run_id=store.run_id,
        entries=tuple(entries),
        complete=complete,
        digest=_canonical_digest(unsigned),
    )
    store.write_json_path("mutations/manifest.json", manifest.to_dict())
    return manifest


class PatchBundle:
    """Read and replay sealed source/patch evidence into an empty workspace."""

    def __init__(self, store: RunStore) -> None:
        self.store = store
        self.manifest = PatchManifest.from_dict(store.read_json_path("mutations/manifest.json"))
        if self.manifest.run_id != store.run_id:
            raise ValueError("patch manifest run id mismatch")

    def entry_path(self, entry: PatchEntry) -> Path:
        return self.store.artifact_path(f"patch/files/{entry.path}")

    def materialize_source(self, destination: str | Path) -> None:
        target_root = Path(destination).resolve(strict=True)
        raw = self.store.read_json_path("source/manifest.json")
        if not isinstance(raw, dict) or int(raw.get("schema_version", 0)) != 1:
            raise ValueError("unsupported source snapshot schema")
        if not bool(raw.get("complete")):
            raise RuntimeError("base source snapshot is incomplete")
        captured = raw.get("captured")
        if not isinstance(captured, list) or any(not isinstance(item, str) for item in captured):
            raise ValueError("source snapshot paths are invalid")
        files = raw.get("files")
        unsigned = {
            "schema_version": 1,
            "complete": bool(raw.get("complete")),
            "captured": captured,
            "files": files,
            "unsupported": dict(sorted(dict(raw.get("unsupported", {})).items())),
        }
        if not isinstance(files, dict) or raw.get("digest") != _canonical_digest(unsigned):
            raise ValueError("source snapshot digest mismatch")
        for path in captured:
            expected = files.get(path)
            if not isinstance(expected, dict):
                raise ValueError("source snapshot file identity is missing")
            digest, size = self.store.artifact_digest(f"source/files/{path}")
            if digest != expected.get("sha256") or size != expected.get("size"):
                raise RuntimeError("source snapshot payload digest mismatch")
            self._copy_capsule_file(
                f"source/files/{normalize_relative_path(path)}",
                target_root,
                path,
            )

    def apply(self, destination: str | Path) -> None:
        if not self.manifest.complete:
            raise RuntimeError("patch evidence is incomplete")
        target_root = Path(destination).resolve(strict=True)
        for entry in self.manifest.entries:
            target = self._safe_target(target_root, entry.path)
            if entry.change_type == "deleted":
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise RuntimeError(f"unsafe deletion target: {entry.path}")
                target.unlink(missing_ok=True)
                continue
            self._copy_capsule_file(f"patch/files/{entry.path}", target_root, entry.path)
            if os.name != "nt" and entry.result_mode is not None:
                target.chmod(entry.result_mode)

    def _copy_capsule_file(self, artifact: str, root: Path, relative: str) -> None:
        target = self._safe_target(root, relative, create_parents=True)
        source = self.store.artifact_path(artifact)
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError("capsule payload is not a single-link regular file")
        if target.exists() and target.is_symlink():
            raise RuntimeError(f"unsafe patch target: {relative}")
        temporary = target.parent / (
            f".agentdiff-{hashlib.sha256(relative.encode()).hexdigest()}.tmp"
        )
        try:
            with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _safe_target(root: Path, relative: str, *, create_parents: bool = False) -> Path:
        normalized = normalize_relative_path(relative)
        target = root.joinpath(*normalized.split("/"))
        current = root
        for part in normalized.split("/")[:-1]:
            current /= part
            if current.exists() or current.is_symlink():
                info = current.lstat()
                if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise RuntimeError(f"unsafe patch parent: {relative}")
            elif create_parents:
                current.mkdir(mode=0o700)
            else:
                raise RuntimeError(f"missing patch parent: {relative}")
        return target

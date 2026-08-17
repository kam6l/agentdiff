"""Versioned, private storage for local agent transactions."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
import stat
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agentdiff import __version__
from agentdiff.pathing import normalize_relative_path
from agentdiff.redaction import redact_argv, redact_data

SCHEMA_VERSION = 1
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,95}$")
_ARTIFACT_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*\.json$")
_MAX_JSON_BYTES = 64 * 1024 * 1024
_MAX_EVENT_BYTES = 1024 * 1024
_MUTABLE_AFTER_SEAL = frozenset(
    {"rollback-result.json", "cleanup-result.json", "recovery-events.jsonl"}
)
_REQUIRED_SEALED_ARTIFACTS = frozenset(
    {
        "metadata.json",
        "policy.json",
        "before.json",
        "after.json",
        "runtime.json",
        "result.json",
        "events.jsonl",
    }
)


class InvalidRunIdError(ValueError):
    """Raised when a run identifier could escape the run store."""


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    """One missing, unexpected, unsafe, or digest-mismatched capsule path."""

    path: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    """Result of verifying a run capsule's sealed SHA-256 manifest."""

    present: bool
    ok: bool
    files_checked: int
    issues: tuple[IntegrityIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "present": self.present,
            "ok": self.ok,
            "files_checked": self.files_checked,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(6)}"


def validate_run_id(run_id: str) -> str:
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise InvalidRunIdError("invalid run id")
    return run_id


def _ensure_private_directory(path: Path) -> None:
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise OSError(f"unsafe run-store directory: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)


class RunStore:
    """Access one run below ``<root>/.agentdiff/runs``."""

    def __init__(
        self,
        root: Path,
        run_id: str,
        run_dir: Path,
        *,
        track_events: bool = False,
    ) -> None:
        self.root = root
        self.run_id = run_id
        self.run_dir = run_dir
        self.backup_dir = run_dir / "backup"
        self._trusted_events: list[bytes] | None = [] if track_events else None
        identity = run_dir.lstat()
        if not stat.S_ISDIR(identity.st_mode) or stat.S_ISLNK(identity.st_mode):
            raise InvalidRunIdError("unsafe run directory")
        self._run_identity = (identity.st_dev, identity.st_ino)

    def _ensure_run_dir_identity(self) -> None:
        try:
            current = self.run_dir.lstat()
        except FileNotFoundError as error:
            raise InvalidRunIdError("run directory identity changed") from error
        if (
            not stat.S_ISDIR(current.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or (current.st_dev, current.st_ino) != self._run_identity
        ):
            raise InvalidRunIdError("run directory identity changed")

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        task: str | None,
        command: Iterable[str],
        run_id: str | None = None,
    ) -> "RunStore":
        project_root = Path(root).expanduser().resolve(strict=True)
        if not project_root.is_dir():
            raise ValueError("project root must be a directory")
        selected = validate_run_id(run_id or _new_run_id())
        agentdiff_dir = project_root / ".agentdiff"
        runs_dir = agentdiff_dir / "runs"
        _ensure_private_directory(agentdiff_dir)
        _ensure_private_directory(runs_dir)
        run_dir = runs_dir / selected
        if run_dir.exists():
            raise FileExistsError(f"run already exists: {selected}")
        run_dir.mkdir(mode=0o700)
        _ensure_private_directory(run_dir / "backup")
        store = cls(project_root, selected, run_dir, track_events=True)
        store.write_json(
            "metadata.json",
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": selected,
                "created_at": _utc_now(),
                "task": task,
                "command": redact_argv(command),
                "root": str(project_root),
                "agentdiff_version": __version__,
                "python_version": platform.python_version(),
                "platform": sys.platform,
            },
        )
        store.append_event("transaction_created", {})
        return store

    @classmethod
    def open(cls, root: str | Path, run_id: str) -> "RunStore":
        project_root = Path(root).expanduser().resolve(strict=True)
        selected = validate_run_id(run_id)
        agentdiff_dir = project_root / ".agentdiff"
        runs_dir = agentdiff_dir / "runs"
        run_dir = runs_dir / selected
        if (
            agentdiff_dir.is_symlink()
            or runs_dir.is_symlink()
            or run_dir.is_symlink()
            or not run_dir.is_dir()
        ):
            raise FileNotFoundError(f"run not found: {selected}")
        resolved = run_dir.resolve(strict=True)
        expected_parent = runs_dir.resolve(strict=True)
        if resolved.parent != expected_parent:
            raise InvalidRunIdError("run path escaped the run store")
        store = cls(project_root, selected, resolved)
        metadata = store.read_json("metadata.json")
        recorded_root = Path(str(metadata.get("root", ""))).expanduser().resolve(strict=False)
        if recorded_root != project_root or metadata.get("run_id") != selected:
            raise InvalidRunIdError("run metadata does not match project root")
        if store.backup_dir.is_symlink():
            raise InvalidRunIdError("unsafe backup directory")
        return store

    def finalize_integrity(self) -> dict[str, Any]:
        """Seal immutable run artifacts with a deterministic SHA-256 manifest.

        The manifest is tamper-evident, not authenticated: a process able to
        rewrite the entire capsule can also rewrite its checksums. Stronger
        runtimes should keep or sign this manifest outside the wrapped root.
        """

        self._ensure_run_dir_identity()
        integrity_path = self.run_dir / "integrity" / "manifest.json"
        if integrity_path.exists():
            raise RuntimeError("run capsule is already sealed")
        discovered = self._discover_sealed_files()
        discovered_names = {relative for relative, _ in discovered}
        missing_principal = sorted(_REQUIRED_SEALED_ARTIFACTS - discovered_names)
        if missing_principal:
            raise RuntimeError("missing required sealed artifacts: " + ", ".join(missing_principal))
        required = self._required_sealed_paths()
        missing = sorted(required - discovered_names)
        if missing:
            raise RuntimeError("missing required sealed artifacts: " + ", ".join(missing))
        files: dict[str, dict[str, int | str]] = {}
        for relative, path in discovered:
            digest, size = self._hash_regular_artifact(path)
            files[relative] = {"sha256": digest, "size": size}
        manifest: dict[str, Any] = {
            "schema_version": 2,
            "algorithm": "sha256",
            "created_at": _utc_now(),
            "files": dict(sorted(files.items())),
        }
        self.write_json_path("integrity/manifest.json", manifest)
        self.write_json("integrity.json", manifest)
        return manifest

    def verify_integrity(self) -> IntegrityReport:
        """Verify a sealed capsule without following links."""

        self._ensure_run_dir_identity()
        v2_integrity = self.run_dir / "integrity" / "manifest.json"
        v1_integrity = self.run_dir / "integrity.json"
        if not v2_integrity.exists() and not v1_integrity.exists():
            return IntegrityReport(present=False, ok=False, files_checked=0)
        issues: list[IntegrityIssue] = []
        if not v2_integrity.exists():
            issues.append(IntegrityIssue("integrity/manifest.json", "missing integrity manifest"))
            return IntegrityReport(present=True, ok=False, files_checked=0, issues=tuple(issues))
        try:
            manifest = self.read_json_path("integrity/manifest.json")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            return IntegrityReport(
                present=True,
                ok=False,
                files_checked=0,
                issues=(IntegrityIssue("integrity/manifest.json", type(error).__name__),),
            )
        if not isinstance(manifest, dict) or manifest.get("algorithm") != "sha256":
            return IntegrityReport(
                present=True,
                ok=False,
                files_checked=0,
                issues=(IntegrityIssue("integrity/manifest.json", "invalid integrity manifest"),),
            )
        raw_files = manifest.get("files")
        if not isinstance(raw_files, dict):
            return IntegrityReport(
                present=True,
                ok=False,
                files_checked=0,
                issues=(IntegrityIssue("integrity/manifest.json", "files must be an object"),),
            )

        try:
            actual_files = dict(self._discover_sealed_files())
        except (OSError, ValueError) as error:
            return IntegrityReport(
                present=True,
                ok=False,
                files_checked=0,
                issues=(IntegrityIssue("<capsule>", str(error)),),
            )
        expected_names = {str(name) for name in raw_files}
        required = set(_REQUIRED_SEALED_ARTIFACTS)
        try:
            if "before.json" in actual_files:
                required = self._required_sealed_paths()
        except (OSError, TypeError, ValueError) as error:
            issues.append(IntegrityIssue("before.json", f"invalid recovery evidence: {error}"))
        for missing in sorted(required - expected_names):
            issues.append(IntegrityIssue(missing, "required artifact absent from manifest"))
        for unexpected in sorted(set(actual_files) - expected_names):
            issues.append(IntegrityIssue(unexpected, "unexpected sealed artifact"))

        checked = 0
        for relative in sorted(expected_names):
            expected = raw_files.get(relative)
            if not isinstance(expected, dict):
                issues.append(IntegrityIssue(relative, "invalid digest entry"))
                continue
            path = actual_files.get(relative)
            if path is None:
                issues.append(IntegrityIssue(relative, "missing artifact"))
                continue
            try:
                digest, size = self._hash_regular_artifact(path)
            except (OSError, ValueError, RuntimeError) as error:
                issues.append(IntegrityIssue(relative, str(error)))
                continue
            checked += 1
            if expected.get("sha256") != digest or expected.get("size") != size:
                issues.append(IntegrityIssue(relative, "digest or size mismatch"))
        return IntegrityReport(
            present=True,
            ok=not issues,
            files_checked=checked,
            issues=tuple(issues),
        )

    def _required_sealed_paths(self) -> set[str]:
        """Return principal artifacts plus every backup referenced by before-state."""

        required = set(_REQUIRED_SEALED_ARTIFACTS)
        before = self.read_json("before.json")
        if not isinstance(before, dict) or not isinstance(before.get("files"), dict):
            raise InvalidRunIdError("before.json has no files mapping")
        for record in before["files"].values():
            if not isinstance(record, dict) or record.get("backup_path") is None:
                continue
            raw = str(record["backup_path"])
            normalized = normalize_relative_path(raw)
            if normalized != raw:
                raise InvalidRunIdError("before.json contains a non-normalized backup path")
            required.add(f"backup/{normalized}")
        return required

    def verify_backup(self, relative: str, *, sha256: str, size: int) -> None:
        """Verify one before-state backup against trusted in-memory evidence."""

        self._ensure_run_dir_identity()
        normalized = normalize_relative_path(relative)
        if normalized != relative:
            raise InvalidRunIdError("backup path is not normalized")
        backup_root = self.backup_dir.lstat()
        if not stat.S_ISDIR(backup_root.st_mode) or stat.S_ISLNK(backup_root.st_mode):
            raise InvalidRunIdError("unsafe backup directory")
        path = self.backup_dir.joinpath(*normalized.split("/"))
        current = self.backup_dir
        for part in normalized.split("/")[:-1]:
            current /= part
            parent = current.lstat()
            if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
                raise InvalidRunIdError("unsafe backup path")
        actual_sha256, actual_size = self._hash_regular_artifact(path)
        if actual_sha256 != sha256 or actual_size != size:
            raise InvalidRunIdError("backup digest or size mismatch")

    def _discover_sealed_files(self) -> list[tuple[str, Path]]:
        self._ensure_run_dir_identity()
        _EXTENSION_DIRS = frozenset({"proof", "promotion", "recovery", "staging", "backups", ".agentdiff"})
        discovered: list[tuple[str, Path]] = []
        for directory, directory_names, file_names in os.walk(self.run_dir, followlinks=False):
            base = Path(directory)
            for name in list(directory_names):
                candidate = base / name
                if candidate.is_symlink():
                    directory_relative = candidate.relative_to(self.run_dir)
                    raise InvalidRunIdError(
                        f"sealed artifact directory is a symlink: {directory_relative}"
                    )
            for name in file_names:
                path = base / name
                relative = path.relative_to(self.run_dir).as_posix()
                if relative in {"integrity.json", "integrity/manifest.json"} or relative in _MUTABLE_AFTER_SEAL:
                    continue
                if name.startswith(".") and name.endswith(".tmp"):
                    continue
                parts = relative.split("/")
                if parts[0] in _EXTENSION_DIRS:
                    continue
                discovered.append((relative, path))
        return sorted(discovered)


    @staticmethod
    def _hash_regular_artifact(path: Path) -> tuple[str, int]:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise InvalidRunIdError("artifact must be a single-link regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
            ):
                raise InvalidRunIdError("artifact must be a single-link regular file")
            digest = hashlib.sha256()
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            finished = os.fstat(descriptor)
            if (
                finished.st_dev != opened.st_dev
                or finished.st_ino != opened.st_ino
                or finished.st_size != opened.st_size
                or finished.st_mtime_ns != opened.st_mtime_ns
            ):
                raise RuntimeError("artifact changed during verification")
            return digest.hexdigest(), int(opened.st_size)
        finally:
            os.close(descriptor)

    def write_json(self, name: str, data: Any) -> None:
        target = self._artifact_path(name)
        if (self.run_dir / "integrity.json").exists() and name not in _MUTABLE_AFTER_SEAL:
            raise RuntimeError("sealed run artifacts are immutable")
        payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{name}.", suffix=".tmp", dir=self.run_dir
        )
        temporary = Path(temporary_name)
        try:
            fchmod = getattr(os, "fchmod", None)
            if fchmod is not None:
                fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            if os.name != "nt":
                target.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)

    def read_json(self, name: str) -> Any:
        target = self._artifact_path(name)
        before = target.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise InvalidRunIdError("artifact must be a single-link regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target, flags)
        except OSError as error:
            if target.is_symlink():
                raise InvalidRunIdError("artifact is a symlink") from error
            raise
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
            ):
                raise InvalidRunIdError("artifact must be a single-link regular file")
            if opened.st_size > _MAX_JSON_BYTES:
                raise InvalidRunIdError("artifact exceeds JSON size limit")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read(_MAX_JSON_BYTES + 1)
            finished = os.fstat(descriptor)
            if (
                finished.st_dev != opened.st_dev
                or finished.st_ino != opened.st_ino
                or finished.st_size != opened.st_size
                or finished.st_mtime_ns != opened.st_mtime_ns
            ):
                raise InvalidRunIdError("artifact changed while being read")
            return json.loads(payload.decode("utf-8"))
        finally:
            os.close(descriptor)

    def append_event(self, event_type: str, data: dict[str, Any]) -> None:
        self._ensure_run_dir_identity()
        if not event_type or any(ord(character) < 32 for character in event_type):
            raise ValueError("invalid event type")
        target_name = (
            "recovery-events.jsonl"
            if (self.run_dir / "integrity.json").exists()
            else "events.jsonl"
        )
        target = self.run_dir / target_name
        event = {
            "schema_version": SCHEMA_VERSION,
            "timestamp": _utc_now(),
            "type": event_type,
            "data": redact_data(data),
        }
        payload = (json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n").encode()
        if len(payload) > _MAX_EVENT_BYTES:
            raise ValueError("event exceeds size limit")
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_APPEND
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        before: os.stat_result | None
        try:
            before = target.lstat()
        except FileNotFoundError:
            before = None
        if before is not None and (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1):
            raise InvalidRunIdError("event log must be a single-link regular file")
        try:
            descriptor = os.open(target, flags, 0o600)
        except OSError as error:
            if target.is_symlink():
                raise InvalidRunIdError("event log is a symlink") from error
            raise
        try:
            opened = os.fstat(descriptor)
            current = target.lstat()
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or not stat.S_ISREG(current.st_mode)
                or current.st_dev != opened.st_dev
                or current.st_ino != opened.st_ino
                or (
                    before is not None
                    and (opened.st_dev != before.st_dev or opened.st_ino != before.st_ino)
                )
            ):
                raise InvalidRunIdError("event log must be a single-link regular file")
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if os.name != "nt":
            target.chmod(0o600)
        if target_name == "events.jsonl" and self._trusted_events is not None:
            self._trusted_events.append(payload)

    def restore_trusted_event_log(self) -> None:
        """Replace a pre-seal event log from the transaction's in-memory copy."""

        self._ensure_run_dir_identity()
        if self._trusted_events is None:
            raise RuntimeError("trusted event history is unavailable")
        target = self.run_dir / "events.jsonl"
        descriptor, temporary = tempfile.mkstemp(prefix=".events-", dir=self.run_dir)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(b"".join(self._trusted_events))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, target)
            if os.name != "nt":
                target.chmod(0o600)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _artifact_path(self, name: str) -> Path:
        self._ensure_run_dir_identity()
        if not _ARTIFACT_PATTERN.fullmatch(name):
            raise ValueError("invalid artifact name")
        return self.run_dir / name

    def ensure_artifact_directory(self, relpath: str) -> Path:
        target = self.artifact_path(relpath)
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        return target

    def copy_artifact(
        self,
        relpath: str,
        source: Path,
        *,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
        mode: int | None = None,
    ) -> tuple[str, int]:
        target = self.artifact_path(relpath)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise InvalidRunIdError("source artifact must be a single-link regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(source, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise InvalidRunIdError("source artifact must be a single-link regular file")
            temp_descriptor, temp_path = tempfile.mkstemp(
                prefix=".artifact-copy-", suffix=".tmp", dir=str(target.parent)
            )
            hasher = hashlib.sha256()
            size = 0
            with (
                os.fdopen(descriptor, "rb", closefd=False) as src,
                os.fdopen(temp_descriptor, "wb") as dst,
            ):
                while chunk := src.read(1024 * 1024):
                    dst.write(chunk)
                    hasher.update(chunk)
                    size += len(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            digest = hasher.hexdigest()
            if expected_sha256 is not None and digest != expected_sha256:
                raise InvalidRunIdError(
                    f"artifact digest mismatch: expected {expected_sha256}, got {digest}"
                )
            if expected_size is not None and size != expected_size:
                raise InvalidRunIdError(
                    f"artifact size mismatch: expected {expected_size}, got {size}"
                )
            os.replace(temp_path, str(target))
            if mode is not None and os.name != "nt":
                target.chmod(stat.S_IMODE(mode))
            return digest, size
        finally:
            os.close(descriptor)

    def artifact_digest(self, relpath: str) -> tuple[str, int]:
        target = self.artifact_path(relpath)
        return self._hash_regular_artifact(target)

    def artifact_path(self, relpath: str) -> Path:

        self._ensure_run_dir_identity()
        normalized = normalize_relative_path(relpath)
        if normalized != relpath:
            raise ValueError("unsafe artifact path")
        target = self.run_dir.joinpath(*normalized.split("/"))
        current = self.run_dir
        for part in normalized.split("/")[:-1]:
            current /= part
            if current.exists() or current.is_symlink():
                info = current.lstat()
                if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise ValueError("unsafe artifact directory")
        return target

    def write_json_path(self, relpath: str, data: Any) -> None:
        target = self.artifact_path(relpath)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".artifact-", suffix=".tmp", dir=str(target.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            if os.name != "nt":
                target.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)

    def read_json_path(self, relpath: str) -> Any:
        target = self.artifact_path(relpath)
        if not target.is_file():
            raise FileNotFoundError(f"artifact not found: {relpath}")
        before = target.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise InvalidRunIdError("artifact must be a single-link regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(target, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                raise InvalidRunIdError("artifact must be a single-link regular file")
            if opened.st_size > _MAX_JSON_BYTES:
                raise InvalidRunIdError("artifact exceeds JSON size limit")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                payload = stream.read(_MAX_JSON_BYTES + 1)
            return json.loads(payload.decode("utf-8"))
        finally:
            os.close(descriptor)

    def immutable_manifest_sha256(self) -> str:
        integrity_path = self.run_dir / "integrity.json"
        if not integrity_path.is_file():
            raise RuntimeError("run capsule is not sealed")
        digest, _ = self._hash_regular_artifact(integrity_path)
        return digest

    def seal_extension(self, name: str, files: tuple[str, ...]) -> dict[str, Any]:
        self._ensure_run_dir_identity()
        normalized_name = normalize_relative_path(name)
        ext_dir = self.run_dir / normalized_name
        if not ext_dir.is_dir():
            ext_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        manifest_files: dict[str, dict[str, int | str]] = {}
        for filename in files:
            path = ext_dir / filename
            digest, size = self._hash_regular_artifact(path)
            manifest_files[filename] = {"sha256": digest, "size": size}
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "extension": normalized_name,
            "created_at": _utc_now(),
            "immutable_manifest_sha256": self.immutable_manifest_sha256(),
            "files": dict(sorted(manifest_files.items())),
        }
        self.write_json_path(f"{normalized_name}/integrity.json", manifest)
        return manifest

    def verify_extension(self, name: str) -> IntegrityReport:
        self._ensure_run_dir_identity()
        normalized_name = normalize_relative_path(name)
        integrity_path = self.run_dir / normalized_name / "integrity.json"
        if not integrity_path.exists():
            return IntegrityReport(present=False, ok=False, files_checked=0)
        issues: list[IntegrityIssue] = []
        try:
            manifest = self.read_json_path(f"{normalized_name}/integrity.json")
        except Exception as error:
            return IntegrityReport(
                present=True,
                ok=False,
                files_checked=0,
                issues=(IntegrityIssue(f"{name}/integrity.json", str(error)),),
            )
        if not isinstance(manifest, dict) or manifest.get("extension") != normalized_name:
            return IntegrityReport(
                present=True,
                ok=False,
                files_checked=0,
                issues=(IntegrityIssue(f"{name}/integrity.json", "invalid extension manifest"),),
            )
        if manifest.get("immutable_manifest_sha256") != self.immutable_manifest_sha256():
            issues.append(
                IntegrityIssue(
                    f"{name}/integrity.json",
                    "extension not bound to immutable run manifest",
                )
            )
        raw_files = manifest.get("files", {})
        checked = 0
        if not isinstance(raw_files, dict):
            return IntegrityReport(
                present=True,
                ok=False,
                files_checked=0,
                issues=(IntegrityIssue(f"{name}/integrity.json", "files must be a mapping"),),
            )
        # Verify no unsealed files exist in extension directory
        actual_ext_files: set[str] = set()
        for directory, _, file_names in os.walk(self.run_dir / normalized_name):
            for fname in file_names:
                p = Path(directory) / fname
                rel = p.relative_to(self.run_dir / normalized_name).as_posix()
                if rel != "integrity.json":
                    actual_ext_files.add(rel)
        for unsealed in sorted(actual_ext_files - set(raw_files.keys())):
            issues.append(IntegrityIssue(f"{name}/{unsealed}", "unsealed extension artifact"))

        for filename, expected in raw_files.items():
            path = self.run_dir / normalized_name / filename
            if not path.is_file():
                issues.append(IntegrityIssue(f"{name}/{filename}", "missing extension artifact"))
                continue
            try:
                digest, size = self._hash_regular_artifact(path)
                checked += 1
                if not isinstance(expected, dict) or expected.get("sha256") != digest or expected.get("size") != size:
                    issues.append(IntegrityIssue(f"{name}/{filename}", "digest or size mismatch"))
            except Exception as error:
                issues.append(IntegrityIssue(f"{name}/{filename}", str(error)))
        return IntegrityReport(present=True, ok=not issues, files_checked=checked, issues=tuple(issues))

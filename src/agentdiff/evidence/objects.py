"""Content-addressed immutable object storage.

Objects live under ``<root>/.agentdiff/objects/<sha256[:2]>/<sha256>`` and are
written once: content is streamed while its SHA-256 is computed, written to a
temp file, fsynced, digest-validated, and atomically renamed into place. An
existing object with the same digest is never rewritten (immutability).

Layout notes
------------

Run capsules remain self-contained file trees today (spec v2). This object
store is the foundation for the incremental migration to content-addressed
artifact references (spec v3 planning) and for future export/import
hydration. Nothing in the sealed-capsule format changes as a result of this
module.

Objects are tamper-evident, not authenticated: anyone able to write the
object store can add or replace objects, but digest-addressed reads fail
closed if the content does not match the requested digest.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable

_CHUNK_SIZE = 1024 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ObjectStoreError(RuntimeError):
    """Raised for invalid digests, corrupted objects, or storage failures."""


@dataclass(frozen=True, slots=True)
class ObjectRef:
    sha256: str
    size: int

    def to_dict(self) -> dict[str, object]:
        return {"sha256": self.sha256, "size": self.size}


def validate_object_digest(value: str) -> str:
    """Return the lowercase hex digest or raise."""
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise ObjectStoreError(f"invalid object digest: {value!r}")
    return value


class ObjectStore:
    """Content-addressed immutable object storage below one AgentDiff root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.objects_dir = self.root / ".agentdiff" / "objects"
        self.objects_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._assert_real_directory(self.objects_dir)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def put(self, source: str | Path | BinaryIO | bytes) -> ObjectRef:
        """Store one stream of bytes and return its content address.

        The object is written immutably: if an object with the same digest
        already exists, its stored content is re-verified and nothing is
        rewritten.
        """
        hasher = hashlib.sha256()
        size = 0
        temporary: Path | None = None
        close_source = False
        try:
            if isinstance(source, (bytes, bytearray)):
                stream: BinaryIO = io.BytesIO(bytes(source))
            elif hasattr(source, "read"):
                stream = source  # type: ignore[assignment]
            else:
                path = Path(source)  # type: ignore[arg-type]
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise ObjectStoreError("object source must be a regular file")
                flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(path, flags)
                stream = os.fdopen(descriptor, "rb", closefd=False)
                close_source = True
            temp_fd, temp_name = tempfile.mkstemp(
                prefix="object-", suffix=".tmp", dir=str(self.objects_dir)
            )
            temporary = Path(temp_name)
            try:
                with os.fdopen(temp_fd, "wb") as output:
                    while chunk := stream.read(_CHUNK_SIZE):
                        hasher.update(chunk)
                        size += len(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                if close_source:
                    stream.close()
        except OSError as error:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise ObjectStoreError(f"object write failed: {error}") from error

        digest = hasher.hexdigest()
        target = self.path_for(digest)
        if target.exists():
            self._verify_existing(digest, size)
            temporary.unlink(missing_ok=True)
            return ObjectRef(sha256=digest, size=size)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.replace(temporary, target)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ObjectStoreError(f"object commit failed: {error}") from error
        return ObjectRef(sha256=digest, size=size)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def path_for(self, digest: str) -> Path:
        """Return the on-disk path for a digest without touching the filesystem."""
        validated = validate_object_digest(digest)
        return self.objects_dir / validated[:2] / validated

    def has(self, digest: str) -> bool:
        try:
            path = self.path_for(digest)
        except ObjectStoreError:
            return False
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        return stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)

    def open(self, digest: str) -> BinaryIO:
        """Open an object for reading after verifying its identity."""
        path = self.path_for(digest)
        try:
            info = path.lstat()
        except FileNotFoundError as error:
            raise ObjectStoreError(f"object not found: {digest}") from error
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
            raise ObjectStoreError(f"object is not a single-link regular file: {digest}")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_dev != info.st_dev
            or opened.st_ino != info.st_ino
        ):
            os.close(descriptor)
            raise ObjectStoreError(f"object identity changed while opening: {digest}")
        return os.fdopen(descriptor, "rb")

    def read_bytes(self, digest: str) -> bytes:
        """Read an object and fail closed if its content does not match the digest."""
        validated = validate_object_digest(digest)
        with self.open(digest) as stream:
            hasher = hashlib.sha256()
            chunks: list[bytes] = []
            while chunk := stream.read(_CHUNK_SIZE):
                hasher.update(chunk)
                chunks.append(chunk)
        if hasher.hexdigest() != validated:
            raise ObjectStoreError(f"object content does not match digest: {digest}")
        return b"".join(chunks)

    def verify(self, digest: str, expected_size: int | None = None) -> int:
        """Recompute the digest of one stored object; raises on mismatch."""
        validated = validate_object_digest(digest)
        with self.open(digest) as stream:
            hasher = hashlib.sha256()
            size = 0
            while chunk := stream.read(_CHUNK_SIZE):
                hasher.update(chunk)
                size += len(chunk)
        if hasher.hexdigest() != validated:
            raise ObjectStoreError(f"object content does not match digest: {digest}")
        if expected_size is not None and size != expected_size:
            raise ObjectStoreError(f"object size mismatch: {digest}")
        return size

    def iter_all(self) -> Iterable[ObjectRef]:
        """Yield every stored object reference in deterministic order."""
        references: list[ObjectRef] = []
        for prefix_dir in sorted(self.objects_dir.iterdir()):
            if not prefix_dir.is_dir() or prefix_dir.is_symlink():
                continue
            for candidate in sorted(prefix_dir.iterdir()):
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                name = candidate.name
                if not _SHA256_PATTERN.fullmatch(name):
                    continue
                try:
                    size = self.verify(name)
                except ObjectStoreError:
                    continue
                references.append(ObjectRef(sha256=name, size=size))
        return references

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _verify_existing(self, digest: str, expected_size: int) -> None:
        actual = self.verify(digest, expected_size=expected_size)
        if actual != expected_size:
            raise ObjectStoreError(f"existing object size mismatch: {digest}")

    @staticmethod
    def _assert_real_directory(path: Path) -> None:
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ObjectStoreError(f"object store path is not a real directory: {path}")

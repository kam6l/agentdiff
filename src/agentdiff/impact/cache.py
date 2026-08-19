"""Deterministic, content-addressed proof cache.

A proof result is cached only when every input that can influence the verdict
is identical:

- base digest (sealed pre-run source snapshot)
- patch digest (exact mutation set + payloads)
- dependency lock digest (lockfile digests from the trust lock)
- runtime image digest (image name + repository digest when available)
- proof plan digest (exact argv phases)
- target (proof level: static / targeted / full)

A cache hit for an identical input set is deterministic and safe to reuse; any
input change is a miss. Cache entries carry their own SHA-256 integrity
manifest and are never trusted across different keys.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentdiff.pathing import normalize_relative_path


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class ProofCacheKey:
    """All inputs that deterministically determine a proof outcome."""

    base_digest: str
    patch_digest: str
    lock_digest: str
    image_digest: str
    plan_digest: str
    target: str = "full"

    def digest(self) -> str:
        return _canonical_digest(asdict(self))

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProofCacheKey":
        return cls(
            base_digest=str(value["base_digest"]),
            patch_digest=str(value["patch_digest"]),
            lock_digest=str(value["lock_digest"]),
            image_digest=str(value["image_digest"]),
            plan_digest=str(value["plan_digest"]),
            target=str(value.get("target", "full")),
        )


@dataclass(frozen=True, slots=True)
class ProofCachePhase:
    """One cached verification phase outcome."""

    phase: str
    returncode: int | None
    output_sha256: str | None
    duration_seconds: float
    tests_passed: int | None = None
    tests_total: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProofCacheEntry:
    """One integrity-sealed cached proof outcome."""

    key: ProofCacheKey
    verdict: str  # "PROVEN" | "NOT_PROVEN"
    promotion: str
    phases: tuple[ProofCachePhase, ...]
    cached_from_run: str
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "key": self.key.to_dict(),
            "verdict": self.verdict,
            "promotion": self.promotion,
            "phases": [phase.to_dict() for phase in self.phases],
            "cached_from_run": self.cached_from_run,
            "created_at": self.created_at,
        }


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class ProofCache:
    """Content-addressed proof cache under ``<root>/.agentdiff/cache/proof``."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        max_entries: int = 32,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        self.max_entries = max_entries
        self.directory = self.root / ".agentdiff" / "cache" / "proof"

    def lookup(self, key: ProofCacheKey) -> ProofCacheEntry | None:
        entry_dir = self._entry_dir(key.digest())
        entry_path = entry_dir / "entry.json"
        integrity_path = entry_dir / "integrity.json"
        if not entry_path.is_file() or not integrity_path.is_file():
            return None
        integrity = _read_json(integrity_path)
        if integrity is None or integrity.get("entry_sha256") != self._hash_file(entry_path):
            return None
        raw = _read_json(entry_path)
        if raw is None:
            return None
        try:
            stored_key = ProofCacheKey.from_dict(raw["key"])
        except (KeyError, TypeError, ValueError):
            return None
        if stored_key.digest() != key.digest():
            return None
        entry = self._entry_from_dict(raw)
        if entry is None:
            return None
        with contextlib.suppress(OSError):
            entry_path.touch()  # LRU recency
        return entry

    def store(self, key: ProofCacheKey, entry: ProofCacheEntry) -> None:
        entry_dir = self._entry_dir(key.digest())
        entry_path = entry_dir / "entry.json"
        entry_dict = entry.to_dict()
        _atomic_write_json(entry_path, entry_dict)
        digest = self._hash_file(entry_path)
        _atomic_write_json(
            entry_dir / "integrity.json",
            {
                "schema_version": 1,
                "entry_sha256": digest,
                "created_at": _utc_now_iso(),
            },
        )
        self._prune()

    def stats(self) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        if self.directory.is_dir():
            for entry_dir in sorted(self.directory.iterdir()):
                if not entry_dir.is_dir():
                    continue
                entry_path = entry_dir / "entry.json"
                raw = _read_json(entry_path)
                if raw is None:
                    continue
                entries.append(
                    {
                        "key_digest": entry_dir.name,
                        "verdict": raw.get("verdict"),
                        "target": (raw.get("key") or {}).get("target"),
                        "cached_from_run": raw.get("cached_from_run"),
                        "created_at": raw.get("created_at"),
                    }
                )
        return {"schema_version": 1, "entries": entries, "count": len(entries)}

    def clear(self) -> int:
        count = 0
        if self.directory.is_dir():
            for entry_dir in list(self.directory.iterdir()):
                if entry_dir.is_dir():
                    shutil.rmtree(entry_dir)
                    count += 1
        return count

    def _entry_dir(self, key_digest: str) -> Path:
        normalized = normalize_relative_path(key_digest)
        if normalized != key_digest or len(key_digest) != 64:
            raise ValueError("proof cache key digest must be a normalized sha256 hex")
        return self.directory / key_digest

    def _prune(self) -> None:
        if not self.directory.is_dir():
            return
        candidates: list[tuple[float, Path]] = []
        for entry_dir in self.directory.iterdir():
            if not entry_dir.is_dir():
                continue
            try:
                mtime = entry_dir.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, entry_dir))
        candidates.sort()
        for _, entry_dir in candidates[: max(0, len(candidates) - self.max_entries)]:
            shutil.rmtree(entry_dir, ignore_errors=True)

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _entry_from_dict(raw: dict[str, Any]) -> ProofCacheEntry | None:
        try:
            key = ProofCacheKey.from_dict(raw["key"])
            phases = tuple(
                ProofCachePhase(
                    phase=str(phase.get("phase", "")),
                    returncode=(
                        int(phase["returncode"]) if phase.get("returncode") is not None else None
                    ),
                    output_sha256=(
                        str(phase["output_sha256"])
                        if phase.get("output_sha256") is not None
                        else None
                    ),
                    duration_seconds=float(phase.get("duration_seconds", 0.0)),
                    tests_passed=(
                        int(phase["tests_passed"])
                        if phase.get("tests_passed") is not None
                        else None
                    ),
                    tests_total=(
                        int(phase["tests_total"]) if phase.get("tests_total") is not None else None
                    ),
                )
                for phase in raw.get("phases", [])
                if isinstance(phase, dict)
            )
            return ProofCacheEntry(
                key=key,
                verdict=str(raw["verdict"]),
                promotion=str(raw.get("promotion", "BLOCKED")),
                phases=phases,
                cached_from_run=str(raw.get("cached_from_run", "")),
                created_at=str(raw.get("created_at", "")),
            )
        except (KeyError, TypeError, ValueError):
            return None

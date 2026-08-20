"""Content-addressed object storage tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
import hashlib
import os

import pytest

from agentdiff.evidence import ObjectRef, ObjectStore, ObjectStoreError


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_object_put_and_read_back(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    payload = b"hello object store"
    ref = store.put(payload)
    assert isinstance(ref, ObjectRef)
    assert ref.sha256 == sha256(payload)
    assert ref.size == len(payload)
    assert store.read_bytes(ref.sha256) == payload
    assert store.verify(ref.sha256) == len(payload)


def test_object_store_deduplicates_identical_content(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    payload = b"shared content"
    first = store.put(payload)
    second = store.put(payload)
    assert first.sha256 == second.sha256
    assert first.sha256 == sha256(payload)
    # One object on disk.
    count = sum(1 for _ in store.iter_all())
    assert count == 1


def test_object_store_keeps_objects_immutable(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    payload = b"immutable"
    ref = store.put(payload)
    path = store.path_for(ref.sha256)
    before = path.stat().st_mtime_ns
    # Re-putting the same content must not rewrite the object.
    store.put(payload)
    assert path.stat().st_mtime_ns == before


def test_object_store_rejects_invalid_digest(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    with pytest.raises(ObjectStoreError, match="invalid object digest"):
        store.path_for("../../etc/passwd")
    with pytest.raises(ObjectStoreError, match="invalid object digest"):
        store.path_for("abc")
    with pytest.raises(ObjectStoreError, match="invalid object digest"):
        store.path_for("A" * 64)
    assert store.has("../../etc/passwd") is False
    with pytest.raises(ObjectStoreError):
        store.open("deadbeef")


def test_object_store_path_stays_under_objects_dir(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    ref = store.put(b"x")
    resolved = store.path_for(ref.sha256).resolve()
    assert resolved.parent.parent == store.objects_dir.resolve()
    assert str(resolved).startswith(str(store.objects_dir.resolve()))


def test_object_store_corruption_detected(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    ref = store.put(b"original content")
    path = store.path_for(ref.sha256)
    path.write_bytes(b"tampered content")
    with pytest.raises(ObjectStoreError, match="does not match digest"):
        store.verify(ref.sha256)
    with pytest.raises(ObjectStoreError):
        store.read_bytes(ref.sha256)


def test_object_store_rejects_symlinked_object(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    ref = store.put(b"data")
    target = store.path_for(ref.sha256)
    target.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside data")
    os.symlink(outside, target)
    assert store.has(ref.sha256) is False
    with pytest.raises(ObjectStoreError, match="single-link regular file"):
        store.open(ref.sha256)


def test_object_store_put_from_path(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    source = tmp_path / "source.bin"
    source.write_bytes(b"from path")
    ref = store.put(source)
    assert store.read_bytes(ref.sha256) == b"from path"


def test_object_store_iter_all_deterministic(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    payloads = [b"one", b"two", b"three"]
    refs = [store.put(payload) for payload in payloads]
    found = list(store.iter_all())
    assert {item.sha256 for item in found} == {ref.sha256 for ref in refs}
    # Deterministic order.
    assert [item.sha256 for item in found] == sorted(item.sha256 for item in found)

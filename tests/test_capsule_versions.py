"""Capsule spec v1/v2 verification separation and root-digest terminology."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentdiff.evidence import CapsuleReader
from agentdiff.transaction import RunStore


def build_capsule(tmp_path: Path) -> RunStore:
    """Create a sealed store with the principal artifacts written."""
    store = RunStore.create(tmp_path, task="t", command=["agent"])
    for name in ("metadata.json", "policy.json", "after.json", "runtime.json"):
        store.write_json(name, {"schema_version": 1, "x": 1})
    store.write_json("before.json", {"schema_version": 1, "files": {}})
    store.write_json("result.json", {"schema_version": 1, "status": "passed"})
    store.append_event("created", {})
    return store


def v1_manifest(store: RunStore) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    for name in (
        "metadata.json",
        "policy.json",
        "before.json",
        "after.json",
        "runtime.json",
        "result.json",
        "events.jsonl",
    ):
        digest, size = store.artifact_digest(name)
        files[name] = {"sha256": digest, "size": size}
    return {"schema_version": 1, "algorithm": "sha256", "files": files}


def test_v1_capsule_verifies_under_original_guarantees(tmp_path: Path) -> None:
    store = build_capsule(tmp_path)
    (store.run_dir / "integrity.json").write_text(
        json.dumps(v1_manifest(store)), encoding="utf-8"
    )

    report = store.verify_integrity()
    assert report.present is True
    assert report.ok is True
    assert report.version == 1
    assert report.files_checked == 7

    reader = CapsuleReader(store.run_dir)
    assert reader.version == 1
    assert reader.read_manifest()["schema_version"] == 1


def test_v2_capsule_verifies_with_structured_manifest(tmp_path: Path) -> None:
    store = build_capsule(tmp_path)
    store.finalize_integrity()

    report = store.verify_integrity()
    assert report.ok is True
    assert report.version == 2

    reader = CapsuleReader(store.run_dir)
    assert reader.version == 2
    assert (store.run_dir / "integrity" / "manifest.json").is_file()


def test_v1_capsule_tampering_is_detected(tmp_path: Path) -> None:
    store = build_capsule(tmp_path)
    (store.run_dir / "integrity.json").write_text(
        json.dumps(v1_manifest(store)), encoding="utf-8"
    )
    (store.run_dir / "result.json").write_text('{"status": "tampered"}\n', encoding="utf-8")

    report = store.verify_integrity()
    assert report.ok is False
    assert any(issue.path == "result.json" for issue in report.issues)


def test_schema2_mirror_without_integrity_dir_is_incomplete(tmp_path: Path) -> None:
    """Deleting integrity/manifest.json must not downgrade a v2 capsule to v1."""
    store = build_capsule(tmp_path)
    store.finalize_integrity()
    (store.run_dir / "integrity" / "manifest.json").unlink()

    report = store.verify_integrity()
    assert report.ok is False
    assert any(issue.path == "integrity/manifest.json" for issue in report.issues)
    assert any("incomplete spec-v2 seal" in issue.reason for issue in report.issues)


def test_root_digest_is_flat_aggregate_not_merkle(tmp_path: Path) -> None:
    store = build_capsule(tmp_path)
    store.finalize_integrity()
    reader = CapsuleReader(store.run_dir)

    digest = reader.compute_root_digest()
    assert isinstance(digest, str) and len(digest) == 64
    # The deprecated alias must agree.
    assert reader.compute_merkle_root() == digest
    # Deterministic across reads.
    assert reader.compute_root_digest() == digest


def test_root_digest_changes_when_manifest_changes(tmp_path: Path) -> None:
    store = build_capsule(tmp_path)
    store.finalize_integrity()
    reader = CapsuleReader(store.run_dir)
    before = reader.compute_root_digest()

    manifest = reader.read_manifest()
    manifest["files"]["result.json"] = {"sha256": "0" * 64, "size": 1}
    (store.run_dir / "integrity" / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    assert reader.compute_root_digest() != before

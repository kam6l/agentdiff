"""Comprehensive unit tests for hardened Trust Pipeline v0.2.0 components."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentdiff.evidence import BlobReference, CapsuleReader, PatchBundle, PatchEntry
from agentdiff.policy import Policy, PolicyAction, PolicyDecision, ProofPolicy, load_policy
from agentdiff.proof import ProofEngine, ProofVerdict
from agentdiff.proof.plan import TrustedVerificationPlan, select_trusted_verification_plan
from agentdiff.promotion import (
    JournalEntry,
    JournalState,
    PromotionEngine,
    PromotionJournal,
    PromotionLockError,
    PromotionRecovery,
    WorkspaceLease,
)
from agentdiff.runtime import MaterializationStrategy, WorkspaceMaterializer
from agentdiff.safety import HybridSafetyWatcher, SafetyController
from agentdiff.state import FilesystemScanner


def test_proof_plan_detects_and_blocks_build_config_tampering(tmp_path: Path) -> None:
    """If a patch alters build/test config files without an explicit policy plan, proof fails."""
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}', encoding="utf-8")
    (tmp_path / "index.js").write_text("console.log('hello');", encoding="utf-8")

    # Tampered patch modifying package.json to fake tests
    tampered_entry = PatchEntry(
        path="package.json",
        change_type="modified",
        decision="allow",
        base_sha256="abc",
        result_sha256="def",
        base_mode=0o644,
        result_mode=0o644,
        size=10,
        materialized=True,
        reason="tampered build configuration",
    )

    policy = Policy(version=2, proof=ProofPolicy())
    plan = select_trusted_verification_plan(
        base_root=tmp_path,
        policy=policy,
        patch_entries=(tampered_entry,),
    )

    assert plan.trusted is False
    assert "package.json" in plan.tampered_files
    assert "patch modified test/build infrastructure" in plan.reason


def test_proof_plan_accepts_explicit_policy_override(tmp_path: Path) -> None:
    """Explicit commands pinned in policy are trusted even if patch modifies package.json."""
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}', encoding="utf-8")

    tampered_entry = PatchEntry(
        path="package.json",
        change_type="modified",
        decision="allow",
        base_sha256="abc",
        result_sha256="def",
        base_mode=0o644,
        result_mode=0o644,
        size=10,
        materialized=True,
        reason="authorized build update",
    )

    policy = Policy(
        version=2,
        proof=ProofPolicy(tests=["npm run test:isolated"]),
    )
    plan = select_trusted_verification_plan(
        base_root=tmp_path,
        policy=policy,
        patch_entries=(tampered_entry,),
    )

    assert plan.trusted is True
    assert plan.source == "policy"
    assert list(plan.tests) == ["npm run test:isolated"]


def test_promotion_write_ahead_journal_and_recovery(tmp_path: Path) -> None:
    """Test WAL journal persistence and crash recovery restores files."""
    host_file = tmp_path / "target.txt"
    host_file.write_text("initial host state", encoding="utf-8")

    backup_dir = tmp_path / ".agentdiff" / "backups" / "run-123"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / "target.txt"
    backup_file.write_text("initial host state", encoding="utf-8")

    created_file = tmp_path / "created.txt"
    created_file.write_text("partially created", encoding="utf-8")

    # Simulate an interrupted journal in APPLYING state
    journal = PromotionJournal(
        root=tmp_path,
        run_id="run-123",
        patch_digest="dummy-digest",
        state=JournalState.APPLYING,
        entries=[
            JournalEntry(
                path="target.txt",
                change_type="modified",
                base_sha256="base",
                result_sha256="target",
                base_mode=0o644,
                result_mode=0o644,
                backup_relpath=".agentdiff/backups/run-123/target.txt",
                applied=True,
            ),
            JournalEntry(
                path="created.txt",
                change_type="created",
                base_sha256=None,
                result_sha256="created",
                base_mode=None,
                result_mode=0o644,
                applied=True,
            ),
        ],
    )
    journal.persist()

    # Corrupt target.txt as if mutation was mid-flight
    host_file.write_text("corrupted mid-flight mutation", encoding="utf-8")

    # Recovery should restore target.txt from backup and delete created.txt
    recovery = PromotionRecovery(tmp_path)
    report = recovery.check_and_recover()

    assert report is not None
    assert report.status == "RECOVERED"
    assert "target.txt" in report.restored
    assert "created.txt" in report.cleaned
    assert host_file.read_text(encoding="utf-8") == "initial host state"
    assert not created_file.exists()


def test_workspace_lease_concurrency(tmp_path: Path) -> None:
    """Test advisory lock lease prevents overlapping promotion locks."""
    lease1 = WorkspaceLease(tmp_path, run_id="run-1")
    with lease1.hold():
        lease2 = WorkspaceLease(tmp_path, run_id="run-2")
        with pytest.raises(PromotionLockError, match="another process is promoting"):
            with lease2.hold():
                pass


def test_capsule_reader_and_merkle_root(tmp_path: Path) -> None:
    """Test CapsuleReader inspects v2 capsule and computes Merkle root."""
    run_dir = tmp_path / ".agentdiff" / "runs" / "test-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    integrity_dir = run_dir / "integrity"
    integrity_dir.mkdir(parents=True, exist_ok=True)

    manifest_data = {
        "schema_version": 2,
        "algorithm": "sha256",
        "files": {
            "metadata.json": {"sha256": "1111", "size": 10},
            "result.json": {"sha256": "2222", "size": 20},
        },
    }
    (integrity_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    reader = CapsuleReader(run_dir)
    assert reader.version == 2
    merkle_root = reader.compute_merkle_root()
    assert isinstance(merkle_root, str)
    assert len(merkle_root) == 64


def test_workspace_materializer_copy(tmp_path: Path) -> None:
    """Test WorkspaceMaterializer correctly copies directory structure."""
    src = tmp_path / "source"
    dst = tmp_path / "target"
    src.mkdir()
    (src / "file1.txt").write_text("content1", encoding="utf-8")
    sub = src / "subdir"
    sub.mkdir()
    (sub / "file2.txt").write_text("content2", encoding="utf-8")

    materializer = WorkspaceMaterializer(strategy=MaterializationStrategy.COPY)
    report = materializer.materialize(src, dst)

    assert report.files_materialized == 2
    assert report.bytes_materialized > 0
    assert (dst / "file1.txt").read_text(encoding="utf-8") == "content1"
    assert (dst / "subdir" / "file2.txt").read_text(encoding="utf-8") == "content2"


def test_hybrid_safety_watcher(tmp_path: Path) -> None:
    """Test HybridSafetyWatcher tracks hints and evaluates safety."""
    policy = load_policy({"version": 2, "limits": {"duration_seconds": 100}})
    scanner = FilesystemScanner(tmp_path)
    before = scanner.capture()

    watcher = HybridSafetyWatcher(
        root=tmp_path,
        policy=policy,
        before=before,
    )
    watcher.notify_event("file.txt")
    assert watcher.stats.hints_received == 1

    terminated = watcher.poll(duration_seconds=1.0, processes_spawned=1)
    assert terminated is False
    assert watcher.stats.full_scans_performed == 1

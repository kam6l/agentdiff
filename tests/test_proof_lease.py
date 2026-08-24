"""Focused tests for deterministic, fail-closed proof leases."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from agentdiff.proof import (
    ProofLease,
    ProofLeaseEvaluator,
    ProofLeaseInvalidation,
    ProofLeaseObservation,
    ProofLeaseStatus,
)

_BASE_SHA = "a" * 40
_MOVED_SHA = "b" * 40


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _lease(*, closure_complete: bool = True) -> ProofLease:
    return ProofLease(
        base_sha=_BASE_SHA,
        patch_digest=_digest("patch"),
        proof_plan_digest=_digest("proof-plan"),
        lockfile_digest=_digest("lockfiles"),
        runtime_digest=_digest("runtime"),
        dependency_closure=(
            "src/auth",
            "tests/auth/test_token.py",
            "pyproject.toml",
        ),
        closure_complete=closure_complete,
    )


def _observation(lease: ProofLease | None = None) -> ProofLeaseObservation:
    bound = lease or _lease()
    return ProofLeaseObservation(
        base_sha=bound.base_sha,
        patch_digest=bound.patch_digest,
        proof_plan_digest=bound.proof_plan_digest,
        lockfile_digest=bound.lockfile_digest,
        runtime_digest=bound.runtime_digest,
    )


def test_lease_is_immutable_canonical_and_round_trips() -> None:
    lease = _lease()
    reordered = ProofLease(
        base_sha=lease.base_sha,
        patch_digest=lease.patch_digest,
        proof_plan_digest=lease.proof_plan_digest,
        lockfile_digest=lease.lockfile_digest,
        runtime_digest=lease.runtime_digest,
        dependency_closure=(
            "tests/auth/test_token.py",
            "src\\auth",
            "pyproject.toml",
            "src/auth",
        ),
        closure_complete=True,
        invalidation_rules=tuple(reversed(tuple(ProofLeaseInvalidation))),
    )

    assert reordered == lease
    assert reordered.id == lease.id
    assert reordered.digest == lease.digest
    assert ProofLease.from_dict(json.loads(json.dumps(lease.to_dict()))) == lease
    assert tuple(lease.invalidation_rules) == tuple(ProofLeaseInvalidation)
    with pytest.raises(AttributeError):
        lease.base_sha = _MOVED_SHA  # type: ignore[misc]


def test_exact_unchanged_inputs_remain_valid_without_reuse_attestations() -> None:
    lease = _lease()
    result = ProofLeaseEvaluator().evaluate(lease, _observation(lease))

    assert result.status is ProofLeaseStatus.VALID
    assert result.valid is True
    assert result.invalidations == ()
    assert result.changed_paths == ()
    assert result.lease_id == lease.id


def test_complete_disjoint_head_movement_preserves_validity() -> None:
    lease = _lease()
    observation = replace(
        _observation(lease),
        base_sha=_MOVED_SHA,
        changed_paths=("docs/runbook.md", "README.md", "src/authentication/client.py"),
        changed_paths_complete=True,
        base_lineage_verified=True,
    )

    result = ProofLeaseEvaluator().evaluate(lease, observation)

    assert result.status is ProofLeaseStatus.VALID
    assert result.intersecting_paths == ()
    assert result.disjoint_paths == (
        "README.md",
        "docs/runbook.md",
        "src/authentication/client.py",
    )
    assert result.current_base_sha == _MOVED_SHA


def test_verified_empty_commit_movement_preserves_validity() -> None:
    lease = _lease()
    observation = replace(
        _observation(lease),
        base_sha=_MOVED_SHA,
        changed_paths_complete=True,
        base_lineage_verified=True,
    )

    assert ProofLeaseEvaluator().evaluate(lease, observation).valid is True


@pytest.mark.parametrize(
    "changed_path",
    (
        "src/auth/token.py",
        "pyproject.toml",
        "tests",
    ),
)
def test_dependency_closure_overlap_invalidates_segment_aware(changed_path: str) -> None:
    lease = _lease()
    observation = replace(
        _observation(lease),
        base_sha=_MOVED_SHA,
        changed_paths=(changed_path,),
        changed_paths_complete=True,
        base_lineage_verified=True,
    )

    result = ProofLeaseEvaluator().evaluate(lease, observation)

    assert result.status is ProofLeaseStatus.INVALIDATED
    assert result.invalidations == (ProofLeaseInvalidation.DEPENDENCY_CLOSURE_TOUCHED,)
    assert result.intersecting_paths == (changed_path,)
    assert result.disjoint_paths == ()


def test_incomplete_dependency_closure_always_invalidates() -> None:
    lease = _lease(closure_complete=False)
    result = ProofLeaseEvaluator().evaluate(lease, _observation(lease))

    assert result.invalidations == (ProofLeaseInvalidation.DEPENDENCY_CLOSURE_INCOMPLETE,)
    assert result.valid is False
    assert result.disjoint_paths == ()


def test_head_movement_requires_complete_paths_and_verified_lineage() -> None:
    lease = _lease()
    observation = replace(
        _observation(lease),
        base_sha=_MOVED_SHA,
        changed_paths=("README.md",),
    )

    result = ProofLeaseEvaluator().evaluate(lease, observation)

    assert result.invalidations == (
        ProofLeaseInvalidation.BASE_LINEAGE_UNVERIFIED,
        ProofLeaseInvalidation.CHANGED_PATHS_INCOMPLETE,
    )
    assert result.disjoint_paths == ()


def test_dirty_workspace_requires_a_complete_changed_path_set() -> None:
    lease = _lease()
    observation = replace(_observation(lease), changed_paths=("README.md",))

    result = ProofLeaseEvaluator().evaluate(lease, observation)

    assert result.invalidations == (ProofLeaseInvalidation.CHANGED_PATHS_INCOMPLETE,)
    assert result.valid is False


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("patch_digest", ProofLeaseInvalidation.PATCH_DIGEST_CHANGED),
        ("proof_plan_digest", ProofLeaseInvalidation.PROOF_PLAN_DIGEST_CHANGED),
        ("lockfile_digest", ProofLeaseInvalidation.LOCKFILE_DIGEST_CHANGED),
        ("runtime_digest", ProofLeaseInvalidation.RUNTIME_DIGEST_CHANGED),
    ),
)
def test_every_exact_binding_change_invalidates(field: str, reason: ProofLeaseInvalidation) -> None:
    lease = _lease()
    observation = replace(_observation(lease), **{field: _digest(f"changed-{field}")})

    result = ProofLeaseEvaluator().evaluate(lease, observation)

    assert result.status is ProofLeaseStatus.INVALIDATED
    assert result.invalidations == (reason,)


def test_multiple_invalidations_have_a_stable_auditable_order() -> None:
    lease = _lease()
    observation = ProofLeaseObservation(
        base_sha=_MOVED_SHA,
        patch_digest=_digest("changed-patch"),
        proof_plan_digest=_digest("changed-plan"),
        lockfile_digest=_digest("changed-lock"),
        runtime_digest=_digest("changed-runtime"),
        changed_paths=("src/auth/token.py",),
    )

    result = ProofLeaseEvaluator().evaluate(lease, observation)

    assert result.invalidations == (
        ProofLeaseInvalidation.PATCH_DIGEST_CHANGED,
        ProofLeaseInvalidation.PROOF_PLAN_DIGEST_CHANGED,
        ProofLeaseInvalidation.LOCKFILE_DIGEST_CHANGED,
        ProofLeaseInvalidation.RUNTIME_DIGEST_CHANGED,
        ProofLeaseInvalidation.BASE_LINEAGE_UNVERIFIED,
        ProofLeaseInvalidation.CHANGED_PATHS_INCOMPLETE,
        ProofLeaseInvalidation.DEPENDENCY_CLOSURE_TOUCHED,
    )
    assert result.to_dict()["status"] == "INVALIDATED"


def test_observation_round_trip_is_strict_and_canonical() -> None:
    observation = replace(
        _observation(),
        changed_paths=("docs\\guide.md", "README.md", "README.md"),
        changed_paths_complete=True,
    )

    restored = ProofLeaseObservation.from_dict(json.loads(json.dumps(observation.to_dict())))

    assert restored == observation
    assert restored.changed_paths == ("README.md", "docs/guide.md")
    unknown = observation.to_dict()
    unknown["certificate"] = "must-not-be-restamped"
    with pytest.raises(ValueError, match="unknown fields"):
        ProofLeaseObservation.from_dict(unknown)


def test_malformed_or_tampered_lease_data_is_rejected() -> None:
    lease = _lease()
    with pytest.raises(ValueError, match="Git SHA"):
        replace(lease, base_sha="not-a-sha")
    with pytest.raises(ValueError, match="SHA-256"):
        replace(lease, patch_digest="A" * 64)
    with pytest.raises(ValueError, match="safe relative path"):
        replace(lease, dependency_closure=("../escape.py",))
    with pytest.raises(ValueError, match="at least one path"):
        replace(lease, dependency_closure=())
    with pytest.raises(ValueError, match="boolean"):
        replace(lease, closure_complete=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="object"):
        ProofLease.from_dict([])

    missing_rule = lease.to_dict()
    missing_rule["invalidation_rules"] = missing_rule["invalidation_rules"][:-1]
    with pytest.raises(ValueError, match="complete fail-closed policy"):
        ProofLease.from_dict(missing_rule)

    tampered = lease.to_dict()
    tampered["dependency_closure"] = ["src/payments"]
    with pytest.raises(ValueError, match="id"):
        ProofLease.from_dict(tampered)


def test_evaluator_requires_typed_validated_inputs() -> None:
    evaluator = ProofLeaseEvaluator()
    with pytest.raises(TypeError, match="ProofLease"):
        evaluator.evaluate({}, _observation())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ProofLeaseObservation"):
        evaluator.evaluate(_lease(), {})  # type: ignore[arg-type]

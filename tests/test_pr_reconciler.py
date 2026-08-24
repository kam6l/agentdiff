"""Focused tests for sealed-identity pull-request reconciliation."""

from __future__ import annotations

from agentdiff.delivery import (
    PRReconciler,
    PRReconciliationDecision,
    PullRequestSnapshot,
    PullRequestState,
    SealedDeliveryIdentity,
)


def _identity(
    *,
    base: str = "base-a",
    patch: str = "patch-a",
    proof: str = "proof-a",
) -> SealedDeliveryIdentity:
    return SealedDeliveryIdentity(base, patch, proof)


def test_open_pr_with_exact_sealed_identity_is_reused_without_merge_authority() -> None:
    desired = _identity()
    result = PRReconciler().reconcile(
        desired,
        PullRequestSnapshot(42, PullRequestState.OPEN, desired, url="https://example/pr/42"),
    )

    assert result.decision is PRReconciliationDecision.REUSE
    assert result.exact_identity_match is True
    assert result.regeneration_allowed is False
    assert result.merge_allowed is False
    assert result.to_dict()["desired_identity"]["proof_digest"] == "proof-a"


def test_same_base_and_patch_with_new_proof_allows_metadata_update_only() -> None:
    result = PRReconciler().reconcile(
        _identity(proof="proof-new"),
        PullRequestSnapshot(7, PullRequestState.DRAFT, _identity(proof="proof-old")),
    )

    assert result.decision is PRReconciliationDecision.UPDATE
    assert result.base_matches is True
    assert result.patch_matches is True
    assert result.proof_matches is False
    assert result.metadata_update_only is True
    assert result.regeneration_allowed is False


def test_same_patch_on_changed_base_is_stale_and_requires_reproof() -> None:
    result = PRReconciler().reconcile(
        _identity(base="base-new"),
        PullRequestSnapshot(9, PullRequestState.OPEN, _identity(base="base-old")),
    )

    assert result.decision is PRReconciliationDecision.STALE
    assert result.requires_reproof is True
    assert result.patch_matches is True
    assert "reproof" in result.reason


def test_different_patch_is_closed_or_superseded_never_rewritten() -> None:
    result = PRReconciler().reconcile(
        _identity(patch="patch-new"),
        PullRequestSnapshot(11, PullRequestState.OPEN, _identity(patch="patch-old")),
    )

    assert result.decision is PRReconciliationDecision.CLOSE_OR_SUPERSEDE
    assert result.patch_matches is False
    assert result.metadata_update_only is False
    assert result.regeneration_allowed is False


def test_missing_identity_and_closed_pr_fail_closed() -> None:
    desired = _identity()
    missing = PRReconciler().reconcile(
        desired,
        PullRequestSnapshot(13, PullRequestState.OPEN, None),
    )
    closed = PRReconciler().reconcile(
        desired,
        PullRequestSnapshot(14, PullRequestState.CLOSED, desired),
    )

    assert missing.decision is PRReconciliationDecision.STALE
    assert missing.exact_identity_match is False
    assert closed.decision is PRReconciliationDecision.CLOSE_OR_SUPERSEDE


def test_merged_exact_identity_is_terminal_reuse_but_mismatch_is_superseded() -> None:
    desired = _identity()
    exact = PRReconciler().reconcile(
        desired,
        PullRequestSnapshot(20, PullRequestState.MERGED, desired),
    )
    mismatch = PRReconciler().reconcile(
        desired,
        PullRequestSnapshot(21, PullRequestState.MERGED, _identity(proof="old-proof")),
    )

    assert exact.decision is PRReconciliationDecision.REUSE
    assert exact.merge_allowed is False
    assert mismatch.decision is PRReconciliationDecision.CLOSE_OR_SUPERSEDE

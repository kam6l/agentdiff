"""Pure reconciliation for pull requests bound to sealed proof identities.

This module deliberately does not call GitHub, rewrite branches, regenerate a
patch, or merge anything.  It compares an existing pull-request snapshot with
the exact desired base, patch, and proof identities and emits the only safe
next disposition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PullRequestState(str, Enum):
    """Explicit remote lifecycle state used by the reconciler."""

    OPEN = "OPEN"
    DRAFT = "DRAFT"
    CLOSED = "CLOSED"
    MERGED = "MERGED"


class PRReconciliationDecision(str, Enum):
    """Safe disposition for an already-created pull request."""

    REUSE = "REUSE"
    UPDATE = "UPDATE"
    STALE = "STALE"
    CLOSE_OR_SUPERSEDE = "CLOSE_OR_SUPERSEDE"


@dataclass(frozen=True, slots=True)
class SealedDeliveryIdentity:
    """Exact content identities that bind delivery to deterministic proof."""

    base_sha: str
    patch_digest: str
    proof_digest: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field_name in ("base_sha", "patch_digest", "proof_digest"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{field_name} must be a non-empty exact identity")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "base_sha": self.base_sha,
            "patch_digest": self.patch_digest,
            "proof_digest": self.proof_digest,
        }


@dataclass(frozen=True, slots=True)
class PullRequestSnapshot:
    """Read-only facts about one existing pull request.

    ``identity=None`` represents a PR whose sealed identity metadata is absent
    or could not be verified.  Such a PR is never reused or updated.
    """

    number: int
    state: PullRequestState
    identity: SealedDeliveryIdentity | None
    url: str = ""
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.number, bool) or not isinstance(self.number, int) or self.number < 1:
            raise ValueError("pull request number must be a positive integer")
        if self.identity is not None and not isinstance(self.identity, SealedDeliveryIdentity):
            raise TypeError("pull request identity must be a SealedDeliveryIdentity")
        state = (
            self.state
            if isinstance(self.state, PullRequestState)
            else PullRequestState(str(self.state).upper())
        )
        object.__setattr__(self, "state", state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "number": self.number,
            "state": self.state.value,
            "identity": self.identity.to_dict() if self.identity is not None else None,
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class PRReconciliationResult:
    """Evidence-backed recommendation with deliberately narrow authority."""

    decision: PRReconciliationDecision
    pull_request: PullRequestSnapshot
    desired_identity: SealedDeliveryIdentity
    base_matches: bool
    patch_matches: bool
    proof_matches: bool
    reason: str
    schema_version: int = 1

    @property
    def exact_identity_match(self) -> bool:
        return self.base_matches and self.patch_matches and self.proof_matches

    @property
    def metadata_update_only(self) -> bool:
        """UPDATE may only refresh proof metadata for the same base and patch."""

        return self.decision is PRReconciliationDecision.UPDATE

    @property
    def requires_reproof(self) -> bool:
        return self.decision is PRReconciliationDecision.STALE

    @property
    def regeneration_allowed(self) -> bool:
        """A reconciler never authorizes patch regeneration."""

        return False

    @property
    def merge_allowed(self) -> bool:
        """A reconciler never authorizes or performs a merge."""

        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision": self.decision.value,
            "pull_request": self.pull_request.to_dict(),
            "desired_identity": self.desired_identity.to_dict(),
            "base_matches": self.base_matches,
            "patch_matches": self.patch_matches,
            "proof_matches": self.proof_matches,
            "exact_identity_match": self.exact_identity_match,
            "metadata_update_only": self.metadata_update_only,
            "requires_reproof": self.requires_reproof,
            "regeneration_allowed": self.regeneration_allowed,
            "merge_allowed": self.merge_allowed,
            "reason": self.reason,
        }


class PRReconciler:
    """Classify an existing PR using only state and exact sealed identities."""

    def reconcile(
        self,
        desired_identity: SealedDeliveryIdentity,
        pull_request: PullRequestSnapshot,
    ) -> PRReconciliationResult:
        observed = pull_request.identity
        base_matches = observed is not None and observed.base_sha == desired_identity.base_sha
        patch_matches = (
            observed is not None and observed.patch_digest == desired_identity.patch_digest
        )
        proof_matches = (
            observed is not None and observed.proof_digest == desired_identity.proof_digest
        )

        if pull_request.state is PullRequestState.CLOSED:
            return self._result(
                PRReconciliationDecision.CLOSE_OR_SUPERSEDE,
                pull_request,
                desired_identity,
                base_matches,
                patch_matches,
                proof_matches,
                "closed pull requests are not reusable delivery targets",
            )

        if pull_request.state is PullRequestState.MERGED:
            if base_matches and patch_matches and proof_matches:
                return self._result(
                    PRReconciliationDecision.REUSE,
                    pull_request,
                    desired_identity,
                    base_matches,
                    patch_matches,
                    proof_matches,
                    "the exact sealed delivery identity is already merged",
                )
            return self._result(
                PRReconciliationDecision.CLOSE_OR_SUPERSEDE,
                pull_request,
                desired_identity,
                base_matches,
                patch_matches,
                proof_matches,
                "a merged pull request is immutable and must be superseded",
            )

        if observed is None:
            return self._result(
                PRReconciliationDecision.STALE,
                pull_request,
                desired_identity,
                False,
                False,
                False,
                "pull request has no verified sealed delivery identity",
            )

        if not patch_matches:
            return self._result(
                PRReconciliationDecision.CLOSE_OR_SUPERSEDE,
                pull_request,
                desired_identity,
                base_matches,
                patch_matches,
                proof_matches,
                "pull request contains a different sealed patch",
            )

        if not base_matches:
            return self._result(
                PRReconciliationDecision.STALE,
                pull_request,
                desired_identity,
                base_matches,
                patch_matches,
                proof_matches,
                "sealed base identity changed; rebase and independent reproof are required",
            )

        if not proof_matches:
            return self._result(
                PRReconciliationDecision.UPDATE,
                pull_request,
                desired_identity,
                base_matches,
                patch_matches,
                proof_matches,
                "base and patch match; only sealed proof metadata may be refreshed",
            )

        return self._result(
            PRReconciliationDecision.REUSE,
            pull_request,
            desired_identity,
            base_matches,
            patch_matches,
            proof_matches,
            "open pull request exactly matches the sealed base, patch, and proof",
        )

    @staticmethod
    def _result(
        decision: PRReconciliationDecision,
        pull_request: PullRequestSnapshot,
        desired_identity: SealedDeliveryIdentity,
        base_matches: bool,
        patch_matches: bool,
        proof_matches: bool,
        reason: str,
    ) -> PRReconciliationResult:
        return PRReconciliationResult(
            decision=decision,
            pull_request=pull_request,
            desired_identity=desired_identity,
            base_matches=base_matches,
            patch_matches=patch_matches,
            proof_matches=proof_matches,
            reason=reason,
        )


# Compact product-language alias.
PRIdentity = SealedDeliveryIdentity


__all__ = [
    "PRIdentity",
    "PRReconciler",
    "PRReconciliationDecision",
    "PRReconciliationResult",
    "PullRequestSnapshot",
    "PullRequestState",
    "SealedDeliveryIdentity",
]

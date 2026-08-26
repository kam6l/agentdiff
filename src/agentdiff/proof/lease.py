"""Fail-closed freshness leases for an already completed proof.

A lease does not issue, modify, or restamp a certificate. It records the exact
inputs under which an existing proof was established and deterministically
decides whether later repository movement is provably disjoint from that proof.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agentdiff.pathing import normalize_relative_path

_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OBSERVATION_FIELDS = frozenset(
    {
        "base_sha",
        "patch_digest",
        "proof_plan_digest",
        "lockfile_digest",
        "runtime_digest",
        "changed_paths",
        "changed_paths_complete",
        "base_lineage_verified",
    }
)


class ProofLeaseStatus(str, Enum):
    """Freshness state of the proof bound by a lease."""

    VALID = "VALID"
    INVALIDATED = "INVALIDATED"


class ProofLeaseInvalidation(str, Enum):
    """Complete fail-closed invalidation policy for a proof lease."""

    PATCH_DIGEST_CHANGED = "patch_digest_changed"
    PROOF_PLAN_DIGEST_CHANGED = "proof_plan_digest_changed"
    LOCKFILE_DIGEST_CHANGED = "lockfile_digest_changed"
    RUNTIME_DIGEST_CHANGED = "runtime_digest_changed"
    DEPENDENCY_CLOSURE_INCOMPLETE = "dependency_closure_incomplete"
    BASE_LINEAGE_UNVERIFIED = "base_lineage_unverified"
    CHANGED_PATHS_INCOMPLETE = "changed_paths_incomplete"
    DEPENDENCY_CLOSURE_TOUCHED = "dependency_closure_touched"


_REQUIRED_INVALIDATIONS = tuple(ProofLeaseInvalidation)


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("proof lease value is not canonically serializable") from error
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object with string keys")
    return value


def _reject_unknown(
    value: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    field: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{field} contains unknown fields: {', '.join(unknown)}")


def _clean_git_sha(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase 40- or 64-character Git SHA")
    return value


def _clean_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _clean_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _clean_paths(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of repository-relative paths")
    if len(value) > 100_000:
        raise ValueError(f"{field} exceeds the 100000 item limit")
    paths: list[str] = []
    for path in value:
        if not isinstance(path, str):
            raise ValueError(f"{field} must contain only strings")
        paths.append(normalize_relative_path(path))
    return tuple(sorted(set(paths)))


def _clean_invalidation_rules(value: object) -> tuple[ProofLeaseInvalidation, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("invalidation_rules must be a list")
    try:
        rules = tuple(ProofLeaseInvalidation(item) for item in value)
    except (TypeError, ValueError) as error:
        raise ValueError("invalidation_rules contains an invalid rule") from error
    if len(rules) != len(set(rules)):
        raise ValueError("invalidation_rules cannot contain duplicates")
    if set(rules) != set(_REQUIRED_INVALIDATIONS):
        raise ValueError("invalidation_rules must contain the complete fail-closed policy")
    return _REQUIRED_INVALIDATIONS


@dataclass(frozen=True, slots=True)
class ProofLease:
    """Exact proof inputs and the verified dependency closure they cover."""

    base_sha: str
    patch_digest: str
    proof_plan_digest: str
    lockfile_digest: str
    runtime_digest: str
    dependency_closure: tuple[str, ...]
    closure_complete: bool
    invalidation_rules: tuple[ProofLeaseInvalidation, ...] = _REQUIRED_INVALIDATIONS
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ProofLease schema version")
        object.__setattr__(self, "base_sha", _clean_git_sha(self.base_sha, field="base_sha"))
        for field in (
            "patch_digest",
            "proof_plan_digest",
            "lockfile_digest",
            "runtime_digest",
        ):
            object.__setattr__(self, field, _clean_digest(getattr(self, field), field=field))
        closure = _clean_paths(self.dependency_closure, field="dependency_closure")
        if not closure:
            raise ValueError("dependency_closure must contain at least one path")
        object.__setattr__(self, "dependency_closure", closure)
        object.__setattr__(
            self,
            "closure_complete",
            _clean_bool(self.closure_complete, field="closure_complete"),
        )
        object.__setattr__(
            self,
            "invalidation_rules",
            _clean_invalidation_rules(self.invalidation_rules),
        )

    @property
    def id(self) -> str:
        return f"proof-lease-{_canonical_sha256(self._payload())[:24]}"

    @property
    def digest(self) -> str:
        return _canonical_sha256(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "base_sha": self.base_sha,
            "patch_digest": self.patch_digest,
            "proof_plan_digest": self.proof_plan_digest,
            "lockfile_digest": self.lockfile_digest,
            "runtime_digest": self.runtime_digest,
            "dependency_closure": list(self.dependency_closure),
            "closure_complete": self.closure_complete,
            "invalidation_rules": [rule.value for rule in self.invalidation_rules],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "id": self.id, "digest": self.digest}

    @classmethod
    def from_dict(cls, value: object) -> ProofLease:
        data = _require_mapping(value, field="ProofLease")
        _reject_unknown(
            data,
            allowed=frozenset(
                {
                    "schema_version",
                    "id",
                    "digest",
                    "base_sha",
                    "patch_digest",
                    "proof_plan_digest",
                    "lockfile_digest",
                    "runtime_digest",
                    "dependency_closure",
                    "closure_complete",
                    "invalidation_rules",
                }
            ),
            field="ProofLease",
        )
        version = data.get("schema_version")
        if isinstance(version, bool) or version != 1:
            raise ValueError("unsupported ProofLease schema version")
        lease = cls(
            base_sha=data.get("base_sha", ""),
            patch_digest=data.get("patch_digest", ""),
            proof_plan_digest=data.get("proof_plan_digest", ""),
            lockfile_digest=data.get("lockfile_digest", ""),
            runtime_digest=data.get("runtime_digest", ""),
            dependency_closure=_clean_paths(
                data.get("dependency_closure"), field="dependency_closure"
            ),
            closure_complete=_clean_bool(data.get("closure_complete"), field="closure_complete"),
            invalidation_rules=_clean_invalidation_rules(data.get("invalidation_rules")),
        )
        if data.get("id", lease.id) != lease.id:
            raise ValueError("ProofLease id does not match its canonical payload")
        if data.get("digest", lease.digest) != lease.digest:
            raise ValueError("ProofLease digest does not match its canonical payload")
        return lease


@dataclass(frozen=True, slots=True)
class ProofLeaseObservation:
    """Trusted current inputs used to evaluate one lease.

    ``changed_paths_complete`` attests that ``changed_paths`` is the complete
    repository-relative change set since ``lease.base_sha``. When the base SHA
    moves, ``base_lineage_verified`` must independently attest ancestry.
    """

    base_sha: str
    patch_digest: str
    proof_plan_digest: str
    lockfile_digest: str
    runtime_digest: str
    changed_paths: tuple[str, ...] = ()
    changed_paths_complete: bool = False
    base_lineage_verified: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_sha", _clean_git_sha(self.base_sha, field="base_sha"))
        for field in (
            "patch_digest",
            "proof_plan_digest",
            "lockfile_digest",
            "runtime_digest",
        ):
            object.__setattr__(self, field, _clean_digest(getattr(self, field), field=field))
        object.__setattr__(
            self,
            "changed_paths",
            _clean_paths(self.changed_paths, field="changed_paths"),
        )
        object.__setattr__(
            self,
            "changed_paths_complete",
            _clean_bool(self.changed_paths_complete, field="changed_paths_complete"),
        )
        object.__setattr__(
            self,
            "base_lineage_verified",
            _clean_bool(self.base_lineage_verified, field="base_lineage_verified"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_sha": self.base_sha,
            "patch_digest": self.patch_digest,
            "proof_plan_digest": self.proof_plan_digest,
            "lockfile_digest": self.lockfile_digest,
            "runtime_digest": self.runtime_digest,
            "changed_paths": list(self.changed_paths),
            "changed_paths_complete": self.changed_paths_complete,
            "base_lineage_verified": self.base_lineage_verified,
        }

    @classmethod
    def from_dict(cls, value: object) -> ProofLeaseObservation:
        data = _require_mapping(value, field="ProofLeaseObservation")
        _reject_unknown(data, allowed=_OBSERVATION_FIELDS, field="ProofLeaseObservation")
        return cls(
            base_sha=data.get("base_sha", ""),
            patch_digest=data.get("patch_digest", ""),
            proof_plan_digest=data.get("proof_plan_digest", ""),
            lockfile_digest=data.get("lockfile_digest", ""),
            runtime_digest=data.get("runtime_digest", ""),
            changed_paths=_clean_paths(data.get("changed_paths", []), field="changed_paths"),
            changed_paths_complete=_clean_bool(
                data.get("changed_paths_complete"), field="changed_paths_complete"
            ),
            base_lineage_verified=_clean_bool(
                data.get("base_lineage_verified"), field="base_lineage_verified"
            ),
        )


@dataclass(frozen=True, slots=True)
class ProofLeaseEvaluation:
    """Deterministic freshness result; never a replacement certificate."""

    lease_id: str
    status: ProofLeaseStatus
    current_base_sha: str
    invalidations: tuple[ProofLeaseInvalidation, ...]
    changed_paths: tuple[str, ...]
    intersecting_paths: tuple[str, ...]
    disjoint_paths: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.status is ProofLeaseStatus.VALID

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "status": self.status.value,
            "valid": self.valid,
            "current_base_sha": self.current_base_sha,
            "invalidations": [reason.value for reason in self.invalidations],
            "changed_paths": list(self.changed_paths),
            "intersecting_paths": list(self.intersecting_paths),
            "disjoint_paths": list(self.disjoint_paths),
        }


class ProofLeaseEvaluator:
    """Evaluate freshness using only explicit, deterministic lease bindings."""

    def evaluate(
        self,
        lease: ProofLease,
        observation: ProofLeaseObservation,
    ) -> ProofLeaseEvaluation:
        if not isinstance(lease, ProofLease):
            raise TypeError("lease must be a ProofLease")
        if not isinstance(observation, ProofLeaseObservation):
            raise TypeError("observation must be a ProofLeaseObservation")

        invalidations: list[ProofLeaseInvalidation] = []
        comparisons = (
            (
                lease.patch_digest,
                observation.patch_digest,
                ProofLeaseInvalidation.PATCH_DIGEST_CHANGED,
            ),
            (
                lease.proof_plan_digest,
                observation.proof_plan_digest,
                ProofLeaseInvalidation.PROOF_PLAN_DIGEST_CHANGED,
            ),
            (
                lease.lockfile_digest,
                observation.lockfile_digest,
                ProofLeaseInvalidation.LOCKFILE_DIGEST_CHANGED,
            ),
            (
                lease.runtime_digest,
                observation.runtime_digest,
                ProofLeaseInvalidation.RUNTIME_DIGEST_CHANGED,
            ),
        )
        invalidations.extend(
            reason for expected, current, reason in comparisons if expected != current
        )

        if not lease.closure_complete:
            invalidations.append(ProofLeaseInvalidation.DEPENDENCY_CLOSURE_INCOMPLETE)

        base_moved = observation.base_sha != lease.base_sha
        workspace_moved = base_moved or bool(observation.changed_paths)
        if base_moved and not observation.base_lineage_verified:
            invalidations.append(ProofLeaseInvalidation.BASE_LINEAGE_UNVERIFIED)
        if workspace_moved and not observation.changed_paths_complete:
            invalidations.append(ProofLeaseInvalidation.CHANGED_PATHS_INCOMPLETE)

        intersecting = tuple(
            path
            for path in observation.changed_paths
            if any(_paths_overlap(path, dependency) for dependency in lease.dependency_closure)
        )
        if intersecting:
            invalidations.append(ProofLeaseInvalidation.DEPENDENCY_CLOSURE_TOUCHED)

        trusted_classification = lease.closure_complete and (
            not workspace_moved or observation.changed_paths_complete
        )
        intersecting_set = set(intersecting)
        disjoint = (
            tuple(path for path in observation.changed_paths if path not in intersecting_set)
            if trusted_classification
            else ()
        )
        status = ProofLeaseStatus.INVALIDATED if invalidations else ProofLeaseStatus.VALID
        return ProofLeaseEvaluation(
            lease_id=lease.id,
            status=status,
            current_base_sha=observation.base_sha,
            invalidations=tuple(invalidations),
            changed_paths=observation.changed_paths,
            intersecting_paths=intersecting,
            disjoint_paths=disjoint,
        )


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")

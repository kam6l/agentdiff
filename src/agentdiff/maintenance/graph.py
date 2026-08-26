"""Canonical provenance graph for the verified maintenance lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ._canonical import (
    canonical_sha256,
    clean_confidence,
    clean_identifier,
    clean_string_tuple,
    clean_text,
    clean_timestamp,
    reject_unknown,
    require_mapping,
)

_MAX_GRAPH_ITEMS = 100_000


class MaintenanceEntityKind(str, Enum):
    """Canonical entities in the maintenance lifecycle."""

    UPSTREAM_EVENT = "upstream_event"
    CHANGE_SPEC = "change_spec"
    EXPOSURE = "exposure"
    REPOSITORY = "repository"
    CANDIDATE_PATCH = "candidate_patch"
    BEHAVIOR_CONTRACT = "behavior_contract"
    PROOF = "proof"
    CERTIFICATE = "certificate"
    PROOF_LEASE = "proof_lease"
    PULL_REQUEST = "pull_request"
    DEPLOYMENT = "deployment"
    OUTCOME = "outcome"


@dataclass(frozen=True, slots=True)
class MaintenanceNode:
    """One immutable entity reference with provenance and evidence bindings."""

    kind: MaintenanceEntityKind
    key: str
    source: str
    timestamp: str
    status: str
    provenance: tuple[str, ...] = ()
    confidence: float = 1.0
    evidence: tuple[str, ...] = ()
    content_digest: str = ""

    def __post_init__(self) -> None:
        try:
            kind = MaintenanceEntityKind(self.kind)
        except ValueError as error:
            raise ValueError("node.kind is invalid") from error
        object.__setattr__(self, "kind", kind)
        object.__setattr__(
            self,
            "key",
            clean_text(self.key, field="node.key", required=True, max_length=512),
        )
        object.__setattr__(
            self,
            "source",
            clean_text(self.source, field="node.source", required=True, max_length=2048),
        )
        object.__setattr__(
            self,
            "timestamp",
            clean_timestamp(self.timestamp, field="node.timestamp"),
        )
        object.__setattr__(
            self,
            "status",
            clean_text(self.status, field="node.status", required=True, max_length=128),
        )
        object.__setattr__(
            self,
            "provenance",
            clean_string_tuple(self.provenance, field="node.provenance"),
        )
        object.__setattr__(
            self,
            "confidence",
            clean_confidence(self.confidence, field="node.confidence"),
        )
        object.__setattr__(
            self,
            "evidence",
            clean_string_tuple(self.evidence, field="node.evidence"),
        )
        object.__setattr__(
            self,
            "content_digest",
            clean_text(self.content_digest, field="node.content_digest", max_length=256),
        )

    @property
    def id(self) -> str:
        identity = {"kind": self.kind.value, "key": self.key}
        return f"{self.kind.value}-{canonical_sha256(identity)[:24]}"

    @property
    def digest(self) -> str:
        return canonical_sha256(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "key": self.key,
            "source": self.source,
            "timestamp": self.timestamp,
            "status": self.status,
            "provenance": list(self.provenance),
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "content_digest": self.content_digest,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "id": self.id, "digest": self.digest}

    @classmethod
    def from_dict(cls, value: object) -> MaintenanceNode:
        data = require_mapping(value, field="node")
        reject_unknown(
            data,
            frozenset(
                {
                    "id",
                    "digest",
                    "kind",
                    "key",
                    "source",
                    "timestamp",
                    "status",
                    "provenance",
                    "confidence",
                    "evidence",
                    "content_digest",
                }
            ),
            field="node",
        )
        try:
            kind = MaintenanceEntityKind(data.get("kind", ""))
        except ValueError as error:
            raise ValueError("node.kind is invalid") from error
        node = cls(
            kind=kind,
            key=data.get("key", ""),
            source=data.get("source", ""),
            timestamp=data.get("timestamp", ""),
            status=data.get("status", ""),
            provenance=clean_string_tuple(data.get("provenance", []), field="node.provenance"),
            confidence=clean_confidence(data.get("confidence", 1.0), field="node.confidence"),
            evidence=clean_string_tuple(data.get("evidence", []), field="node.evidence"),
            content_digest=data.get("content_digest", ""),
        )
        if data.get("id", node.id) != node.id:
            raise ValueError("node id does not match its canonical identity")
        if data.get("digest", node.digest) != node.digest:
            raise ValueError("node digest does not match its canonical payload")
        return node


@dataclass(frozen=True, slots=True)
class MaintenanceEdge:
    """One immutable lifecycle relation with its own provenance."""

    source_id: str
    target_id: str
    relationship: str
    source: str
    timestamp: str
    status: str
    provenance: tuple[str, ...] = ()
    confidence: float = 1.0
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            clean_text(
                self.source_id,
                field="edge.source_id",
                required=True,
                max_length=256,
            ),
        )
        object.__setattr__(
            self,
            "target_id",
            clean_text(
                self.target_id,
                field="edge.target_id",
                required=True,
                max_length=256,
            ),
        )
        if self.source_id == self.target_id:
            raise ValueError("edge cannot connect a node to itself")
        object.__setattr__(
            self,
            "relationship",
            clean_identifier(self.relationship, field="edge.relationship"),
        )
        object.__setattr__(
            self,
            "source",
            clean_text(self.source, field="edge.source", required=True, max_length=2048),
        )
        object.__setattr__(
            self,
            "timestamp",
            clean_timestamp(self.timestamp, field="edge.timestamp"),
        )
        object.__setattr__(
            self,
            "status",
            clean_text(self.status, field="edge.status", required=True, max_length=128),
        )
        object.__setattr__(
            self,
            "provenance",
            clean_string_tuple(self.provenance, field="edge.provenance"),
        )
        object.__setattr__(
            self,
            "confidence",
            clean_confidence(self.confidence, field="edge.confidence"),
        )
        object.__setattr__(
            self,
            "evidence",
            clean_string_tuple(self.evidence, field="edge.evidence"),
        )

    @property
    def id(self) -> str:
        identity = {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship": self.relationship,
        }
        return f"edge-{canonical_sha256(identity)[:24]}"

    @property
    def digest(self) -> str:
        return canonical_sha256(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship": self.relationship,
            "source": self.source,
            "timestamp": self.timestamp,
            "status": self.status,
            "provenance": list(self.provenance),
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "id": self.id, "digest": self.digest}

    @classmethod
    def from_dict(cls, value: object) -> MaintenanceEdge:
        data = require_mapping(value, field="edge")
        reject_unknown(
            data,
            frozenset(
                {
                    "id",
                    "digest",
                    "source_id",
                    "target_id",
                    "relationship",
                    "source",
                    "timestamp",
                    "status",
                    "provenance",
                    "confidence",
                    "evidence",
                }
            ),
            field="edge",
        )
        edge = cls(
            source_id=data.get("source_id", ""),
            target_id=data.get("target_id", ""),
            relationship=data.get("relationship", ""),
            source=data.get("source", ""),
            timestamp=data.get("timestamp", ""),
            status=data.get("status", ""),
            provenance=clean_string_tuple(data.get("provenance", []), field="edge.provenance"),
            confidence=clean_confidence(data.get("confidence", 1.0), field="edge.confidence"),
            evidence=clean_string_tuple(data.get("evidence", []), field="edge.evidence"),
        )
        if data.get("id", edge.id) != edge.id:
            raise ValueError("edge id does not match its canonical identity")
        if data.get("digest", edge.digest) != edge.digest:
            raise ValueError("edge digest does not match its canonical payload")
        return edge


@dataclass(frozen=True, slots=True)
class MaintenanceGraph:
    """A validated immutable snapshot of maintenance nodes and edges."""

    nodes: tuple[MaintenanceNode, ...] = ()
    edges: tuple[MaintenanceEdge, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported MaintenanceGraph schema version")
        if not isinstance(self.nodes, tuple) or any(
            not isinstance(node, MaintenanceNode) for node in self.nodes
        ):
            raise ValueError("graph.nodes must be a tuple of MaintenanceNode values")
        if not isinstance(self.edges, tuple) or any(
            not isinstance(edge, MaintenanceEdge) for edge in self.edges
        ):
            raise ValueError("graph.edges must be a tuple of MaintenanceEdge values")
        if len(self.nodes) > _MAX_GRAPH_ITEMS or len(self.edges) > _MAX_GRAPH_ITEMS:
            raise ValueError(f"graph exceeds the {_MAX_GRAPH_ITEMS} item limit")
        nodes = tuple(sorted(self.nodes, key=lambda node: node.id))
        edges = tuple(sorted(self.edges, key=lambda edge: edge.id))
        node_ids = [node.id for node in nodes]
        edge_ids = [edge.id for edge in edges]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("graph contains duplicate node identities")
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("graph contains duplicate edge identities")
        known_nodes = set(node_ids)
        dangling = sorted(
            {
                endpoint
                for edge in edges
                for endpoint in (edge.source_id, edge.target_id)
                if endpoint not in known_nodes
            }
        )
        if dangling:
            raise ValueError("graph contains dangling edge endpoints: " + ", ".join(dangling))
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "edges", edges)

    @property
    def id(self) -> str:
        identity = {
            "schema_version": self.schema_version,
            "nodes": [node.id for node in self.nodes],
            "edges": [edge.id for edge in self.edges],
        }
        return f"maintenance-graph-{canonical_sha256(identity)[:24]}"

    @property
    def digest(self) -> str:
        return canonical_sha256(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "id": self.id, "digest": self.digest}

    @classmethod
    def from_dict(cls, value: object) -> MaintenanceGraph:
        data = require_mapping(value, field="MaintenanceGraph")
        reject_unknown(
            data,
            frozenset({"schema_version", "id", "digest", "nodes", "edges"}),
            field="MaintenanceGraph",
        )
        version = data.get("schema_version", 0)
        if isinstance(version, bool) or version != 1:
            raise ValueError("unsupported MaintenanceGraph schema version")
        raw_nodes = data.get("nodes")
        raw_edges = data.get("edges")
        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise ValueError("graph nodes and edges must be lists")
        graph = cls(
            nodes=tuple(MaintenanceNode.from_dict(node) for node in raw_nodes),
            edges=tuple(MaintenanceEdge.from_dict(edge) for edge in raw_edges),
        )
        if data.get("id", graph.id) != graph.id:
            raise ValueError("graph id does not match its canonical identity")
        if data.get("digest", graph.digest) != graph.digest:
            raise ValueError("graph digest does not match its canonical payload")
        return graph

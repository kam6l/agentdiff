from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

import agentdiff.maintenance.store as maintenance_store
from agentdiff.api.manifest import get_builtin_manifest
from agentdiff.maintenance import (
    ChangeDelivery,
    ChangeProof,
    ChangeSource,
    ChangeSpec,
    ChangeStrategy,
    ChangeTargets,
    LocalJSONMaintenanceStore,
    MaintenanceEdge,
    MaintenanceEntityKind,
    MaintenanceGraph,
    MaintenanceGraphStore,
    MaintenanceNode,
    MaintenanceSeverity,
    PriorityDecision,
    PriorityEngine,
    PriorityInputs,
    ProofRequirement,
    StrategyDisposition,
)

if TYPE_CHECKING:
    from pathlib import Path


_NOW = "2026-08-22T12:00:00+00:00"


def _spec() -> ChangeSpec:
    return ChangeSpec(
        kind="upstream_change",
        external_id="sdk-4-removal",
        title="Remove the retired SDK call",
        description="The old call is unavailable in SDK 4.",
        source=ChangeSource(
            type="sdk_release",
            provider="example",
            version="4.0.0",
            uri="https://example.test/releases/4.0.0",
            retrieved_at=_NOW,
            content_digest="sha256:release-notes",
            provenance=("release-feed", "signed-index"),
        ),
        targets=ChangeTargets(
            symbols=("client.old_call", "Client.old_call"),
            packages=("example-sdk",),
        ),
        severity=MaintenanceSeverity.HIGH,
        strategy=ChangeStrategy(
            deterministic=StrategyDisposition.PREFERRED,
            agent=StrategyDisposition.FALLBACK,
            transform_id="example-old-call-v1",
        ),
        proof=ChangeProof(
            required=ProofRequirement.CAUSAL,
            behavior_contracts=("old-call-is-replaced",),
        ),
        delivery=ChangeDelivery(open_pr=True),
        deadline="2026-09-30",
        confidence=0.9,
    )


def _nodes() -> tuple[MaintenanceNode, MaintenanceNode]:
    spec = _spec()
    change = MaintenanceNode(
        kind=MaintenanceEntityKind.CHANGE_SPEC,
        key=spec.id,
        source=spec.source.uri,
        timestamp=_NOW,
        status="validated",
        provenance=("change-radar", spec.source.uri),
        confidence=spec.confidence,
        evidence=(spec.digest,),
        content_digest=spec.digest,
    )
    repository = MaintenanceNode(
        kind=MaintenanceEntityKind.REPOSITORY,
        key="github.com/example/payments",
        source="github-app-installation:42",
        timestamp=_NOW,
        status="exposed",
        provenance=("installation:42", "exposure-scan:123"),
        confidence=1.0,
        evidence=("blob:payments-client.py",),
        content_digest="sha256:repository-tree",
    )
    return change, repository


def _graph() -> MaintenanceGraph:
    change, repository = _nodes()
    edge = MaintenanceEdge(
        source_id=change.id,
        target_id=repository.id,
        relationship="affects",
        source="exposure-scan:123",
        timestamp=_NOW,
        status="confirmed",
        provenance=("scanner:v1",),
        confidence=0.95,
        evidence=("blob:payments-client.py#L12",),
    )
    return MaintenanceGraph(nodes=(repository, change), edges=(edge,))


def _priority_inputs() -> PriorityInputs:
    return PriorityInputs(
        security_severity=MaintenanceSeverity.MODERATE,
        repository_criticality=50,
        usage_count=5,
        blast_radius=40,
        version_distance=2,
        deterministic_transform=True,
        test_quality=80,
        proof_available=True,
        owners=("payments",),
        maintenance_window_open=True,
    )


def test_change_spec_is_immutable_canonical_and_round_trips() -> None:
    spec = _spec()
    reordered = replace(
        spec,
        source=replace(
            spec.source,
            retrieved_at="2026-08-22T05:00:00-07:00",
            provenance=tuple(reversed(spec.source.provenance)),
        ),
        targets=replace(spec.targets, symbols=tuple(reversed(spec.targets.symbols))),
    )

    assert reordered == spec
    assert reordered.id == spec.id
    assert reordered.digest == spec.digest
    assert ChangeSpec.from_dict(json.loads(json.dumps(spec.to_dict()))) == spec
    with pytest.raises(AttributeError):
        spec.title = "mutated"  # type: ignore[misc]

    revised = replace(spec, description="A more detailed explanation.")
    assert revised.id == spec.id
    assert revised.digest != spec.digest
    assert replace(spec, confidence=-0.0).digest == replace(spec, confidence=0.0).digest


def test_change_spec_adapts_existing_api_manifest_without_mutating_it() -> None:
    manifest = get_builtin_manifest("openai", "chat_to_responses")
    assert manifest is not None
    original = manifest.to_dict()

    spec = ChangeSpec.from_api_manifest(manifest)

    assert manifest.to_dict() == original
    assert spec.kind == "upstream_change"
    assert spec.external_id == manifest.change_id
    assert spec.source.provider == manifest.provider
    assert spec.targets.symbols == manifest.affected.symbols
    assert spec.strategy.deterministic is StrategyDisposition.PREFERRED
    assert spec.strategy.agent is StrategyDisposition.FALLBACK
    assert spec.proof.required is ProofRequirement.STRONG
    assert spec.delivery == ChangeDelivery(open_pr=False, auto_merge=False)


def test_change_spec_rejects_malformed_and_tampered_data() -> None:
    with pytest.raises(ValueError, match="at least one selector"):
        ChangeTargets()
    with pytest.raises(ValueError, match="requires"):
        ChangeDelivery(auto_merge=True)
    with pytest.raises(ValueError, match="object"):
        ChangeSpec.from_dict([])

    unknown = _spec().to_dict()
    unknown["surprise"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        ChangeSpec.from_dict(unknown)

    invalid_severity = _spec().to_dict()
    invalid_severity["severity"] = "urgent-ish"
    with pytest.raises(ValueError, match="severity"):
        ChangeSpec.from_dict(invalid_severity)

    tampered = _spec().to_dict()
    tampered["title"] = "Unverified replacement title"
    with pytest.raises(ValueError, match="digest"):
        ChangeSpec.from_dict(tampered)


def test_graph_is_canonical_provenance_rich_and_round_trips() -> None:
    graph = _graph()
    reordered = MaintenanceGraph(
        nodes=tuple(reversed(graph.nodes)),
        edges=tuple(reversed(graph.edges)),
    )

    assert reordered == graph
    assert reordered.id == graph.id
    assert reordered.digest == graph.digest
    assert MaintenanceGraph.from_dict(json.loads(json.dumps(graph.to_dict()))) == graph
    assert all(node.provenance and node.evidence and node.digest for node in graph.nodes)
    assert all(edge.provenance and edge.evidence and edge.digest for edge in graph.edges)


def test_graph_rejects_duplicate_dangling_and_tampered_data() -> None:
    change, repository = _nodes()
    edge = MaintenanceEdge(
        source_id=change.id,
        target_id=repository.id,
        relationship="affects",
        source="exposure-scan:123",
        timestamp=_NOW,
        status="confirmed",
    )
    with pytest.raises(ValueError, match="duplicate node"):
        MaintenanceGraph(nodes=(change, change))
    with pytest.raises(ValueError, match="duplicate edge"):
        MaintenanceGraph(nodes=(change, repository), edges=(edge, edge))

    dangling = replace(edge, source_id="change-spec-missing")
    with pytest.raises(ValueError, match="dangling"):
        MaintenanceGraph(nodes=(change, repository), edges=(dangling,))

    tampered = _graph().to_dict()
    tampered["nodes"][0]["status"] = "silently-modified"
    with pytest.raises(ValueError, match="digest"):
        MaintenanceGraph.from_dict(tampered)


def test_local_store_round_trips_deterministically_and_privately(tmp_path: Path) -> None:
    path = tmp_path / "state" / "maintenance-graph.json"
    store = LocalJSONMaintenanceStore(path)
    graph = _graph()

    assert isinstance(store, MaintenanceGraphStore)
    assert store.load() is None
    assert store.save(graph) == path
    first_payload = path.read_bytes()
    assert store.load() == graph
    store.save(graph)
    assert path.read_bytes() == first_payload
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_local_store_preserves_old_snapshot_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "maintenance-graph.json"
    store = LocalJSONMaintenanceStore(path)
    graph = _graph()
    store.save(graph)
    original = path.read_bytes()
    outcome = MaintenanceNode(
        kind=MaintenanceEntityKind.OUTCOME,
        key="deployment:42",
        source="post-merge-verifier",
        timestamp=_NOW,
        status="healthy",
    )
    updated = MaintenanceGraph(nodes=(*graph.nodes, outcome), edges=graph.edges)

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("injected replacement failure")

    monkeypatch.setattr(maintenance_store.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        store.save(updated)

    assert path.read_bytes() == original
    assert store.load() == graph
    assert not tuple(tmp_path.glob(f".{path.name}.*.tmp"))


def test_local_store_rejects_symlink_paths(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    leaf_link = tmp_path / "leaf-link.json"
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    parent_link = tmp_path / "parent-link"
    try:
        leaf_link.symlink_to(outside)
        parent_link.symlink_to(real_parent, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")

    with pytest.raises(ValueError, match="symlink"):
        LocalJSONMaintenanceStore(leaf_link).load()
    with pytest.raises(ValueError, match="symlink"):
        LocalJSONMaintenanceStore(parent_link / "graph.json").save(_graph())


def test_local_store_rejects_invalid_and_oversized_json(tmp_path: Path) -> None:
    path = tmp_path / "maintenance-graph.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        LocalJSONMaintenanceStore(path).load()

    path.write_text("12345", encoding="utf-8")
    with pytest.raises(ValueError, match="size limit"):
        LocalJSONMaintenanceStore(path, max_bytes=4).load()


def test_priority_engine_produces_all_decisions_deterministically() -> None:
    engine = PriorityEngine()
    base = _priority_inputs()
    fix_now = replace(
        base,
        breaking_deadline="2026-08-27T12:00:00Z",
        evaluated_at=_NOW,
    )
    urgent = replace(
        base,
        security_severity=MaintenanceSeverity.HIGH,
        repository_criticality=100,
        usage_count=15,
        blast_radius=100,
        version_distance=5,
    )

    cases = {
        PriorityDecision.FIX_NOW: fix_now,
        PriorityDecision.SCHEDULE: replace(urgent, maintenance_window_open=False),
        PriorityDecision.REVIEW: replace(urgent, owners=()),
        PriorityDecision.IGNORE: replace(base, usage_count=0),
    }
    for expected, inputs in cases.items():
        first = engine.decide(inputs)
        assert first.decision is expected
        assert first == engine.decide(inputs)
        assert first.reasons


def test_priority_inputs_round_trip_and_reject_ambiguous_data() -> None:
    inputs = _priority_inputs()
    assert PriorityInputs.from_dict(inputs.to_dict()) == inputs

    malformed = inputs.to_dict()
    malformed["maintenance_window_open"] = 1
    with pytest.raises(ValueError, match="boolean"):
        PriorityInputs.from_dict(malformed)
    with pytest.raises(ValueError, match="between 0 and 100"):
        replace(inputs, test_quality=101)
    with pytest.raises(ValueError, match="provided together"):
        replace(inputs, breaking_deadline="2026-09-01T00:00:00Z")

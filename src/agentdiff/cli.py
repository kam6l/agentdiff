#!/usr/bin/env python3
"""AgentDiff command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentdiff.api import (
    APIMatcher,
    APIScanner,
    ChangeSeverity,
    detect_installed_sdk_versions,
    get_providers_for_selection,
)
from agentdiff.cortex import (
    AgentMemoryStore,
    ContextCompressor,
    ContextPacker,
    CortexRouter,
    RemediationAdvisor,
    RepositoryMemoryProvider,
    SkillCardGenerator,
)
from agentdiff.diff_engine import DiffEngine, EnvironmentSnapshot, FilesystemSnapshot
from agentdiff.doctor import doctor_report
from agentdiff.evaluator import AgentDiffEvaluator
from agentdiff.impact.cache import ProofCache
from agentdiff.impact.impact import ImpactEngine
from agentdiff.policy import (
    Policy,
    PolicyAction,
    PolicyEngine,
    PolicyLoadError,
    PolicyValidationError,
    load_policy,
    load_policy_file,
)
from agentdiff.promotion import PromotionEngine
from agentdiff.proof import ProofEngine, ProofVerdict
from agentdiff.providers import (
    PROVIDER_NAMES,
    OllamaEmbeddingProvider,
    ProviderError,
    create_provider,
)
from agentdiff.redaction import safe_display
from agentdiff.repair import RepairLoop
from agentdiff.runtime import SandboxRuntime
from agentdiff.scoring.blast_radius import RiskLevel
from agentdiff.sidecar import (
    SidecarClient,
    SidecarError,
    WrapRunner,
    ensure_sidecar,
)
from agentdiff.trajectory import AgentFramework, TrajectoryTracker
from agentdiff.transaction import (
    AgentRunTransaction,
    RollbackEngine,
    RunInspector,
    RunStore,
    list_runs,
)
from agentdiff.trust import RepoImpactGraph, TrustCompiler
from agentdiff.workspace import WarmWorkspaceFactory, compute_identity

_DEFAULT_POLICY: dict[str, Any] = {
    "version": 1,
    "filesystem": {
        "allow_write": [],
        "review": ["**"],
        "deny": [
            ".env",
            ".env.*",
            ".git/**",
            ".ssh/**",
            "**/*.key",
            "**/*.pem",
        ],
        "default": "review",
    },
    "process": {"allow": ["*"], "default": "allow"},
    "network": {"mode": "observe"},
    "limits": {},
    "rollback": {"enabled": True, "max_backup_file_mb": 25},
}

_POLICY_TEMPLATE = """# AgentDiff policy schema version 1
version: 1
filesystem:
  allow_write:
    - "src/**"
    - "tests/**"
  review:
    - "pyproject.toml"
    - "**/package.json"
  deny:
    - ".env"
    - ".env.*"
    - ".git/**"
    - ".ssh/**"
    - "**/*.key"
    - "**/*.pem"
  default: review
process:
  allow:
    - "python*"
    - "pytest"
    - "node"
    - "npm"
  default: review
network:
  # observe = machine-wide observation only; it does not block traffic
  mode: observe
limits:
  files_changed: 100
  files_deleted: 10
  processes_spawned: 32
  duration_seconds: 900
rollback:
  enabled: true
  max_backup_file_mb: 25
"""


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _load_runtime_policy(root: Path, requested: str | None) -> Policy:
    if requested is not None:
        return load_policy_file(requested)
    default_path = root / "agentdiff.yaml"
    if default_path.is_file() and not default_path.is_symlink():
        return load_policy_file(default_path)
    return load_policy(_DEFAULT_POLICY)


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Capture the legacy environment snapshot format."""

    engine = DiffEngine(
        watch_paths=[args.root] if args.root else None,
        ignore_patterns=args.ignore.split(",") if args.ignore else None,
        max_file_size_mb=args.max_size // (1024 * 1024) if args.max_size else 100,
        capture_env_vars=not args.no_env,
        capture_processes=not args.no_proc,
        capture_ports=not args.no_ports,
    )
    fs_snap, env_snap = engine.snapshot()
    snapshot_data = {
        "filesystem": fs_snap.to_dict(),
        "environment": env_snap.to_dict(),
        "timestamp": fs_snap.timestamp,
    }
    output = args.output or f"snapshot_{snapshot_data['timestamp']}.json"
    Path(output).write_text(_json(snapshot_data), encoding="utf-8")
    print(f"Snapshot saved to {safe_display(output)}")
    print(f"  Files: {len(fs_snap.file_hashes)}")
    print(f"  Dirs:  {len(fs_snap.directories)}")
    print(f"  Env vars: {len(env_snap.env_vars)}")
    print(f"  Processes: {len(env_snap.process_pids)}")
    print(f"  Ports: {len(env_snap.open_ports)}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Diff two legacy snapshots."""

    pre_data = json.loads(Path(args.pre).read_text(encoding="utf-8"))
    post_data = json.loads(Path(args.post).read_text(encoding="utf-8"))
    pre_fs = FilesystemSnapshot.from_dict(pre_data["filesystem"])
    pre_env = EnvironmentSnapshot.from_dict(pre_data["environment"])
    post_fs = FilesystemSnapshot.from_dict(post_data["filesystem"])
    post_env = EnvironmentSnapshot.from_dict(post_data["environment"])
    engine = DiffEngine(watch_paths=[args.root] if args.root else None)
    diff = engine.diff(pre_fs, post_fs, pre_env, post_env)

    if args.format == "json":
        print(_json(diff.to_dict()))
    else:
        summary = diff.summary
        print(
            f"Files: +{summary.get('file_created', 0)} "
            f"~{summary.get('file_modified', 0)} "
            f"-{summary.get('file_deleted', 0)}"
        )
        print(f"Dirs:  +{summary.get('dir_created', 0)} -{summary.get('dir_deleted', 0)}")
        print(
            f"Env:   +{summary.get('env_var_added', 0)} "
            f"~{summary.get('env_var_modified', 0)} "
            f"-{summary.get('env_var_removed', 0)}"
        )
        print(
            f"Procs: +{summary.get('process_spawned', 0)} -{summary.get('process_terminated', 0)}"
        )
        print(f"Ports: +{summary.get('port_opened', 0)} -{summary.get('port_closed', 0)}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    """Evaluate a trajectory file using the compatibility evaluator."""

    trajectory_data = json.loads(Path(args.trajectory).read_text(encoding="utf-8"))
    tracker = TrajectoryTracker(
        task_description=trajectory_data.get("task_description", ""),
        framework=AgentFramework(trajectory_data.get("framework", "custom")),
    )
    for step_data in trajectory_data.get("steps", []):
        tracker.start_step(thought=step_data.get("thought"))
        for tc_data in step_data.get("tool_calls", []):
            tracker.record_tool_call(
                name=tc_data.get("name", ""),
                arguments=tc_data.get("arguments", {}),
                result=tc_data.get("result"),
                error=tc_data.get("error"),
                duration_ms=tc_data.get("duration_ms", 0),
            )
        tracker.end_step(observation=step_data.get("observation"))
    trajectory = tracker.finish(
        final_result=trajectory_data.get("final_result"),
        final_error=trajectory_data.get("final_error"),
    )

    snapshots = None
    if args.pre and args.post:
        pre_data = json.loads(Path(args.pre).read_text(encoding="utf-8"))
        post_data = json.loads(Path(args.post).read_text(encoding="utf-8"))
        pre_snapshot = (
            FilesystemSnapshot.from_dict(pre_data["filesystem"]),
            EnvironmentSnapshot.from_dict(pre_data["environment"]),
        )
        post_snapshot = (
            FilesystemSnapshot.from_dict(post_data["filesystem"]),
            EnvironmentSnapshot.from_dict(post_data["environment"]),
        )
        snapshots = (pre_snapshot, post_snapshot)

    evaluator = AgentDiffEvaluator(
        target_paths=[args.root] if args.root else None,
        cleanliness_threshold=args.threshold,
    )
    target_root = Path(args.root or ".").resolve()
    targets = [
        str(path.resolve() if path.is_absolute() else (target_root / path).resolve())
        for target in (args.target.split(",") if args.target else [])
        if (path := Path(target))
    ]
    evaluator.set_target_mutations(targets)
    result = (
        evaluator.evaluate_from_snapshots(trajectory, *snapshots)
        if snapshots
        else evaluator.evaluate(trajectory)
    )

    if args.format == "json":
        print(result.to_json())
    else:
        print(f"Cleanliness: {result.metrics.cleanliness_score:.1%}")
        print(f"Efficiency:  {result.metrics.efficiency_score:.1%}")
        print(f"Passed:      {result.passed}")
        print(f"Side Effects: {len(result.side_effects)}")
        for effect in result.side_effects:
            print(f"  {effect.severity.value}: {safe_display(effect.description)}")
    return 1 if args.fail_below_threshold and not result.passed else 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run one command in an observed local transaction."""

    root = Path(args.root).expanduser().resolve(strict=True)
    command = list(args.argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("run requires a command after '--'")
    policy = _load_runtime_policy(root, args.policy)
    runtime = None
    if args.runtime == "srt":
        runtime = SandboxRuntime(
            root=root,
            executable=args.srt_executable,
            settings=args.srt_settings,
            observe_ports=policy.network.mode.value == "observe",
        )
    transaction = AgentRunTransaction(root=root, policy=policy, task=args.task, runtime=runtime)
    stream = sys.stderr if args.format == "json" else None
    result = transaction.run(
        command,
        timeout_seconds=args.timeout,
        stdout=stream,
        stderr=stream,
    )
    if args.format == "json":
        print(_json(result.to_dict()))
    else:
        expected = sum(change.decision.action is PolicyAction.ALLOW for change in result.changes)
        unexpected = sum(change.decision.action is PolicyAction.REVIEW for change in result.changes)
        protected = sum(change.decision.action is PolicyAction.DENY for change in result.changes)
        recovery_available = any(
            change.reversible and change.decision.action in {PolicyAction.REVIEW, PolicyAction.DENY}
            for change in result.changes
        )
        if result.status == "blocked":
            task_state = "Task blocked"
        elif result.status in {"error", "failed", "timed_out"}:
            task_state = "Task failed"
        else:
            task_state = "Task completed"
        print(task_state)
        print()
        print(f"Expected changes:   {expected}")
        print(f"Unexpected changes: {unexpected}")
        print(f"Protected changes:  {protected}")
        print()
        print(
            f"Blast Radius: {result.blast_radius.level.value.upper()} "
            f"({result.blast_radius.score}/100)"
        )
        print(f"Recovery available: {'YES' if recovery_available else 'NO'}")
        print(f"Policy outcome: {result.safety_outcome.value.upper()}")
        print()
        print(f"Run: {result.run_id}")
        print(f"Status: {result.status} ({result.safety_outcome.value})")
        if result.runtime is not None:
            print(f"Runtime: {result.runtime.backend} ({result.runtime.enforcement})")
        print(f"Mutations: {len(result.changes)}")
        for change in result.changes:
            print(
                f"  {change.decision.action.value:6} {change.change_type:8} "
                f"{safe_display(change.path)}"
            )
        if result.observation_warnings:
            print(f"Observation warnings: {len(result.observation_warnings)}")
        print(f"Inspect: agentdiff inspect {result.run_id} --root {safe_display(root)}")

    try:
        memory = AgentMemoryStore(root)
        card = ContextCompressor.compress_trajectory(
            task=args.task or "",
            run_id=result.run_id,
            mutations=result.to_dict().get("mutations", {}),
            policy_decision=result.safety_outcome.value,
            blast_radius=result.blast_radius.score,
            argv=command,
        )
        collateral = [
            c.path
            for c in result.changes
            if c.decision.action in {PolicyAction.REVIEW, PolicyAction.DENY}
        ]
        memory.record_episode(card, collateral_paths=collateral)
    except (OSError, ValueError, TypeError, KeyError):
        pass

    return result.recommended_exit_code(args.fail_on)


def cmd_skill_list(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    skills = SkillCardGenerator(root).list_skills()
    if args.format == "json":
        print(_json([s.to_dict() for s in skills]))
        return 0
    if not skills:
        print("No evidence skill cards found in .agentdiff/skills/")
        return 0
    print(f"AgentDiff Evidence Skill Cards ({len(skills)} found):")
    for s in skills:
        print(f"  • {s.skill_id:24} {safe_display(s.title)}")
    return 0


def cmd_skill_generate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    inspector = RunInspector(root, args.run_id)
    summary_dict = inspector.summary().to_dict()
    generator = SkillCardGenerator(root)
    skill = generator.generate(summary_dict, title=args.title, save=True)
    if args.format == "json":
        print(_json(skill.to_dict()))
    else:
        print(f"Generated skill card: {skill.skill_id}")
        print(f"Title: {safe_display(skill.title)}")
        print(f"Triggers: {', '.join(skill.triggers)}")
        print(f"Verification Recipe: {skill.verification_recipe}")
        print(f"Saved to: .agentdiff/skills/{skill.skill_id}.md")
    return 0


def cmd_context_pack(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    pack = ContextPacker.pack(args.task, root)
    if args.format == "json":
        print(_json({"task": args.task, "context_pack": pack}))
    else:
        print(pack)
    return 0


def cmd_memory_stats(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    stats = AgentMemoryStore(root).get_stats()
    if args.format == "json":
        print(_json(stats))
    else:
        print("AgentDiff Trajectory Memory Stats")
        print(f"  Total episodes recorded: {stats['total_episodes']}")
        print(f"  Fragile paths tracked:   {stats['fragile_paths_tracked']}")
        if stats["top_fragile_paths"]:
            print("  Top Fragile Paths:")
            for path, score in stats["top_fragile_paths"]:
                print(f"    - {path} (Risk score: {score})")
    return 0


def cmd_memory_search(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    store = AgentMemoryStore(root)
    query_embedding = None
    if args.embedding_model:
        embedder = OllamaEmbeddingProvider(
            model=args.embedding_model,
            endpoint=args.embedding_endpoint,
            timeout_seconds=args.timeout,
        )
        vectors = embedder.embed([args.query])
        query_embedding = vectors[0] if vectors else None
    hits = store.search(args.query, limit=args.limit, query_embedding=query_embedding)
    if args.format == "json":
        print(_json([hit.to_dict() for hit in hits]))
        return 0
    if not hits:
        print("No trajectory memory found.")
        return 0
    print(f"AgentDiff Memory Matches ({len(hits)})")
    for hit in hits:
        card = hit.card
        print(f"  {hit.score:.3f}  {card.outcome:7}  {safe_display(card.task)}")
        if card.modified_symbols_or_files:
            paths = ", ".join(safe_display(item) for item in card.modified_symbols_or_files[:4])
            print(f"           Paths: {paths}")
    return 0


def cmd_memory_index(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    embedder = OllamaEmbeddingProvider(
        model=args.model,
        endpoint=args.endpoint,
        timeout_seconds=args.timeout,
    )
    indexed = AgentMemoryStore(root).index_embeddings(embedder, batch_size=args.batch_size)
    if args.format == "json":
        print(_json({"indexed": indexed, "provider": embedder.name, "model": embedder.model}))
    else:
        print(f"Indexed {indexed} evidence episodes with {embedder.name}:{embedder.model}")
    return 0


def cmd_agent_ask(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    provider = create_provider(
        args.provider,
        model=args.model,
        api_key_env=args.api_key_env,
        endpoint=args.endpoint,
        executable=args.executable,
        timeout_seconds=args.timeout,
    )
    embedder = None
    if args.embedding_model:
        embedder = OllamaEmbeddingProvider(
            model=args.embedding_model,
            endpoint=args.embedding_endpoint,
            timeout_seconds=args.timeout,
        )
    memory = None
    if not args.no_memory:
        memory = RepositoryMemoryProvider(
            root,
            max_memories=args.max_memories,
            embedder=embedder,
        )
    router = CortexRouter(provider, memory=memory, root=root)
    try:
        result = router.ask(args.task, previous_response_id=args.previous_response_id)
    finally:
        router.shutdown()
    if args.format == "json":
        print(_json(result.to_dict()))
    else:
        print(result.response.text)
    return 0


def cmd_advise(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    inspector = RunInspector(root, args.run_id)
    payload = RemediationAdvisor.generate_remediation(inspector.summary().to_dict())
    if args.format == "json":
        print(_json(payload))
    else:
        print(f"Remediation Status: {payload['status']}")
        print(
            f"Decision: {payload['decision']} (Blast Radius: {payload['blast_radius_score']}/100)"
        )
        if payload["collateral_files_to_revert"]:
            print(f"Collateral to Revert: {', '.join(payload['collateral_files_to_revert'])}")
        print(f"Recovery Command: {payload['recovery_command']}")
        print(f"Prompt Directive: {payload['prompt_repair_directive']}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    inspector = RunInspector(args.root, args.run_id)
    if args.format == "json":
        print(_json(inspector.inspect()))
        return 0
    summary = inspector.summary()
    print(f"Run: {summary.run_id}")
    print(f"Created: {safe_display(summary.created_at)}")
    print(f"Task: {safe_display(summary.task or '-')}")
    print(f"Status: {summary.status} ({summary.safety_outcome})")
    print(f"Blast radius: {summary.blast_radius}/100")
    print(f"Return code: {summary.returncode}")
    integrity = "unsealed" if summary.integrity_ok is None else str(summary.integrity_ok).lower()
    print(f"Capsule integrity: {integrity}")
    print(f"Command: {' '.join(safe_display(item) for item in summary.command)}")
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    summaries = list_runs(args.root, limit=args.limit)
    if args.format == "json":
        print(_json([summary.to_dict() for summary in summaries]))
        return 0
    if not summaries:
        print("No AgentDiff runs found.")
        return 0
    for summary in summaries:
        print(
            f"{summary.run_id}  {summary.status:9}  "
            f"blast={summary.blast_radius:3}/100  {safe_display(summary.task or '-')}"
        )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify the immutable checksum manifest for one run capsule."""

    report = RunStore.open(args.root, args.run_id).verify_integrity()
    if args.format == "json":
        print(_json(report.to_dict()))
    else:
        state = "valid" if report.ok else "INVALID"
        print(f"Capsule integrity: {state}")
        print(f"Files checked: {report.files_checked}")
        for issue in report.issues:
            print(f"  {safe_display(issue.path)}: {safe_display(issue.reason)}")
    return 0 if report.ok else 6


def cmd_rollback(args: argparse.Namespace) -> int:
    report = RollbackEngine.open(args.root, args.run_id).rollback(
        safe_only=args.safe_only,
        all_changes=args.all_changes,
        paths=args.path,
    )
    if args.format == "json":
        print(_json(report.to_dict()))
    else:
        print(f"Rollback run: {report.run_id}")
        print(f"Actions: {len(report.actions)}")
        for action in report.actions:
            print(f"  {action.action:8} {safe_display(action.path)}")
        print(f"Conflicts: {len(report.conflicts)}")
        for conflict in report.conflicts:
            print(f"  {safe_display(conflict.path)}: {safe_display(conflict.reason)}")
        print(f"Skipped: {len(report.skipped)}")
    return 4 if report.conflicts else 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    report = RunInspector(args.root, args.run_id).cleanup(grace_period_seconds=args.grace_period)
    if args.format == "json":
        print(_json(report.to_dict()))
    else:
        print(f"Cleanup identities signaled: {report.targeted}")
        for outcome in report.outcomes:
            print(
                f"  pid={outcome.process.pid} create_time={outcome.process.create_time} "
                f"{outcome.action}"
            )
    return 5 if any(outcome.action == "access_denied" for outcome in report.outcomes) else 0


def cmd_doctor(args: argparse.Namespace) -> int:
    report = doctor_report()
    if args.format == "json":
        print(_json(report))
    else:
        print("AgentDiff local runtime capabilities")
        for key, value in report.items():
            print(f"  {key}: {safe_display(value)}")
    return 0


def cmd_policy_init(args: argparse.Namespace) -> int:
    destination = Path(args.output)
    if destination.exists() and not args.force:
        raise FileExistsError(f"policy already exists: {destination}")
    destination.write_text(_POLICY_TEMPLATE, encoding="utf-8")
    print(f"Policy written to {safe_display(destination)}")
    return 0


def cmd_policy_validate(args: argparse.Namespace) -> int:
    policy = load_policy_file(args.policy)
    print(f"Policy is valid schema version {policy.version}: {safe_display(args.policy)}")
    return 0


def cmd_policy_explain(args: argparse.Namespace) -> int:
    decision = PolicyEngine(load_policy_file(args.policy)).decide_path(args.path)
    if args.format == "json":
        print(_json(decision.to_dict()))
    else:
        print(f"Path: {safe_display(decision.subject)}")
        print(f"Decision: {decision.action.value}")
        print(f"Rule: {decision.rule}")
        print(f"Reason: {safe_display(decision.reason)}")
    return 0


# ---------------------------------------------------------------------------
# Zero-touch automation layer: bootstrap / prove / promote / repair / wrap
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """Bootstrap the canonical trust configuration (zero-touch entry point).

    ``init`` is idempotent: an existing configuration is recompiled in place.
    """
    root = Path(args.root).resolve()
    compiler = TrustCompiler(root, write_agents=args.agents)
    report = compiler.compile(force=True)
    print(f"Trust configuration compiled for {safe_display(root)}")
    print(f"  Primary language: {report.primary_language}")
    print(f"  Package manager:  {report.package_manager or '-'}")
    print(f"  Test tooling:     {', '.join(report.test_tools) or '-'}")
    for path in report.written:
        print(f"  wrote {safe_display(path)}")
    if args.daemon:
        ensure_sidecar(root)
        print(f"Sidecar started for {safe_display(root)}")
    print("Next: run your agent through AgentDiff, e.g.")
    print('  agentdiff wrap -- codex exec "your task"')
    print('or alias it:  alias codex="agentdiff wrap -- codex"')
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Compile repository trust configuration from deterministic inspection."""
    root = Path(args.root).resolve()
    compiler = TrustCompiler(root, write_agents=args.agents)
    try:
        report = compiler.compile(force=args.force, dry_run=args.dry_run)
    except FileExistsError as error:
        print(f"agentdiff: {safe_display(error)}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(_json(report.to_dict()))
        return 0
    print(f"Trust configuration compiled for {safe_display(root)}")
    print(f"  Primary language: {report.primary_language}")
    print(f"  Package manager:  {report.package_manager or '-'}")
    print(f"  Policy digest:    {report.policy_sha256}")
    print(f"  Graph digest:     {report.graph_sha256}")
    print(f"  Proof plan digest:{report.proof_plan_sha256}")
    for path in report.written:
        print(f"  wrote {safe_display(path)}")
    return 0


def cmd_prove(args: argparse.Namespace) -> int:
    """Run deterministic clean-room proof for a sealed run capsule."""
    root = Path(args.root).resolve()
    cache = ProofCache(root) if not args.no_cache else None
    target = args.target or "full"
    proof = ProofEngine(root, args.run_id, cache=cache, target=target).prove(
        timeout_seconds=args.timeout
    )
    if args.format == "json":
        print(_json(proof.to_dict()))
    else:
        verdict = proof.verdict.value
        print(f"Proof verdict: {verdict}")
        print(f"Promotion:     {proof.promotion}")
        print(f"Agent run:     {proof.agent_run}")
        print(f"Policy:        {proof.policy}")
        print(f"Clean room:    {proof.clean_environment}")
        print(
            "Blast radius:  "
            f"immediate={proof.immediate_blast_radius} "
            f"future={proof.future_blast_radius}"
        )
        print(f"Patch digest:  {proof.patch_digest}")
        print(f"Verification:  {proof.verification_source} ({proof.verification_digest})")
        if proof.cache_hit:
            print(f"Cache:         HIT (from run {proof.cached_from_run})")
        for phase in proof.phases:
            print(
                f"  {phase.phase:16} {phase.status} rc={phase.returncode} "
                f"{phase.duration_seconds:.1f}s tests={phase.tests_passed}/{phase.tests_total}"
            )
        for reason in proof.reasons:
            print(f"  reason: {safe_display(reason)}")
    return 0 if proof.verdict is ProofVerdict.PROVEN else 7


def cmd_promote(args: argparse.Namespace) -> int:
    """Promote a proven patch to the host repository with conflict checks."""
    root = Path(args.root).resolve()
    engine = PromotionEngine(
        root,
        args.run_id,
        store_root=Path(args.store_root).resolve() if args.store_root else None,
    )
    report = engine.promote(
        dry_run=args.dry_run,
        safe_only=args.safe_only,
        paths=args.path,
    )
    if args.format == "json":
        print(_json(report.to_dict()))
    else:
        print(f"Promotion: {report.status}")
        print(f"Patch digest: {report.patch_digest}")
        for action in report.actions:
            print(f"  {action.action:12} {safe_display(action.path)}")
        for conflict in report.conflicts:
            print(f"  CONFLICT {safe_display(conflict.path)}: {safe_display(conflict.reason)}")
        for path in report.skipped:
            print(f"  skipped  {safe_display(path)}")
    return 0 if report.status in {"PROMOTED", "DRY_RUN_SAFE"} else 8


def cmd_repair(args: argparse.Namespace) -> int:
    """Run verified automatic repair until proof passes or scope changes."""
    root = Path(args.root).resolve()
    policy = None
    if args.policy:
        policy = load_policy_file(args.policy)
    loop = RepairLoop(
        root,
        args.run_id,
        policy=policy,
        max_attempts=args.max_attempts,
        max_runtime_seconds=args.max_runtime,
        cache=ProofCache(root) if not args.no_cache else None,
        repair_command_builder=(None if args.no_agent else _agent_repair_builder(args)),
    )
    outcome = loop.run()
    if args.format == "json":
        print(_json(outcome.to_dict()))
    else:
        print(f"Repair outcome: {outcome.status}")
        if outcome.human_reason:
            print(f"Human reason:   {safe_display(outcome.human_reason)}")
        for attempt in outcome.attempts:
            print(f"  attempt {attempt.attempt} run={attempt.run_id} verdict={attempt.verdict}")
    return {
        "REPAIRED": 0,
        "FAILED": 9,
        "NEEDS_HUMAN": 10,
        "NEEDS_AGENT": 11,
        "BLOCKED": 12,
    }[outcome.status]


def _agent_repair_builder(args: argparse.Namespace):
    """Re-invoke the same agent CLI for bounded repair attempts."""
    from agentdiff.repair import default_repair_command_builder

    if args.agent_argv:
        return default_repair_command_builder(list(args.agent_argv))
    metadata = RunStore.open(Path(args.root).resolve(), args.run_id).read_json("metadata.json")
    original = list(metadata.get("command", []))
    if original:
        return default_repair_command_builder(original)
    return None


def cmd_wrap(args: argparse.Namespace) -> int:
    """Run one agent command through the zero-touch pipeline."""
    root = Path(args.root).resolve()
    command = list(args.argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("wrap requires a command after '--'")
    runner = WrapRunner(
        root,
        policy_file=args.policy,
        enable_proof=not args.no_proof,
        enable_repair=not args.no_repair,
        enable_promote=not args.no_promote,
        max_attempts=args.max_attempts,
        max_repair_runtime=args.max_repair_runtime,
        use_cache=not args.no_cache,
        notify=not args.quiet,
        session_id=args.session,
    )
    summary = runner.wrap(command, task=args.task or "")
    if args.format == "json":
        print(_json(summary.to_dict()))
    else:
        print(f"Wrap status:    {summary.status}")
        print(f"Routing:        {summary.routing}")
        print(f"Run:            {summary.run_id}")
        if summary.proof_verdict:
            print(f"Proof:          {summary.proof_verdict}")
        if summary.repair_outcome:
            print(f"Repair:         {summary.repair_outcome}")
        if summary.promotion_status:
            print(f"Promotion:      {summary.promotion_status}")
        if summary.human_reason:
            print(f"Human reason:   {safe_display(summary.human_reason)}")
    return 0 if summary.routing in {"AUTO", "RETRY"} else 1


# ---------------------------------------------------------------------------
# Sidecar daemon commands
# ---------------------------------------------------------------------------


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the local AgentDiff sidecar daemon."""
    from agentdiff.sidecar.server import serve

    serve(args.root, port=args.port, foreground=not args.daemon)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show the sidecar status."""
    root = Path(args.root).resolve()
    try:
        client = SidecarClient(root)
        status = client.status()
    except SidecarError as error:
        print(f"agentdiff: sidecar not running: {safe_display(error)}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(_json(status))
    else:
        print(f"Sidecar: running (pid={status['pid']})")
        print(f"Root:    {safe_display(status['root'])}")
        print(f"Version: {status['version']}")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop the local AgentDiff sidecar daemon."""
    root = Path(args.root).resolve()
    try:
        client = SidecarClient(root)
        client.request("POST", "/v1/stop")
    except SidecarError as error:
        print(f"agentdiff: {safe_display(error)}", file=sys.stderr)
        return 1
    print("Sidecar stopped.")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Send one lifecycle/tool event to the sidecar (agent adapters)."""
    root = Path(args.root).resolve()
    client = ensure_sidecar(root)
    data = json.loads(args.data) if args.data else {}
    if args.event == "session-begin":
        response = client.session_begin(task=args.task or "", agent=data.get("agent", ""))
    elif args.event == "tool-call":
        response = client.session_event(
            session_id=args.session_id or "",
            event_type="tool_call",
            data=data,
        )
    elif args.event == "session-end":
        response = client.session_end(session_id=args.session_id or "")
    else:
        raise ValueError(f"unknown hook event: {args.event}")
    if args.format == "json":
        print(_json(response))
    return 0


# ---------------------------------------------------------------------------
# Trust, impact, and workspace commands
# ---------------------------------------------------------------------------


def cmd_trust_graph(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    graph = RepoImpactGraph.from_inspection(root)
    if args.format == "json":
        print(_json(graph.serialize()))
    else:
        serialized = graph.serialize()
        print(f"Impact graph for {safe_display(root)}")
        print(f"  nodes: {len(serialized['nodes'])}")
        print(f"  edges: {len(serialized['edges'])}")
    return 0


def cmd_trust_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    lock_path = root / ".agentdiff" / "trust.lock"
    if not lock_path.is_file():
        print("No trust lock found. Run `agentdiff bootstrap` first.")
        return 1
    lock = _json(json.loads(lock_path.read_text(encoding="utf-8")))
    if args.format == "json":
        print(lock)
    else:
        print(f"Trust lock: {safe_display(lock_path)}")
        print(lock)
    return 0


def cmd_impact(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    changed = [path.strip() for path in args.paths.split(",") if path.strip()] if args.paths else []
    if not changed:
        raise ValueError("impact requires --paths (comma-separated relative paths)")
    graph = RepoImpactGraph.from_inspection(root)
    proof_plan = {}
    plan_path = root / ".agentdiff" / "proof-plan.json"
    if plan_path.is_file():
        proof_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    impact = ImpactEngine(root, graph=graph, proof_plan=proof_plan).plan(changed)
    if args.format == "json":
        print(_json(impact.to_dict()))
    else:
        print(f"Impact level: {impact.level}")
        print(f"Triggers:     {', '.join(impact.triggers) or '-'}")
        print(f"Modules:      {', '.join(impact.modules) or '-'}")
        print(f"Tests:        {', '.join(impact.tests) or '-'}")
        print(f"Targets:      {', '.join(impact.build_targets) or '-'}")
        for command in impact.test_commands:
            print(f"  test: {' '.join(command)}")
    return 0


def cmd_proof_cache_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    stats = ProofCache(root).stats()
    if args.format == "json":
        print(_json(stats))
    else:
        print(f"Proof cache entries: {stats['count']}")
        for entry in stats["entries"]:
            print(
                f"  {entry['key_digest'][:12]} {entry['verdict']:10} "
                f"target={entry['target']} run={entry['cached_from_run']}"
            )
    return 0


def cmd_workspace_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    stats = WarmWorkspaceFactory(root).stats()
    if args.format == "json":
        print(_json(stats))
    else:
        print(f"Warm base snapshots: {stats['count']}")
        for base in stats["bases"]:
            print(
                f"  {base['identity_digest'][:12]} files={base['files']} "
                f"strategy={base['materialization']['strategy']}"
            )
    return 0


def cmd_workspace_warm(args: argparse.Namespace) -> int:
    """Materialize the trusted warm base for the current repository identity."""
    root = Path(args.root).resolve()
    policy = _load_runtime_policy(root, args.policy)
    factory = WarmWorkspaceFactory(root)
    identity = compute_identity(root, policy=policy)
    base = factory.ensure_base(identity)
    ok, reason = factory.verify_base(identity)
    if args.format == "json":
        print(
            _json(
                {
                    "identity": identity.to_dict(),
                    "identity_digest": identity.digest(),
                    "base": str(base.path),
                    "verified": ok,
                    "reason": reason,
                }
            )
        )
    else:
        print(f"Workspace identity: {identity.digest()}")
        print(f"Base snapshot:      {safe_display(base.path)}")
        print(f"Verified:           {ok} ({reason})")
    return 0 if ok else 1


def cmd_workspace_prune(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    factory = WarmWorkspaceFactory(root, max_bases=args.keep)
    removed = factory.prune()
    print(f"Removed {removed} stale warm base snapshot(s).")
    return 0


def cmd_api_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    providers = get_providers_for_selection(args.provider)
    scanner = APIScanner(providers=providers)
    usages = scanner.scan(root)
    sdk_versions = detect_installed_sdk_versions(root)

    if args.format == "json":
        print(
            _json(
                {
                    "root": str(root),
                    "provider": args.provider,
                    "count": len(usages),
                    "detected_sdk_versions": {k: v.to_dict() for k, v in sdk_versions.items()},
                    "usages": [u.to_dict() for u in usages],
                }
            )
        )
    else:
        print(f"External API Scan: {safe_display(root)}")
        print(f"Provider filter:   {args.provider}")
        if sdk_versions:
            sdk_summary = ", ".join(
                f"{k} ({v.version_specifier or v.exact_version or 'detected'} from {v.source_file})"
                for k, v in sorted(sdk_versions.items())
            )
            print(f"Detected SDKs:     {sdk_summary}")
        print(f"Total API usages:  {len(usages)}")
        if usages:
            print("")
            for u in usages:
                print(f"  {u.filepath}:{u.line_number} [{u.provider}] {u.symbol} ({u.call_type})")
                if u.code_snippet:
                    print(f"    {u.code_snippet}")
        else:
            print("  No external API usages found.")
    return 0


def cmd_api_check(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    providers = get_providers_for_selection(args.provider)
    scanner = APIScanner(providers=providers)
    usages = scanner.scan(root)

    matcher = APIMatcher(providers=providers)
    impact = matcher.calculate_impact(usages, root=root)

    if args.format == "json":
        print(_json(impact.to_dict()))
    else:
        print(f"External API Breaking Change Check: {safe_display(root)}")
        print(f"Provider filter:   {args.provider}")
        if impact.detected_sdk_versions:
            items = []
            for k, v in sorted(impact.detected_sdk_versions.items()):
                spec = v.get("version_specifier") or v.get("exact_version") or "detected"
                src = v.get("source_file", "manifest")
                items.append(f"{k} ({spec} from {src})")
            print(f"Detected SDKs:     {', '.join(items)}")
        print(f"Total usages:      {impact.total_usages}")
        print(f"Affected usages:   {impact.affected_usages}")
        print(f"Affected files:    {len(impact.affected_files)}")
        print(
            f"Risk level:        {impact.risk_level.value.upper()} "
            f"(Blast Radius Score: {impact.blast_radius.score}/100)"
        )

        if impact.impact_error:
            print(f"Warning:           {impact.impact_error}")
        elif impact.impact_plan is not None:
            print(f"Proof Level:       {impact.impact_plan.level.upper()}")
            if impact.impact_plan.tests:
                print(f"Impacted tests:    {len(impact.impact_plan.tests)}")

        if impact.matched_changes:
            print("\nBreaking Changes & Deprecations Detected:")
            for mc in impact.matched_changes:
                loc = f"{mc.usage.filepath}:{mc.usage.line_number}"
                print(f"\n  [{mc.change.severity.value.upper()}] {loc} -> {mc.change.title}")
                print(f"    Symbol:      {mc.usage.symbol}")
                if mc.change.replacement_symbol:
                    print(f"    Migrate to:  {mc.change.replacement_symbol}")
                if mc.change.migration_guide_url:
                    print(f"    Docs:        {mc.change.migration_guide_url}")
                if mc.change.replacement_code:
                    code_indent = "\n      ".join(mc.change.replacement_code.splitlines())
                    print(f"    Example:\n      {code_indent}")
        else:
            print("\n  All detected API usages are up-to-date. No breaking changes detected.")

    fail_on = getattr(args, "fail_on", "high")
    if fail_on == "never":
        return 0
    if fail_on == "any" and impact.affected_usages > 0:
        return 1
    if fail_on == "high" and (
        impact.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
        or any(
            m.change.severity in {ChangeSeverity.HIGH, ChangeSeverity.CRITICAL}
            for m in impact.matched_changes
        )
    ):
        return 1
    if fail_on == "critical" and (
        impact.risk_level == RiskLevel.CRITICAL
        or any(m.change.severity == ChangeSeverity.CRITICAL for m in impact.matched_changes)
    ):
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentdiff",
        description="Observe, govern, score, and recover local AI-agent mutations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_run = subparsers.add_parser("run", help="Run a command in a local observed transaction")
    p_run.add_argument("--root", default=".", help="Project root")
    p_run.add_argument(
        "--policy", help="Policy YAML/JSON (default: ROOT/agentdiff.yaml if present)"
    )
    p_run.add_argument("--task", help="Human-readable intended task")
    p_run.add_argument("--timeout", type=float, help="Maximum runtime in seconds")
    p_run.add_argument(
        "--runtime",
        choices=["local", "srt"],
        default="local",
        help="local observation or external Anthropic Sandbox Runtime delegation",
    )
    p_run.add_argument(
        "--srt-executable",
        default="srt",
        help="Sandbox Runtime executable used with --runtime srt",
    )
    p_run.add_argument(
        "--srt-settings",
        help="Sandbox Runtime settings JSON used with --runtime srt",
    )
    p_run.add_argument("--format", choices=["json", "summary"], default="summary")
    p_run.add_argument("--fail-on", choices=["never", "review", "deny"], default="deny")
    p_run.add_argument("argv", nargs=argparse.REMAINDER, help="Command argv after --")
    p_run.set_defaults(func=cmd_run)

    p_inspect = subparsers.add_parser("inspect", help="Inspect one durable run capsule")
    p_inspect.add_argument("run_id")
    p_inspect.add_argument("--root", default=".")
    p_inspect.add_argument("--format", choices=["json", "summary"], default="summary")
    p_inspect.set_defaults(func=cmd_inspect)

    p_runs = subparsers.add_parser("runs", help="List durable run capsules")
    p_runs.add_argument("--root", default=".")
    p_runs.add_argument("--limit", type=int)
    p_runs.add_argument("--format", choices=["json", "summary"], default="summary")
    p_runs.set_defaults(func=cmd_runs)

    p_verify = subparsers.add_parser("verify", help="Verify a run capsule checksum manifest")
    p_verify.add_argument("run_id")
    p_verify.add_argument("--root", default=".")
    p_verify.add_argument("--format", choices=["json", "summary"], default="summary")
    p_verify.set_defaults(func=cmd_verify)

    p_rollback = subparsers.add_parser("rollback", help="Conflict-check and recover run changes")
    p_rollback.add_argument("run_id")
    p_rollback.add_argument("--root", default=".")
    selection = p_rollback.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--safe-only",
        action="store_true",
        help="Revert only review/deny changes and preserve allowed work",
    )
    selection.add_argument("--all", dest="all_changes", action="store_true")
    p_rollback.add_argument("--path", action="append", help="Limit recovery to a relative path")
    p_rollback.add_argument("--format", choices=["json", "summary"], default="summary")
    p_rollback.set_defaults(func=cmd_rollback)

    p_cleanup = subparsers.add_parser("cleanup", help="Clean stored PID/create-time identities")
    p_cleanup.add_argument("run_id")
    p_cleanup.add_argument("--root", default=".")
    p_cleanup.add_argument("--grace-period", type=float, default=1.0)
    p_cleanup.add_argument("--format", choices=["json", "summary"], default="summary")
    p_cleanup.set_defaults(func=cmd_cleanup)

    p_doctor = subparsers.add_parser("doctor", help="Report implemented runtime capabilities")
    p_doctor.add_argument("--format", choices=["json", "summary"], default="summary")
    p_doctor.set_defaults(func=cmd_doctor)

    p_policy = subparsers.add_parser("policy", help="Initialize, validate, or explain policies")
    policy_commands = p_policy.add_subparsers(dest="policy_command", required=True)
    p_policy_init = policy_commands.add_parser("init", help="Write a conservative policy template")
    p_policy_init.add_argument("--output", default="agentdiff.yaml")
    p_policy_init.add_argument("--force", action="store_true")
    p_policy_init.set_defaults(func=cmd_policy_init)
    p_policy_validate = policy_commands.add_parser("validate", help="Validate a policy file")
    p_policy_validate.add_argument("--policy", default="agentdiff.yaml")
    p_policy_validate.set_defaults(func=cmd_policy_validate)
    p_policy_explain = policy_commands.add_parser("explain", help="Explain a path decision")
    p_policy_explain.add_argument("path")
    p_policy_explain.add_argument("--policy", default="agentdiff.yaml")
    p_policy_explain.add_argument("--format", choices=["json", "summary"], default="summary")
    p_policy_explain.set_defaults(func=cmd_policy_explain)

    p_cortex = subparsers.add_parser(
        "cortex",
        help="Experimental evidence memory, skill cards, and AI provider tools",
    )
    cortex_commands = p_cortex.add_subparsers(dest="cortex_command", required=True)

    p_skill = cortex_commands.add_parser("skill", help="Manage evidence-backed skill cards")
    skill_commands = p_skill.add_subparsers(dest="skill_command", required=True)
    p_skill_list = skill_commands.add_parser(
        "list", help="List generated skill cards in .agentdiff/skills/"
    )
    p_skill_list.add_argument("--root", default=".")
    p_skill_list.add_argument("--format", choices=["json", "summary"], default="summary")
    p_skill_list.set_defaults(func=cmd_skill_list)
    p_skill_gen = skill_commands.add_parser(
        "generate", help="Generate a reusable SKILL.md from verified run evidence"
    )
    p_skill_gen.add_argument("run_id")
    p_skill_gen.add_argument("--title", help="Custom title for the generated skill card")
    p_skill_gen.add_argument("--root", default=".")
    p_skill_gen.add_argument("--format", choices=["json", "summary"], default="summary")
    p_skill_gen.set_defaults(func=cmd_skill_generate)

    p_context = cortex_commands.add_parser(
        "context", help="Generate bounded evidence context packs for AI models"
    )
    context_commands = p_context.add_subparsers(dest="context_command", required=True)
    p_context_pack = context_commands.add_parser(
        "pack", help="Pack skill cards and evidence memory into prompt context"
    )
    p_context_pack.add_argument(
        "--task", required=True, help="Task prompt intent to pack context for"
    )
    p_context_pack.add_argument("--root", default=".")
    p_context_pack.add_argument("--format", choices=["json", "summary"], default="summary")
    p_context_pack.set_defaults(func=cmd_context_pack)

    p_memory = cortex_commands.add_parser(
        "memory", help="Inspect verified trajectory memory and code fragility"
    )
    memory_commands = p_memory.add_subparsers(dest="memory_command", required=True)
    p_memory_stats = memory_commands.add_parser(
        "stats", help="Display memory statistics and fragile paths"
    )
    p_memory_stats.add_argument("--root", default=".")
    p_memory_stats.add_argument("--format", choices=["json", "summary"], default="summary")
    p_memory_stats.set_defaults(func=cmd_memory_stats)
    p_memory_search = memory_commands.add_parser(
        "search", help="Search verified trajectory memory by task, path, and optional vectors"
    )
    p_memory_search.add_argument("query")
    p_memory_search.add_argument("--root", default=".")
    p_memory_search.add_argument("--limit", type=int, default=5)
    p_memory_search.add_argument("--embedding-model")
    p_memory_search.add_argument("--embedding-endpoint", default="http://127.0.0.1:11434/api/embed")
    p_memory_search.add_argument("--timeout", type=float, default=120.0)
    p_memory_search.add_argument("--format", choices=["json", "summary"], default="summary")
    p_memory_search.set_defaults(func=cmd_memory_search)
    p_memory_index = memory_commands.add_parser(
        "index", help="Build semantic memory vectors with a local Ollama embedding model"
    )
    p_memory_index.add_argument("--root", default=".")
    p_memory_index.add_argument("--model", default="embeddinggemma")
    p_memory_index.add_argument("--endpoint", default="http://127.0.0.1:11434/api/embed")
    p_memory_index.add_argument("--batch-size", type=int, default=32)
    p_memory_index.add_argument("--timeout", type=float, default=120.0)
    p_memory_index.add_argument("--format", choices=["json", "summary"], default="summary")
    p_memory_index.set_defaults(func=cmd_memory_index)

    p_agent = cortex_commands.add_parser(
        "agent", help="Route a memory-aware request to Claude, Codex/OpenAI, or Ollama"
    )
    agent_commands = p_agent.add_subparsers(dest="agent_command", required=True)
    p_agent_ask = agent_commands.add_parser(
        "ask", help="Ask one provider with bounded repository evidence context"
    )
    p_agent_ask.add_argument("--task", required=True)
    p_agent_ask.add_argument("--provider", choices=PROVIDER_NAMES, required=True)
    p_agent_ask.add_argument("--model")
    p_agent_ask.add_argument("--root", default=".")
    p_agent_ask.add_argument("--api-key-env")
    p_agent_ask.add_argument("--endpoint")
    p_agent_ask.add_argument("--executable")
    p_agent_ask.add_argument("--previous-response-id")
    p_agent_ask.add_argument("--no-memory", action="store_true")
    p_agent_ask.add_argument("--max-memories", type=int, default=4)
    p_agent_ask.add_argument("--embedding-model")
    p_agent_ask.add_argument("--embedding-endpoint", default="http://127.0.0.1:11434/api/embed")
    p_agent_ask.add_argument("--timeout", type=float, default=300.0)
    p_agent_ask.add_argument("--format", choices=["json", "summary"], default="summary")
    p_agent_ask.set_defaults(func=cmd_agent_ask)

    p_advise = cortex_commands.add_parser(
        "advise", help="Generate structured remediation advice without executing it"
    )
    p_advise.add_argument("run_id", help="Run ID to generate remediation advice for")
    p_advise.add_argument("--root", default=".")
    p_advise.add_argument("--format", choices=["json", "summary"], default="summary")
    p_advise.set_defaults(func=cmd_advise)

    # --- zero-touch automation layer ----------------------------------------

    p_init = subparsers.add_parser(
        "init", help="Bootstrap trust configuration (zero-touch entry point)"
    )
    p_init.add_argument("--root", default=".")
    p_init.add_argument(
        "--agents", action="store_true", help="append the trust pointer to AGENTS.md"
    )
    p_init.add_argument("--daemon", action="store_true", help="start the sidecar daemon afterwards")
    p_init.set_defaults(func=cmd_init)

    p_bootstrap = subparsers.add_parser(
        "bootstrap", help="Compile canonical trust configuration from repository inspection"
    )
    p_bootstrap.add_argument("--root", default=".")
    p_bootstrap.add_argument("--force", action="store_true")
    p_bootstrap.add_argument("--dry-run", action="store_true")
    p_bootstrap.add_argument("--agents", action="store_true")
    p_bootstrap.add_argument("--format", choices=["json", "summary"], default="summary")
    p_bootstrap.set_defaults(func=cmd_bootstrap)

    p_prove = subparsers.add_parser(
        "prove", help="Run deterministic clean-room proof for a sealed run"
    )
    p_prove.add_argument("run_id")
    p_prove.add_argument("--root", default=".")
    p_prove.add_argument("--timeout", type=float, default=900.0)
    p_prove.add_argument("--target", choices=["static", "targeted", "full"], default=None)
    p_prove.add_argument("--no-cache", action="store_true")
    p_prove.add_argument("--format", choices=["json", "summary"], default="summary")
    p_prove.set_defaults(func=cmd_prove)

    p_promote = subparsers.add_parser(
        "promote", help="Promote a proven patch to the host repository"
    )
    p_promote.add_argument("run_id")
    p_promote.add_argument("--root", default=".")
    p_promote.add_argument("--store-root", help="Capsule root when the run lives in a workspace")
    p_promote.add_argument("--dry-run", action="store_true")
    p_promote.add_argument("--safe-only", action="store_true")
    p_promote.add_argument("--path", action="append", help="Explicit REVIEW path selection")
    p_promote.add_argument("--format", choices=["json", "summary"], default="summary")
    p_promote.set_defaults(func=cmd_promote)

    p_repair = subparsers.add_parser(
        "repair", help="Run verified automatic repair until proof passes or scope changes"
    )
    p_repair.add_argument("run_id")
    p_repair.add_argument("--root", default=".")
    p_repair.add_argument("--policy", help="Policy file to hold fixed during repair")
    p_repair.add_argument("--max-attempts", type=int, default=2)
    p_repair.add_argument("--max-runtime", type=float, default=1800.0)
    p_repair.add_argument("--no-cache", action="store_true")
    p_repair.add_argument("--no-agent", action="store_true", help="write the failure packet only")
    p_repair.add_argument("--agent-argv", nargs=argparse.REMAINDER, help="Agent argv after --")
    p_repair.add_argument("--format", choices=["json", "summary"], default="summary")
    p_repair.set_defaults(func=cmd_repair)

    p_wrap = subparsers.add_parser(
        "wrap", help="Run one agent command through the zero-touch pipeline"
    )
    p_wrap.add_argument("--root", default=".")
    p_wrap.add_argument("--policy", help="Policy file (default: ROOT/agentdiff.yaml)")
    p_wrap.add_argument("--task", help="Human-readable task")
    p_wrap.add_argument("--session", help="Optional session id for warm workspace reuse")
    p_wrap.add_argument("--no-proof", action="store_true")
    p_wrap.add_argument("--no-repair", action="store_true")
    p_wrap.add_argument("--no-promote", action="store_true")
    p_wrap.add_argument("--no-cache", action="store_true")
    p_wrap.add_argument("--max-attempts", type=int, default=2)
    p_wrap.add_argument("--max-repair-runtime", type=float, default=1800.0)
    p_wrap.add_argument("--quiet", action="store_true", help="disable local notifications")
    p_wrap.add_argument("--format", choices=["json", "summary"], default="summary")
    p_wrap.add_argument("argv", nargs=argparse.REMAINDER, help="Agent command after --")
    p_wrap.set_defaults(func=cmd_wrap)

    p_serve = subparsers.add_parser("serve", help="Start the local AgentDiff sidecar daemon")
    p_serve.add_argument("--root", default=".")
    p_serve.add_argument("--port", type=int, default=0)
    p_serve.add_argument("--daemon", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    p_status = subparsers.add_parser("status", help="Show sidecar status")
    p_status.add_argument("--root", default=".")
    p_status.add_argument("--format", choices=["json", "summary"], default="summary")
    p_status.set_defaults(func=cmd_status)

    p_stop = subparsers.add_parser("stop", help="Stop the local sidecar daemon")
    p_stop.add_argument("--root", default=".")
    p_stop.set_defaults(func=cmd_stop)

    p_hook = subparsers.add_parser(
        "hook", help="Send one lifecycle/tool event to the sidecar (agent adapters)"
    )
    p_hook.add_argument("event", choices=["session-begin", "tool-call", "session-end"])
    p_hook.add_argument("--root", default=".")
    p_hook.add_argument("--session-id")
    p_hook.add_argument("--task")
    p_hook.add_argument("--data", help="JSON payload for the event")
    p_hook.add_argument("--format", choices=["json", "summary"], default="summary")
    p_hook.set_defaults(func=cmd_hook)

    p_trust = subparsers.add_parser("trust", help="Inspect the compiled trust configuration")
    trust_commands = p_trust.add_subparsers(dest="trust_command", required=True)
    p_trust_graph = trust_commands.add_parser("graph", help="Show the deterministic impact graph")
    p_trust_graph.add_argument("--root", default=".")
    p_trust_graph.add_argument("--format", choices=["json", "summary"], default="summary")
    p_trust_graph.set_defaults(func=cmd_trust_graph)
    p_trust_status = trust_commands.add_parser("status", help="Show the trust lock")
    p_trust_status.add_argument("--root", default=".")
    p_trust_status.add_argument("--format", choices=["json", "summary"], default="summary")
    p_trust_status.set_defaults(func=cmd_trust_status)

    p_impact = subparsers.add_parser(
        "impact", help="Compute the minimum strong proof for changed paths"
    )
    p_impact.add_argument("--paths", required=True, help="Comma-separated relative paths")
    p_impact.add_argument("--root", default=".")
    p_impact.add_argument("--format", choices=["json", "summary"], default="summary")
    p_impact.set_defaults(func=cmd_impact)

    p_proof = subparsers.add_parser("proof", help="Proof cache tooling")
    proof_commands = p_proof.add_subparsers(dest="proof_command", required=True)
    p_cache = proof_commands.add_parser(
        "cache-status", help="Show the content-addressed proof cache"
    )
    p_cache.add_argument("--root", default=".")
    p_cache.add_argument("--format", choices=["json", "summary"], default="summary")
    p_cache.set_defaults(func=cmd_proof_cache_status)

    p_workspace = subparsers.add_parser("workspace", help="Trusted warm workspace tooling")
    workspace_commands = p_workspace.add_subparsers(dest="workspace_command", required=True)
    p_ws_status = workspace_commands.add_parser("status", help="List warm base snapshots")
    p_ws_status.add_argument("--root", default=".")
    p_ws_status.add_argument("--format", choices=["json", "summary"], default="summary")
    p_ws_status.set_defaults(func=cmd_workspace_status)
    p_ws_warm = workspace_commands.add_parser(
        "warm", help="Materialize the warm base for the current identity"
    )
    p_ws_warm.add_argument("--root", default=".")
    p_ws_warm.add_argument("--policy", help="Policy file (default: ROOT/agentdiff.yaml)")
    p_ws_warm.add_argument("--format", choices=["json", "summary"], default="summary")
    p_ws_warm.set_defaults(func=cmd_workspace_warm)
    p_ws_prune = workspace_commands.add_parser("prune", help="Remove stale warm bases")
    p_ws_prune.add_argument("--root", default=".")
    p_ws_prune.add_argument("--keep", type=int, default=3)
    p_ws_prune.set_defaults(func=cmd_workspace_prune)

    p_api = subparsers.add_parser(
        "api", help="Self-maintaining external API scanner and breaking change checker"
    )
    api_commands = p_api.add_subparsers(dest="api_command", required=True)

    p_api_scan = api_commands.add_parser("scan", help="Scan repository AST for external API usages")
    p_api_scan.add_argument("--root", default=".", help="Project root to scan")
    p_api_scan.add_argument(
        "--provider", default="all", help="Provider filter (openai, stripe, all)"
    )
    p_api_scan.add_argument("--format", choices=["json", "summary"], default="summary")
    p_api_scan.set_defaults(func=cmd_api_scan)

    p_api_check = api_commands.add_parser(
        "check", help="Check for API breaking changes, calculate impact and blast radius"
    )
    p_api_check.add_argument("--root", default=".", help="Project root to check")
    p_api_check.add_argument(
        "--provider", default="all", help="Provider filter (openai, stripe, all)"
    )
    p_api_check.add_argument("--format", choices=["json", "summary"], default="summary")
    p_api_check.add_argument(
        "--fail-on",
        choices=["never", "any", "high", "critical"],
        default="high",
        help="Exit with non-zero on matching risk/severity",
    )
    p_api_check.set_defaults(func=cmd_api_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PolicyLoadError,
        PolicyValidationError,
        ProviderError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"agentdiff: {safe_display(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

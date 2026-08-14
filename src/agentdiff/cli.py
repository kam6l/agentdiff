#!/usr/bin/env python3
"""AgentDiff command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentdiff import AgentDiffEvaluator, AgentFramework, DiffEngine, TrajectoryTracker
from agentdiff.cortex import (
    AgentMemoryStore,
    ContextCompressor,
    ContextPacker,
    SelfHealer,
    SkillSynthesizer,
)
from agentdiff.diff_engine import EnvironmentSnapshot, FilesystemSnapshot
from agentdiff.doctor import doctor_report
from agentdiff.policy import (
    Policy,
    PolicyAction,
    PolicyEngine,
    PolicyLoadError,
    PolicyValidationError,
    load_policy,
    load_policy_file,
)
from agentdiff.redaction import safe_display
from agentdiff.runtime import SandboxRuntime
from agentdiff.transaction import (
    AgentRunTransaction,
    RollbackEngine,
    RunInspector,
    RunStore,
    list_runs,
)

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
    skills = SkillSynthesizer(root).list_skills()
    if args.format == "json":
        print(_json([s.to_dict() for s in skills]))
        return 0
    if not skills:
        print("No learned skills found in .agentdiff/skills/")
        return 0
    print(f"AgentDiff Learned Skills ({len(skills)} found):")
    for s in skills:
        print(f"  • {s.skill_id:24} {safe_display(s.title)}")
    return 0


def cmd_skill_generate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    inspector = RunInspector(root, args.run_id)
    summary_dict = inspector.summary().to_dict()
    synthesizer = SkillSynthesizer(root)
    skill = synthesizer.synthesize(summary_dict, title=args.title, save=True)
    if args.format == "json":
        print(_json(skill.to_dict()))
    else:
        print(f"Synthesized skill: {skill.skill_id}")
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


def cmd_heal(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    inspector = RunInspector(root, args.run_id)
    payload = SelfHealer.generate_remediation(inspector.summary().to_dict())
    if args.format == "json":
        print(_json(payload))
    else:
        print(f"Healing Status: {payload['status']}")
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

    p_skill = subparsers.add_parser("skill", help="Manage and synthesize autonomous agent skills")
    skill_commands = p_skill.add_subparsers(dest="skill_command", required=True)
    p_skill_list = skill_commands.add_parser(
        "list", help="List synthesized skills in .agentdiff/skills/"
    )
    p_skill_list.add_argument("--root", default=".")
    p_skill_list.add_argument("--format", choices=["json", "summary"], default="summary")
    p_skill_list.set_defaults(func=cmd_skill_list)
    p_skill_gen = skill_commands.add_parser(
        "generate", help="Synthesize a reusable SKILL.md from a run"
    )
    p_skill_gen.add_argument("run_id")
    p_skill_gen.add_argument("--title", help="Custom title for the synthesized skill")
    p_skill_gen.add_argument("--root", default=".")
    p_skill_gen.add_argument("--format", choices=["json", "summary"], default="summary")
    p_skill_gen.set_defaults(func=cmd_skill_generate)

    p_context = subparsers.add_parser(
        "context", help="Generate compressed context packs for AI models"
    )
    context_commands = p_context.add_subparsers(dest="context_command", required=True)
    p_context_pack = context_commands.add_parser(
        "pack", help="Pack learned skills and memory into prompt context"
    )
    p_context_pack.add_argument(
        "--task", required=True, help="Task prompt intent to pack context for"
    )
    p_context_pack.add_argument("--root", default=".")
    p_context_pack.add_argument("--format", choices=["json", "summary"], default="summary")
    p_context_pack.set_defaults(func=cmd_context_pack)

    p_memory = subparsers.add_parser("memory", help="Inspect trajectory memory and code fragility")
    memory_commands = p_memory.add_subparsers(dest="memory_command", required=True)
    p_memory_stats = memory_commands.add_parser(
        "stats", help="Display memory statistics and fragile paths"
    )
    p_memory_stats.add_argument("--root", default=".")
    p_memory_stats.add_argument("--format", choices=["json", "summary"], default="summary")
    p_memory_stats.set_defaults(func=cmd_memory_stats)

    p_heal = subparsers.add_parser(
        "heal", help="Generate autonomous remediation JSON for agent retries"
    )
    p_heal.add_argument("run_id", help="Run ID to generate remediation for")
    p_heal.add_argument("--root", default=".")
    p_heal.add_argument("--format", choices=["json", "summary"], default="summary")
    p_heal.set_defaults(func=cmd_heal)

    p_snap = subparsers.add_parser("snapshot", help="Capture a legacy environment snapshot")
    p_snap.add_argument("--root", default=".", help="Root directory")
    p_snap.add_argument("--ignore", help="Comma-separated ignore patterns")
    p_snap.add_argument("--max-size", type=int, default=10_000_000, help="Max file size")
    p_snap.add_argument("--no-env", action="store_true", help="Skip env vars")
    p_snap.add_argument("--no-proc", action="store_true", help="Skip processes")
    p_snap.add_argument("--no-ports", action="store_true", help="Skip ports")
    p_snap.add_argument("-o", "--output", help="Output file")
    p_snap.set_defaults(func=cmd_snapshot)

    p_diff = subparsers.add_parser("diff", help="Diff two legacy snapshots")
    p_diff.add_argument("pre", help="Pre-snapshot JSON file")
    p_diff.add_argument("post", help="Post-snapshot JSON file")
    p_diff.add_argument("--root", help="Root directory for relative paths")
    p_diff.add_argument("--format", choices=["json", "summary"], default="summary")
    p_diff.set_defaults(func=cmd_diff)

    p_eval = subparsers.add_parser("eval", help="Evaluate a legacy trajectory")
    p_eval.add_argument("trajectory", help="Trajectory JSON file")
    p_eval.add_argument("--pre", help="Pre-snapshot JSON file")
    p_eval.add_argument("--post", help="Post-snapshot JSON file")
    p_eval.add_argument("--root", help="Root directory")
    p_eval.add_argument("--target", help="Comma-separated target paths")
    p_eval.add_argument("--threshold", type=float, default=0.8, help="Cleanliness threshold")
    p_eval.add_argument("--format", choices=["json", "summary"], default="summary")
    p_eval.add_argument(
        "--fail-on-failure",
        "--fail-below-threshold",
        dest="fail_below_threshold",
        action="store_true",
        help="Exit 1 when the evaluation fails",
    )
    p_eval.set_defaults(func=cmd_eval)
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
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"agentdiff: {safe_display(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

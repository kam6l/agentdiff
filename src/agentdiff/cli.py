#!/usr/bin/env python3
"""
AgentDiff CLI

Commands:
  agentdiff eval      - Evaluate a trajectory file
  agentdiff diff      - Diff two snapshots
  agentdiff replay    - Replay a trajectory
  agentdiff init      - Initialize config for project
  agentdiff snapshot  - Capture current environment snapshot
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from agentdiff import DiffEngine, TrajectoryTracker, AgentDiffEvaluator, AgentFramework
from agentdiff.diff_engine import EnvironmentSnapshot, FilesystemSnapshot


def cmd_snapshot(args):
    """Capture current environment snapshot."""
    engine = DiffEngine(
        watch_paths=[args.root] if args.root else None,
        ignore_patterns=args.ignore.split(",") if args.ignore else None,
        max_file_size_mb=args.max_size // (1024 * 1024) if args.max_size else 100,
    )
    fs_snap, env_snap = engine.snapshot()
    
    # Combine into a single snapshot dict for saving
    snapshot_data = {
        "filesystem": fs_snap.to_dict(),
        "environment": env_snap.to_dict(),
        "timestamp": fs_snap.timestamp,
    }
    
    output = args.output or f"snapshot_{snapshot_data['timestamp']}.json"
    Path(output).write_text(json.dumps(snapshot_data, indent=2))
    print(f"Snapshot saved to {output}")
    print(f"  Files: {len(fs_snap.file_hashes)}")
    print(f"  Dirs:  {len(fs_snap.directories)}")
    print(f"  Env vars: {len(env_snap.env_vars)}")
    print(f"  Processes: {len(env_snap.process_pids)}")
    print(f"  Ports: {len(env_snap.open_ports)}")


def cmd_diff(args):
    """Diff two snapshots."""
    pre_data = json.loads(Path(args.pre).read_text())
    post_data = json.loads(Path(args.post).read_text())
    
    pre_fs = FilesystemSnapshot(**pre_data["filesystem"])
    pre_env = EnvironmentSnapshot(**pre_data["environment"])
    post_fs = FilesystemSnapshot(**post_data["filesystem"])
    post_env = EnvironmentSnapshot(**post_data["environment"])
    
    engine = DiffEngine(
        watch_paths=[args.root] if args.root else None,
    )
    diff = engine.diff(pre_fs, post_fs, pre_env, post_env)
    
    if args.format == "json":
        print(diff.model_dump_json(indent=2))
    else:
        # Use summary property
        summary = diff.summary
        print(f"Files: +{summary.get('file_created', 0)} ~{summary.get('file_modified', 0)} -{summary.get('file_deleted', 0)}")
        print(f"Dirs:  +{summary.get('dir_created', 0)} -{summary.get('dir_deleted', 0)}")
        print(f"Env:   +{summary.get('env_var_added', 0)} ~{summary.get('env_var_modified', 0)} -{summary.get('env_var_removed', 0)}")
        print(f"Procs: +{summary.get('process_spawned', 0)} -{summary.get('process_terminated', 0)}")
        print(f"Ports: +{summary.get('port_opened', 0)} -{summary.get('port_closed', 0)}")


def cmd_eval(args):
    """Evaluate a trajectory file."""
    # Load trajectory
    trajectory_data = json.loads(Path(args.trajectory).read_text())
    tracker = TrajectoryTracker(
        task_description=trajectory_data.get("task_description", ""),
        framework=AgentFramework(trajectory_data.get("framework", "custom")),
    )
    # Reconstruct trajectory from saved data
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
    
    # Load snapshots if provided
    diff = None
    if args.pre and args.post:
        pre_data = json.loads(Path(args.pre).read_text())
        post_data = json.loads(Path(args.post).read_text())
        
        pre_fs = FilesystemSnapshot(**pre_data["filesystem"])
        pre_env = EnvironmentSnapshot(**pre_data["environment"])
        post_fs = FilesystemSnapshot(**post_data["filesystem"])
        post_env = EnvironmentSnapshot(**post_data["environment"])
        
        engine = DiffEngine(
            watch_paths=[args.root] if args.root else None,
        )
        diff = engine.diff(pre_fs, post_fs, pre_env, post_env)
    
    # Evaluate
    evaluator = AgentDiffEvaluator(
        target_paths=args.target.split(",") if args.target else [],
        cleanliness_threshold=args.threshold,
    )
    result = evaluator.evaluate(diff, trajectory)
    
    # Output
    if args.format == "json":
        print(result.model_dump_json(indent=2))
    else:
        print(f"Cleanliness: {result.metrics.cleanliness_score:.1%}")
        print(f"Efficiency:  {result.metrics.efficiency_score:.1%}")
        print(f"Passed:      {result.passed}")
        print(f"Side Effects: {len(result.side_effects)}")
        for effect in result.side_effects:
            print(f"  {effect.severity.value}: {effect.description}")
    
    # Exit code for CI
    if args.fail_below_threshold and not result.passed:
        sys.exit(1)


def cmd_replay(args):
    """Replay a trajectory (placeholder for future implementation)."""
    print("Replay functionality coming in v0.2")
    print("For now, use the trajectory JSON to manually re-run steps")
    sys.exit(1)


def cmd_init(args):
    """Initialize agentdiff config for project."""
    config = """# AgentDiff Configuration
# See https://github.com/your-org/agentdiff for full options

diff_engine:
  root: "."
  ignore_patterns:
    - "*.pyc"
    - "__pycache__"
    - ".git"
    - "*.log"
    - ".venv"
    - "node_modules"
  max_file_size: 10000000
  hash_algorithm: "sha256"
  capture_env_vars: true
  env_denylist:
    - "*KEY*"
    - "*SECRET*"
    - "*TOKEN*"
    - "*PASSWORD*"
  capture_processes: true
  capture_ports: true

evaluator:
  cleanliness_threshold: 0.8
  efficiency_threshold: 0.7
  critical_types:
    - "file_deleted"
    - "dir_deleted"
    - "process_terminated"
    - "port_closed"
    - "env_var_removed"
  warning_types:
    - "file_modified"
    - "file_created"
    - "env_var_added"
    - "process_spawned"

trajectory:
  max_steps: 1000
  loop_detection_window: 10
  loop_similarity_threshold: 0.9
"""
    output = Path(args.output or "agentdiff.yaml")
    output.write_text(config)
    print(f"Config written to {output}")


def main():
    parser = argparse.ArgumentParser(
        prog="agentdiff",
        description="Full-state trajectory evaluation for AI agents",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # snapshot
    p_snap = subparsers.add_parser("snapshot", help="Capture environment snapshot")
    p_snap.add_argument("--root", default=".", help="Root directory")
    p_snap.add_argument("--ignore", help="Comma-separated ignore patterns")
    p_snap.add_argument("--max-size", type=int, default=10_000_000, help="Max file size")
    p_snap.add_argument("--no-env", action="store_true", help="Skip env vars")
    p_snap.add_argument("--no-proc", action="store_true", help="Skip processes")
    p_snap.add_argument("--no-ports", action="store_true", help="Skip ports")
    p_snap.add_argument("-o", "--output", help="Output file")
    p_snap.set_defaults(func=cmd_snapshot)
    
    # diff
    p_diff = subparsers.add_parser("diff", help="Diff two snapshots")
    p_diff.add_argument("pre", help="Pre-snapshot JSON file")
    p_diff.add_argument("post", help="Post-snapshot JSON file")
    p_diff.add_argument("--root", help="Root directory for relative paths")
    p_diff.add_argument("--format", choices=["json", "summary"], default="summary")
    p_diff.set_defaults(func=cmd_diff)
    
    # eval
    p_eval = subparsers.add_parser("eval", help="Evaluate trajectory")
    p_eval.add_argument("trajectory", help="Trajectory JSON file")
    p_eval.add_argument("--pre", help="Pre-snapshot JSON file")
    p_eval.add_argument("--post", help="Post-snapshot JSON file")
    p_eval.add_argument("--root", help="Root directory")
    p_eval.add_argument("--target", help="Comma-separated target paths")
    p_eval.add_argument("--threshold", type=float, default=0.8, help="Cleanliness threshold")
    p_eval.add_argument("--format", choices=["json", "summary"], default="summary")
    p_eval.add_argument("--fail-below-threshold", action="store_true", help="Exit 1 if failed")
    p_eval.set_defaults(func=cmd_eval)
    
    # replay
    p_replay = subparsers.add_parser("replay", help="Replay trajectory")
    p_replay.add_argument("trajectory", help="Trajectory JSON file")
    p_replay.add_argument("--dry-run", action="store_true")
    p_replay.set_defaults(func=cmd_replay)
    
    # init
    p_init = subparsers.add_parser("init", help="Initialize config")
    p_init.add_argument("-o", "--output", help="Output config file")
    p_init.set_defaults(func=cmd_init)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
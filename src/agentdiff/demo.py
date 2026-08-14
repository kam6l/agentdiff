#!/usr/bin/env python3
"""Run a real AgentDiff transaction against a disposable project."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from agentdiff.policy import load_policy
from agentdiff.transaction import AgentRunTransaction, TransactionResult


def create_demo_project(project_dir: Path) -> None:
    """Create the before-state used by the transaction demo."""

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "calculator.py").write_text(
        "def add(a, b):\n    return a - b  # BUG: should be +\n",
        encoding="utf-8",
    )
    (project_dir / "config.json").write_text(
        json.dumps({"debug": False}, indent=2),
        encoding="utf-8",
    )


def run_demo_transaction(project_dir: Path) -> TransactionResult:
    """Execute one real subprocess through the primary transaction pipeline."""

    policy = load_policy(
        {
            "version": 1,
            "filesystem": {
                "allow_write": ["calculator.py"],
                "review": ["debug.log"],
                "deny": ["config.json"],
                "default": "review",
            },
            "process": {"allow": ["*"], "default": "allow"},
            "network": {"mode": "off"},
            "rollback": {"enabled": True, "max_backup_file_mb": 5},
        }
    )
    script = (
        "from pathlib import Path; "
        "Path('calculator.py').write_text('def add(a, b):\\n    return a + b\\n', "
        "encoding='utf-8'); "
        "Path('debug.log').write_text('temporary debug output\\n', encoding='utf-8'); "
        "Path('config.json').write_text('{\\\"debug\\\": true}\\n', encoding='utf-8')"
    )
    return AgentRunTransaction(
        root=project_dir,
        policy=policy,
        task="Fix the calculator addition bug",
    ).run([sys.executable, "-c", script])


def run_demo(show_json: bool = False) -> None:
    """Run the transaction demo, emitting only JSON when requested."""

    with tempfile.TemporaryDirectory(prefix="agentdiff-demo-") as directory:
        project_dir = Path(directory) / "calculator-project"
        create_demo_project(project_dir)
        result = run_demo_transaction(project_dir)

        if show_json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return

        print("AgentDiff transaction demo")
        print("=" * 48)
        print(f"Run: {result.run_id}")
        print(f"Status: {result.status}")
        print(f"Policy outcome: {result.safety_outcome.value.upper()}")
        print(f"Blast radius: {result.blast_radius.score}/100")
        print("\nObserved changes:")
        for change in result.changes:
            print(
                f"  {change.decision.action.value.upper():6} {change.change_type:8} {change.path}"
            )
        print(f"\nInspect the same evidence shape with: agentdiff inspect {result.run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real AgentDiff transaction demo")
    parser.add_argument("--json", action="store_true", help="Output the transaction result as JSON")
    args = parser.parse_args()
    run_demo(show_json=args.json)


if __name__ == "__main__":
    main()

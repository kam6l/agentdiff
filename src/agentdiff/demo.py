#!/usr/bin/env python3
"""
AgentDiff CLI Demo

Demonstrates the full evaluation pipeline:
1. Capture pre-execution snapshot
2. Simulate agent trajectory (with tool calls)
3. Capture post-execution snapshot
4. Evaluate and print rich report
"""

import argparse
import json
import tempfile
from pathlib import Path

from agentdiff import (
    AgentDiffEvaluator,
    AgentFramework,
    DiffEngine,
    TrajectoryTracker,
)


def create_demo_project(project_dir: Path) -> None:
    """Create a sample project for the demo."""
    project_dir.mkdir(parents=True, exist_ok=True)

    # Main source file with a bug
    (project_dir / "calculator.py").write_text('''
def add(a, b):
    """Add two numbers."""
    return a - b  # BUG: should be +

def multiply(a, b):
    """Multiply two numbers."""
    return a * b

def divide(a, b):
    """Divide two numbers."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
''')

    # Test file
    (project_dir / "test_calculator.py").write_text("""
import pytest
from calculator import add, multiply, divide

def test_add():
    assert add(2, 3) == 5

def test_multiply():
    assert multiply(4, 5) == 20

def test_divide():
    assert divide(10, 2) == 5
    with pytest.raises(ValueError):
        divide(1, 0)
""")

    # Config file
    (project_dir / "config.json").write_text(
        json.dumps({"name": "calculator-demo", "version": "1.0.0", "debug": False}, indent=2)
    )


def simulate_agent_run(project_dir: Path) -> tuple:
    """
    Simulate an agent fixing the bug but introducing side effects.
    Returns (trajectory, pre_snapshot, post_snapshot)
    """
    engine = DiffEngine(watch_paths=[str(project_dir)])

    # First, take pre-snapshot of the INITIAL state
    pre_fs, pre_env = engine.snapshot()

    # NOW simulate agent making changes to files
    # Step 1: Fix the bug in calculator.py
    fixed_content = '''def add(a, b):
    """Add two numbers."""
    return a + b  # FIXED

def multiply(a, b):
    """Multiply two numbers."""
    return a * b

def divide(a, b):
    """Divide two numbers."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
'''
    (project_dir / "calculator.py").write_text(fixed_content)

    # Step 2: Add debug.log (side effect)
    (project_dir / "debug.log").write_text("DEBUG: add(2, 3) = 5\nDEBUG: multiply(4, 5) = 20\n")

    # Step 3: Modify config.json (side effect)
    (project_dir / "config.json").write_text(
        json.dumps(
            {"name": "calculator-demo", "version": "1.0.0", "debug": True, "log_level": "DEBUG"},
            indent=2,
        )
    )

    # NOW take post-snapshot
    post_fs, post_env = engine.snapshot()

    # Simulate agent trajectory (record what the agent "did")
    tracker = TrajectoryTracker(
        task_description="Fix the add() function bug in calculator.py",
        framework=AgentFramework.CUSTOM,
    )

    # Step 1: Read the buggy file
    tracker.start_step(thought="Reading calculator.py to understand the bug")
    tracker.record_tool_call(
        "read_file",
        {"path": str(project_dir / "calculator.py")},
        result="def add(a, b):\n    return a - b  # BUG: should be +",
        duration_ms=45,
    )
    tracker.end_step(observation="Found bug: add() uses subtraction instead of addition")

    # Step 2: Fix the bug
    tracker.start_step(thought="Fixing the add function to use + instead of -")
    tracker.record_tool_call(
        "write_file",
        {"path": str(project_dir / "calculator.py"), "content": fixed_content},
        result="ok",
        duration_ms=60,
    )
    tracker.end_step(observation="Fixed the add() function")

    # Step 3: Run tests (simulated)
    tracker.start_step(thought="Running tests to verify the fix")
    tracker.record_tool_call(
        "run_command",
        {"command": "python -m pytest test_calculator.py -v"},
        result="test_add PASSED\ntest_multiply PASSED\ntest_divide PASSED\n\n3 passed in 0.12s",
        duration_ms=1200,
    )
    tracker.end_step(observation="All tests pass!")

    # Step 4: Side effect - agent adds debug logging (unintended)
    tracker.start_step(thought="Adding some debug logging for future debugging")
    tracker.record_tool_call(
        "write_file",
        {
            "path": str(project_dir / "debug.log"),
            "content": "DEBUG: add(2, 3) = 5\nDEBUG: multiply(4, 5) = 20\n",
        },
        result="ok",
        duration_ms=30,
    )
    tracker.record_tool_call(
        "write_file",
        {
            "path": str(project_dir / "config.json"),
            "content": json.dumps(
                {
                    "name": "calculator-demo",
                    "version": "1.0.0",
                    "debug": True,
                    "log_level": "DEBUG",
                },
                indent=2,
            ),
        },
        result="ok",
        duration_ms=25,
    )
    tracker.end_step(observation="Added debug logging and config")

    trajectory = tracker.finish(final_result="Bug fixed, but added debug artifacts")

    return trajectory, (pre_fs, pre_env), (post_fs, post_env)


def run_demo(show_json: bool = False) -> None:
    """Run the full demo, emitting only JSON when ``show_json`` is enabled."""
    if not show_json:
        print("🤖 AgentDiff Demo: Evaluating AI Agent Trajectories")
        print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "demo_project"

        if not show_json:
            print("\n📁 Setting up demo project...")
        create_demo_project(project_dir)
        if not show_json:
            print(f"   Created project at: {project_dir}")
            print("\n🤖 Simulating agent execution...")

        trajectory, pre_snapshot, post_snapshot = simulate_agent_run(project_dir)
        if not show_json:
            print(
                f"   Recorded {trajectory.total_steps} steps with "
                f"{trajectory.total_tool_calls} tool calls"
            )
            print("\n🔍 Evaluating trajectory...")

        evaluator = AgentDiffEvaluator(target_paths=[str(project_dir)])
        evaluator.set_target_mutations([str(project_dir / "calculator.py")])
        result = evaluator.evaluate_from_snapshots(trajectory, pre_snapshot, post_snapshot)

        if show_json:
            print(result.to_json())
            return

        print("\n" + "=" * 60)
        result.print_summary()
        print("\n📝 Trajectory Steps:")
        for step in trajectory.steps:
            print(f"  Step {step.step_index}: {step.thought or 'No thought'}")
            for tc in step.tool_calls:
                status = "✅" if tc.succeeded else "❌"
                print(
                    f"    {status} {tc.name}({list(tc.arguments.keys())}) → {tc.duration_ms:.0f}ms"
                )


def main():
    parser = argparse.ArgumentParser(description="AgentDiff CLI Demo")
    parser.add_argument("--json", action="store_true", help="Output evaluation as JSON")
    args = parser.parse_args()

    run_demo(show_json=args.json)


if __name__ == "__main__":
    main()

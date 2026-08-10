#!/usr/bin/env python3
"""Run a small AgentDiff transaction in an explicit disposable workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentdiff.policy import load_policy_file
from agentdiff.transaction import AgentRunTransaction


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).with_name("agentdiff.yaml"),
    )
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    policy = load_policy_file(args.policy)
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; Path('src/result.txt').write_text('ok\\n', encoding='utf-8')",
    ]
    result = AgentRunTransaction(
        root=workspace,
        policy=policy,
        task="Create one allowed result file",
    ).run(command, timeout_seconds=10)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return result.recommended_exit_code("deny")


if __name__ == "__main__":
    raise SystemExit(main())

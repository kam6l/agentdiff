#!/usr/bin/env python3
"""Exercise run -> prove -> dry-run -> promote in an explicit workspace."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentdiff import (
    AgentRunTransaction,
    DockerRuntime,
    PromotionEngine,
    ProofEngine,
    ProofVerdict,
    load_policy_file,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).with_name("agentdiff.yaml"),
    )
    args = parser.parse_args()

    root = args.workspace.expanduser().resolve()
    (root / "src").mkdir(parents=True, exist_ok=True)
    result_path = root / "src" / "result.txt"
    if result_path.exists():
        raise SystemExit(f"refusing to overwrite existing example path: {result_path}")

    policy = load_policy_file(args.policy)
    runtime = DockerRuntime(root=root, image="python:3.12-slim", network="none")
    run = AgentRunTransaction(
        root=root,
        policy=policy,
        runtime=runtime,
        task="Create one independently provable file",
    ).run(
        [
            "python",
            "-c",
            "from pathlib import Path; Path('src/result.txt').write_text('ok\\n', encoding='utf-8')",
        ],
        timeout_seconds=60,
    )
    print(f"run={run.run_id} status={run.status} host_untouched={not result_path.exists()}")

    proof = ProofEngine.open(root, run.run_id).prove(timeout_seconds=60)
    print(f"proof={proof.verdict.value} hidden_state={proof.hidden_state_dependency}")
    if proof.verdict is not ProofVerdict.PROVEN:
        return 7

    promoter = PromotionEngine.open(root, run.run_id)
    plan = promoter.promote(dry_run=True, safe_only=True)
    print(f"dry_run={plan.status} actions={len(plan.actions)}")
    if not plan.ok:
        return 8

    promoted = promoter.promote(safe_only=True)
    print(f"promotion={promoted.status} content={result_path.read_text(encoding='utf-8')!r}")
    return 0 if promoted.ok else 8


if __name__ == "__main__":
    raise SystemExit(main())

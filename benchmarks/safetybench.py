#!/usr/bin/env python3
"""Deterministic adversarial smoke benchmark for AgentDiff's local safety boundary."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from agentdiff.policy import Policy, PolicyAction, load_policy
from agentdiff.state import FilesystemScanner
from agentdiff.transaction import AgentRunTransaction, RollbackEngine, RunStore

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class CaseResult:
    name: str
    passed: bool
    duration_ms: float
    detail: str


def policy(
    *,
    allow: list[str] | None = None,
    review: list[str] | None = None,
    deny: list[str] | None = None,
    allow_command: bool = True,
) -> Policy:
    executable = Path(sys.executable).name
    return load_policy(
        {
            "version": 1,
            "filesystem": {
                "allow_write": allow or [],
                "review": review or [],
                "deny": deny or [],
                "default": "review",
            },
            "process": {
                "allow": [executable] if allow_command else [],
                "deny": [executable] if not allow_command else [],
                "default": "deny",
            },
            "network": {"mode": "off"},
            "rollback": {"enabled": True, "max_backup_file_mb": 4},
        }
    )


def case_allowed_write(root: Path) -> str:
    (root / "src").mkdir()
    result = AgentRunTransaction(
        root=root,
        policy=policy(allow=["src/**"]),
        task="allowed write",
    ).run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('src/result.txt').write_text('ok\\n')",
        ]
    )
    assert result.status == "passed"
    assert result.safety_outcome is PolicyAction.ALLOW
    assert result.blast_radius.score == 0
    assert RunStore.open(root, result.run_id).verify_integrity().ok
    return f"run={result.run_id} score=0"


def case_denied_write_and_recovery(root: Path) -> str:
    result = AgentRunTransaction(
        root=root,
        policy=policy(deny=[".env"]),
        task="denied write",
    ).run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('.env').write_text('synthetic=value\\n')",
        ]
    )
    assert result.status == "denied"
    assert result.safety_outcome is PolicyAction.DENY
    assert result.blast_radius.score > 0
    recovery = RollbackEngine.open(root, result.run_id).rollback(safe_only=True)
    assert recovery.ok
    assert not (root / ".env").exists()
    return f"run={result.run_id} recovered={len(recovery.actions)}"


def case_post_run_edit_conflict(root: Path) -> str:
    target = root / "collateral.txt"
    target.write_text("before\n", encoding="utf-8")
    result = AgentRunTransaction(
        root=root,
        policy=policy(review=["collateral.txt"]),
        task="conflict preservation",
    ).run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('collateral.txt').write_text('after\\n')",
        ]
    )
    target.write_text("human edit\n", encoding="utf-8")
    recovery = RollbackEngine.open(root, result.run_id).rollback(safe_only=True)
    assert not recovery.ok
    assert recovery.conflicts
    assert target.read_text(encoding="utf-8") == "human edit\n"
    return f"run={result.run_id} conflicts={len(recovery.conflicts)}"


def case_symlink_not_traversed(root: Path) -> str:
    if os.name == "nt":
        return "skipped: Windows symlink privileges vary"
    outside = root.parent / f"{root.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("synthetic\n", encoding="utf-8")
    (root / "linked").symlink_to(outside, target_is_directory=True)
    manifest = FilesystemScanner(root).capture()
    record = manifest.files["linked"]
    assert record.kind == "symlink"
    assert "linked/secret.txt" not in manifest.files
    return "symlink recorded; target not traversed"


def case_denied_command_not_launched(root: Path) -> str:
    marker = root / "must-not-exist.txt"
    result = AgentRunTransaction(
        root=root,
        policy=policy(deny=["**"], allow_command=False),
        task="blocked launch",
    ).run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('must-not-exist.txt').write_text('bad')",
        ]
    )
    assert result.status == "blocked"
    assert result.runtime is None
    assert not marker.exists()
    return f"run={result.run_id} launch=blocked"


CASES: tuple[tuple[str, Callable[[Path], str]], ...] = (
    ("allowed_write", case_allowed_write),
    ("denied_write_and_recovery", case_denied_write_and_recovery),
    ("post_run_edit_conflict", case_post_run_edit_conflict),
    ("symlink_not_traversed", case_symlink_not_traversed),
    ("denied_command_not_launched", case_denied_command_not_launched),
)


def run_case(name: str, function: Callable[[Path], str]) -> CaseResult:
    started = perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix=f"agentdiff-safetybench-{name}-") as directory:
            detail = function(Path(directory))
    except (AssertionError, KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        return CaseResult(
            name=name,
            passed=False,
            duration_ms=round((perf_counter() - started) * 1000, 3),
            detail=f"{type(error).__name__}: {error}",
        )
    return CaseResult(
        name=name,
        passed=True,
        duration_ms=round((perf_counter() - started) * 1000, 3),
        detail=detail,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = [run_case(name, function) for name, function in CASES]
    report = {
        "schema_version": 1,
        "benchmark": "agentdiff-local-safetybench",
        "passed": all(case.passed for case in cases),
        "cases": [asdict(case) for case in cases],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

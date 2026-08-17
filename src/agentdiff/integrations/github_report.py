"""Render deterministic run/proof evidence for a GitHub Actions check summary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from agentdiff.transaction import RunInspector


def build_trust_report(root: str | Path, run_id: str) -> dict[str, Any]:
    """Return a machine-readable report without model interpretation."""

    inspected = RunInspector(root, run_id).inspect()
    result = inspected["result"]
    proof_bundle = inspected.get("proof", {})
    proof = proof_bundle.get("result", {}) if isinstance(proof_bundle, dict) else {}
    proof_integrity = proof_bundle.get("integrity", {}) if isinstance(proof_bundle, dict) else {}
    immediate = result.get("blast_radius", {}) if isinstance(result, dict) else {}
    future = result.get("future_blast_radius", {}) if isinstance(result, dict) else {}
    capsule_integrity = bool(inspected["integrity"].get("ok"))
    proof_integrity_ok = bool(proof_integrity.get("ok"))
    verdict = (
        "PROVEN"
        if proof.get("verdict") == "PROVEN" and capsule_integrity and proof_integrity_ok
        else "NOT_PROVEN"
    )
    raw_policy = str(result.get("safety_outcome", "unknown")).upper()
    policy = raw_policy if raw_policy in {"ALLOW", "REVIEW", "DENY"} else "UNKNOWN"
    raw_hidden_state = str(proof.get("hidden_state_dependency", "NOT_ASSESSED"))
    hidden_state = (
        raw_hidden_state
        if raw_hidden_state in {"NONE_DETECTED", "POSSIBLE", "CONFIRMED", "NOT_ASSESSED"}
        else "NOT_ASSESSED"
    )
    return {
        "schema_version": 1,
        "run_id": run_id,
        "policy": policy,
        "immediate_blast_radius": _bounded_score(immediate),
        "future_blast_radius": _bounded_score(future),
        "clean_room_proof": "PASS" if verdict == "PROVEN" else "FAIL",
        "hidden_state": hidden_state,
        "verdict": verdict,
        "capsule_integrity": capsule_integrity,
        "proof_integrity": proof_integrity_ok,
        "tests": _test_summary(proof),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render bounded status-only Markdown suitable for ``GITHUB_STEP_SUMMARY``."""

    passed = report["verdict"] == "PROVEN"
    mark = "✓" if passed else "✗"
    tests = report["tests"]
    test_text = (
        f"{tests['passed']}/{tests['total']}" if tests["total"] is not None else tests["status"]
    )
    return "\n".join(
        (
            "## AgentDiff Trust Report",
            "",
            "| Signal | Result |",
            "|---|---:|",
            f"| Policy | {report['policy']} |",
            f"| Immediate Blast Radius | {report['immediate_blast_radius']}/100 |",
            f"| Future Blast Radius | {report['future_blast_radius']}/100 |",
            f"| Clean-Room Proof | {report['clean_room_proof']} |",
            f"| Tests | {test_text} |",
            f"| Hidden State | {report['hidden_state']} |",
            "",
            "### VERDICT",
            f"{mark} **{report['verdict']}**",
            "",
        )
    )


def _test_summary(proof: dict[str, Any]) -> dict[str, int | str | None]:
    for phase in reversed(proof.get("phases", [])):
        if isinstance(phase, dict) and phase.get("phase") == "tests":
            raw_status = str(phase.get("status", "UNKNOWN"))
            status = raw_status if raw_status in {"PASS", "FAIL"} else "UNKNOWN"
            passed = phase.get("tests_passed")
            total = phase.get("tests_total")
            return {
                "status": status,
                "passed": passed if isinstance(passed, int) and passed >= 0 else None,
                "total": total if isinstance(total, int) and total >= 0 else None,
            }
    return {"status": "NOT_RUN", "passed": None, "total": None}


def _bounded_score(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    score = payload.get("score", 0)
    if not isinstance(score, int) or isinstance(score, bool):
        return 0
    return min(100, max(0, score))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json-output", default="agentdiff-trust-report.json")
    parser.add_argument("--markdown-output", default="agentdiff-trust-report.md")
    args = parser.parse_args(argv)
    report = build_trust_report(args.root, args.run_id)
    json_path = Path(args.json_output)
    markdown_path = Path(args.markdown_output)
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    markdown = render_markdown(report)
    markdown_path.write_text(markdown, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(markdown)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["verdict"] == "PROVEN" else 7


if __name__ == "__main__":
    raise SystemExit(main())

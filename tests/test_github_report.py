"""GitHub trust-report rendering tests."""

from __future__ import annotations

from agentdiff.integrations.github_report import render_markdown


def test_github_report_contains_two_risk_scores_and_proof_verdict() -> None:
    report = {
        "verdict": "PROVEN",
        "policy": "ALLOW",
        "immediate_blast_radius": 12,
        "future_blast_radius": 6,
        "clean_room_proof": "PASS",
        "hidden_state": "NONE_DETECTED",
        "tests": {"status": "PASS", "passed": 214, "total": 214},
    }

    markdown = render_markdown(report)

    assert "Immediate Blast Radius | 12/100" in markdown
    assert "Future Blast Radius | 6/100" in markdown
    assert "Tests | 214/214" in markdown
    assert "**PROVEN**" in markdown

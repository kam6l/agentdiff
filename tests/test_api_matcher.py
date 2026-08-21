"""Unit tests for APIMatcher and MigrationImpact calculation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentdiff.api.matcher import APIMatcher
from agentdiff.api.models import APIUsage
from agentdiff.scoring.blast_radius import RiskLevel

if TYPE_CHECKING:
    from pathlib import Path


def test_matcher_matches_usages_and_computes_impact() -> None:
    usages = [
        APIUsage(
            provider="openai",
            library="openai",
            symbol="openai.ChatCompletion.create",
            call_type="call",
            filepath="src/llm.py",
            line_number=20,
            keyword_arguments={"model": "gpt-3.5-turbo-0301"},
        ),
        APIUsage(
            provider="stripe",
            library="stripe",
            symbol="stripe.Charge.create",
            call_type="call",
            filepath="src/checkout.py",
            line_number=45,
            keyword_arguments={"amount": "2000"},
        ),
    ]

    matcher = APIMatcher()
    impact = matcher.calculate_impact(usages)

    assert impact.total_usages == 2
    assert impact.affected_usages >= 2
    assert "src/llm.py" in impact.affected_files
    assert "src/checkout.py" in impact.affected_files
    assert impact.has_breaking_changes is True
    assert impact.blast_radius.score > 0
    assert len(impact.remediations) > 0


def test_matcher_with_no_breaking_changes() -> None:
    usages = [
        APIUsage(
            provider="openai",
            library="openai",
            symbol="client.responses.create",
            call_type="call",
            filepath="src/modern_llm.py",
            line_number=15,
            keyword_arguments={"model": "gpt-4o", "input": "hello"},
        ),
        APIUsage(
            provider="stripe",
            library="stripe",
            symbol="stripe.PaymentIntent.create",
            call_type="call",
            filepath="src/modern_pay.py",
            line_number=30,
            keyword_arguments={"amount": "5000", "currency": "usd"},
        ),
    ]

    matcher = APIMatcher()
    impact = matcher.calculate_impact(usages)

    assert impact.total_usages == 2
    assert impact.affected_usages == 0
    assert len(impact.affected_files) == 0
    assert impact.has_breaking_changes is False
    assert impact.blast_radius.score == 0
    assert impact.risk_level == RiskLevel.LOW


def test_matcher_integrates_with_impact_engine(tmp_path: Path) -> None:
    # Setup mock repository with tests and code
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "service.py").write_text(
        "import openai\nopenai.ChatCompletion.create(model='gpt-4')\n",
        encoding="utf-8",
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_service.py").write_text("def test_service(): pass\n", encoding="utf-8")

    usages = [
        APIUsage(
            provider="openai",
            library="openai",
            symbol="openai.ChatCompletion.create",
            call_type="call",
            filepath="src/service.py",
            line_number=2,
            keyword_arguments={"model": "gpt-4"},
        ),
    ]

    matcher = APIMatcher()
    impact = matcher.calculate_impact(usages, root=tmp_path)

    assert impact.affected_usages >= 1
    assert "src/service.py" in impact.affected_files
    if impact.impact_plan is not None:
        assert impact.impact_plan.level in {"static", "targeted", "full"}

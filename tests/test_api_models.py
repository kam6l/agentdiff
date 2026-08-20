"""Unit tests for APIUsage, APIChange, and MigrationImpact models."""

from __future__ import annotations

from agentdiff.api.models import (
    APIChange,
    APIUsage,
    ChangeSeverity,
    ChangeType,
    MatchedChange,
    MigrationImpact,
)
from agentdiff.scoring.blast_radius import BlastRadiusResult, RiskComponent, RiskLevel


def test_api_usage_model_serialization() -> None:
    usage = APIUsage(
        provider="openai",
        library="openai",
        symbol="openai.ChatCompletion.create",
        call_type="call",
        filepath="src/llm/client.py",
        line_number=42,
        column=4,
        arguments=("arg1",),
        keyword_arguments={"model": "gpt-4", "temperature": "0.7"},
        code_snippet="openai.ChatCompletion.create(model='gpt-4')",
        enclosing_scope="generate_response",
    )

    data = usage.to_dict()
    assert data["provider"] == "openai"
    assert data["symbol"] == "openai.ChatCompletion.create"
    assert data["line_number"] == 42
    assert data["keyword_arguments"] == {"model": "gpt-4", "temperature": "0.7"}

    restored = APIUsage.from_dict(data)
    assert restored == usage


def test_api_change_model_serialization() -> None:
    change = APIChange(
        change_id="openai-v1-chat-completion-create",
        provider="openai",
        title="Legacy ChatCompletion replaced",
        change_type=ChangeType.REMOVAL,
        severity=ChangeSeverity.HIGH,
        target_symbol="openai.ChatCompletion.create",
        description="Removed in v1.0.0+",
        breaking_version=">=1.0.0",
        migration_guide_url="https://example.com/migration",
        replacement_symbol="client.chat.completions.create",
        replacement_code="client.chat.completions.create()",
    )

    data = change.to_dict()
    assert data["change_id"] == "openai-v1-chat-completion-create"
    assert data["change_type"] == "removal"
    assert data["severity"] == "high"

    restored = APIChange.from_dict(data)
    assert restored == change


def test_migration_impact_model_serialization() -> None:
    usage = APIUsage(
        provider="stripe",
        library="stripe",
        symbol="stripe.Charge.create",
        call_type="call",
        filepath="payments/checkout.py",
        line_number=10,
    )
    change = APIChange(
        change_id="stripe-charges-to-payment-intents",
        provider="stripe",
        title="Use PaymentIntents",
        change_type=ChangeType.DEPRECATION,
        severity=ChangeSeverity.HIGH,
        target_symbol="stripe.Charge.create",
        description="Migrate to PaymentIntents",
    )
    matched = MatchedChange(
        usage=usage,
        change=change,
        risk_points=25,
        remediation_advice="Use stripe.PaymentIntent.create()",
    )
    blast = BlastRadiusResult(
        score=25,
        raw_score=25,
        level=RiskLevel.MODERATE,
        counts={"total_usages": 1, "affected_usages": 1},
        components=[
            RiskComponent(
                name="api_change_high",
                count=1,
                weight=25,
                points=25,
                detail="1 high change",
            )
        ],
    )
    impact = MigrationImpact(
        total_usages=1,
        affected_usages=1,
        affected_files=("payments/checkout.py",),
        matched_changes=(matched,),
        blast_radius=blast,
        risk_level=RiskLevel.MODERATE,
        remediations=("Use stripe.PaymentIntent.create()",),
    )

    assert impact.has_breaking_changes is True
    data = impact.to_dict()
    assert data["total_usages"] == 1
    assert data["affected_usages"] == 1
    assert data["risk_level"] == "moderate"
    assert len(data["matched_changes"]) == 1

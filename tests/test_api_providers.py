"""Unit tests for OpenAI and Stripe API providers."""

from __future__ import annotations

from agentdiff.api.models import APIUsage
from agentdiff.api.providers import (
    OpenAIProvider,
    StripeProvider,
    get_all_providers,
    get_provider,
    get_providers_for_selection,
    list_providers,
)


def test_provider_registry_lookups() -> None:
    providers = list_providers()
    assert "openai" in providers
    assert "stripe" in providers

    openai_p = get_provider("openai")
    assert isinstance(openai_p, OpenAIProvider)

    stripe_p = get_provider("stripe")
    assert isinstance(stripe_p, StripeProvider)

    assert get_provider("nonexistent") is None

    all_provs = get_all_providers()
    assert len(all_provs) >= 2

    selection_all = get_providers_for_selection("all")
    assert len(selection_all) >= 2

    selection_single = get_providers_for_selection("openai")
    assert len(selection_single) == 1
    assert selection_single[0].name == "openai"


def test_openai_provider_changes_catalog() -> None:
    provider = OpenAIProvider()
    changes = provider.get_known_changes()
    assert len(changes) >= 5

    change_ids = {c.change_id for c in changes}
    assert "openai-v1-chat-completion-create" in change_ids
    assert "openai-deprecated-functions-parameter" in change_ids
    assert "openai-shutdown-model-davinci-003" in change_ids
    assert "openai-deprecated-snapshot-gpt35-0301" in change_ids


def test_openai_provider_matches_legacy_chat_completion() -> None:
    provider = OpenAIProvider()
    changes = {c.change_id: c for c in provider.get_known_changes()}

    usage = APIUsage(
        provider="openai",
        library="openai",
        symbol="openai.ChatCompletion.create",
        call_type="call",
        filepath="app.py",
        line_number=10,
        keyword_arguments={"model": "gpt-4"},
    )
    change = changes["openai-v1-chat-completion-create"]
    assert provider.match_usage(usage, change) is True


def test_openai_provider_matches_deprecated_parameter() -> None:
    provider = OpenAIProvider()
    changes = {c.change_id: c for c in provider.get_known_changes()}

    usage_with_funcs = APIUsage(
        provider="openai",
        library="openai",
        symbol="client.chat.completions.create",
        call_type="call",
        filepath="app.py",
        line_number=10,
        keyword_arguments={"model": "gpt-4", "functions": "my_funcs"},
    )
    change = changes["openai-deprecated-functions-parameter"]
    assert provider.match_usage(usage_with_funcs, change) is True

    usage_without_funcs = APIUsage(
        provider="openai",
        library="openai",
        symbol="client.chat.completions.create",
        call_type="call",
        filepath="app.py",
        line_number=10,
        keyword_arguments={"model": "gpt-4", "tools": "my_tools"},
    )
    assert provider.match_usage(usage_without_funcs, change) is False


def test_openai_provider_matches_deprecated_model() -> None:
    provider = OpenAIProvider()
    changes = {c.change_id: c for c in provider.get_known_changes()}

    usage_davinci = APIUsage(
        provider="openai",
        library="openai",
        symbol="openai.Completion.create",
        call_type="call",
        filepath="app.py",
        line_number=10,
        keyword_arguments={"model": "text-davinci-003"},
    )
    change = changes["openai-shutdown-model-davinci-003"]
    assert provider.match_usage(usage_davinci, change) is True


def test_stripe_provider_changes_catalog() -> None:
    provider = StripeProvider()
    changes = provider.get_known_changes()
    assert len(changes) >= 4

    change_ids = {c.change_id for c in changes}
    assert "stripe-charges-to-payment-intents" in change_ids
    assert "stripe-sources-to-payment-methods" in change_ids
    assert "stripe-orders-deprecated" in change_ids


def test_stripe_provider_matches_legacy_charges() -> None:
    provider = StripeProvider()
    changes = {c.change_id: c for c in provider.get_known_changes()}

    usage = APIUsage(
        provider="stripe",
        library="stripe",
        symbol="stripe.Charge.create",
        call_type="call",
        filepath="pay.py",
        line_number=5,
        keyword_arguments={"amount": "1000", "currency": "usd"},
    )
    change = changes["stripe-charges-to-payment-intents"]
    assert provider.match_usage(usage, change) is True

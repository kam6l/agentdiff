"""Provider registry for third-party API scanners and change matchers."""

from __future__ import annotations

from typing import Iterable

from agentdiff.api.providers.base import APIProvider
from agentdiff.api.providers.openai import OpenAIProvider
from agentdiff.api.providers.stripe import StripeProvider

_PROVIDERS: dict[str, APIProvider] = {
    "openai": OpenAIProvider(),
    "stripe": StripeProvider(),
}


def get_provider(name: str) -> APIProvider | None:
    """Retrieve an APIProvider instance by name."""
    return _PROVIDERS.get(name.lower().strip())


def list_providers() -> list[str]:
    """Return the names of all registered providers."""
    return sorted(_PROVIDERS.keys())


def get_all_providers() -> list[APIProvider]:
    """Return all registered provider instances."""
    return list(_PROVIDERS.values())


def get_providers_for_selection(selection: str | Iterable[str] = "all") -> list[APIProvider]:
    """Return selected providers based on a filter name or sequence."""
    if isinstance(selection, str):
        if selection.lower() == "all":
            return get_all_providers()
        prov = get_provider(selection)
        return [prov] if prov is not None else []
    
    result: list[APIProvider] = []
    for item in selection:
        prov = get_provider(item)
        if prov is not None and prov not in result:
            result.append(prov)
    return result


__all__ = [
    "APIProvider",
    "OpenAIProvider",
    "StripeProvider",
    "get_all_providers",
    "get_provider",
    "get_providers_for_selection",
    "list_providers",
]

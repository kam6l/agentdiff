"""Tests for provider-isolated Cortex API and local client adapters."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentdiff.providers import (
    AnthropicMessagesProvider,
    OllamaChatProvider,
    OpenAIResponsesProvider,
    ProviderError,
    SubprocessProvider,
    create_provider,
)


def test_openai_responses_provider_uses_current_stateful_shape() -> None:
    captured: dict[str, Any] = {}

    def transport(url: str, headers: Any, payload: Any, timeout: float) -> dict[str, Any]:
        captured.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return {
            "id": "resp_123",
            "model": "gpt-5.6-terra",
            "output_text": "Use the recorded rollback boundary.",
            "usage": {"input_tokens": 20, "output_tokens": 7},
        }

    provider = OpenAIResponsesProvider(api_key="test-key", transport=transport)
    result = provider.complete(
        "Plan the fix",
        system_prompt="verified memory",
        previous_response_id="resp_prior",
    )

    assert result.text == "Use the recorded rollback boundary."
    assert result.response_id == "resp_123"
    assert captured["payload"]["reasoning"] == {
        "effort": "medium",
        "context": "all_turns",
    }
    assert captured["payload"]["previous_response_id"] == "resp_prior"
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_anthropic_provider_sends_system_memory_separately() -> None:
    captured: dict[str, Any] = {}

    def transport(url: str, headers: Any, payload: Any, timeout: float) -> dict[str, Any]:
        captured.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return {
            "id": "msg_123",
            "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": "Review the evidence first."}],
            "usage": {"input_tokens": 11, "output_tokens": 6},
        }

    provider = AnthropicMessagesProvider(api_key="test-key", transport=transport)
    result = provider.complete("Plan the fix", system_prompt="verified memory")

    assert result.text == "Review the evidence first."
    assert captured["payload"]["system"] == "verified memory"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "Plan the fix"}]
    assert captured["headers"]["x-api-key"] == "test-key"


def test_ollama_provider_uses_native_chat_api() -> None:
    captured: dict[str, Any] = {}

    def transport(url: str, headers: Any, payload: Any, timeout: float) -> dict[str, Any]:
        captured.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return {
            "message": {"role": "assistant", "content": "Local answer"},
            "prompt_eval_count": 40,
            "eval_count": 8,
        }

    provider = OllamaChatProvider(model="qwen3.6", transport=transport)
    result = provider.complete("Plan the fix", system_prompt="verified memory")

    assert result.text == "Local answer"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["messages"][0]["role"] == "system"


def test_local_codex_client_is_read_only_and_ephemeral() -> None:
    provider = create_provider("codex-cli", model="gpt-5.6-terra")

    assert isinstance(provider, SubprocessProvider)
    assert "read-only" in provider.command
    assert "--ephemeral" in provider.command
    assert "danger-full-access" not in provider.command


def test_subprocess_provider_sends_prompt_over_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.update(command=command, kwargs=kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="planned response\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = SubprocessProvider(name="test-client", model="test-model", command=["client"])
    result = provider.complete("current task", system_prompt="memory", cwd=Path.cwd())

    assert result.text == "planned response"
    assert "memory" in captured["kwargs"]["input"]
    assert "current task" in captured["kwargs"]["input"]
    assert captured["kwargs"]["check"] is False


def test_ollama_requires_an_explicit_model() -> None:
    with pytest.raises(ProviderError, match="model is required"):
        create_provider("ollama-api")

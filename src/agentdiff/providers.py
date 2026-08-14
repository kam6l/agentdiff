"""Provider-isolated AI clients for AgentDiff Cortex.

The adapters in this module only return model text. API adapters do not expose
tools, and local coding clients are launched in read-only/plan modes. AgentDiff
continues to use ``agentdiff run`` as the explicit mutation boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class ProviderError(RuntimeError):
    """Raised when a provider cannot be configured or returns an invalid result."""


JsonObject = dict[str, Any]
JsonTransport = Callable[[str, Mapping[str, str], Mapping[str, Any], float], JsonObject]


def _error_detail(payload: str) -> str:
    """Extract a bounded provider error without echoing request credentials."""

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return payload.strip()[:500]
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or "provider error")[:500]
        if error:
            return str(error)[:500]
        if parsed.get("message"):
            return str(parsed["message"])[:500]
    return "provider error"


def http_json_transport(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    timeout_seconds: float,
) -> JsonObject:
    """Send one JSON request with the standard library."""

    if not url.startswith(("https://", "http://")):
        raise ProviderError(f"unsupported URL scheme for provider: {url}")

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=dict(headers),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = _error_detail(exc.read().decode("utf-8", errors="replace"))
        raise ProviderError(f"provider returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"provider connection failed: {exc.reason}") from exc

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError("provider returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ProviderError("provider response must be a JSON object")
    return decoded


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Normalized response returned by every Cortex provider."""

    text: str
    provider: str
    model: str
    response_id: str = ""
    usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIProvider(Protocol):
    """Minimal provider contract used by the Cortex router."""

    name: str
    model: str

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        previous_response_id: str | None = None,
        cwd: Path | None = None,
    ) -> ProviderResponse: ...


def _require_secret(value: str | None, environment_name: str) -> str:
    secret = value or os.environ.get(environment_name)
    if not secret:
        raise ProviderError(f"missing API key; set {environment_name}")
    return secret


def _openai_text(payload: Mapping[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks: list[str] = []
    output = payload.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str) and block.get("type") in {"output_text", "text"}:
                    chunks.append(text)
    return "\n".join(chunks).strip()


def _integer_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(item) for key, item in value.items() if isinstance(item, int)}


class OpenAIResponsesProvider:
    """OpenAI Responses API adapter for Codex and current GPT models."""

    name = "openai-api"

    def __init__(
        self,
        *,
        model: str = "gpt-5.6-terra",
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        endpoint: str = "https://api.openai.com/v1/responses",
        timeout_seconds: float = 120.0,
        transport: JsonTransport = http_json_transport,
    ) -> None:
        self.model = model
        self.api_key = _require_secret(api_key, api_key_env)
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        previous_response_id: str | None = None,
        cwd: Path | None = None,
    ) -> ProviderResponse:
        del cwd
        request: JsonObject = {
            "model": self.model,
            "input": prompt,
            "reasoning": {"effort": "medium", "context": "all_turns"},
        }
        if system_prompt:
            request["instructions"] = system_prompt
        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        payload = self.transport(
            self.endpoint,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            request,
            self.timeout_seconds,
        )
        text = _openai_text(payload)
        if not text:
            raise ProviderError("OpenAI response did not contain output text")
        usage = _integer_usage(payload.get("usage"))
        return ProviderResponse(
            text=text,
            provider=self.name,
            model=str(payload.get("model") or self.model),
            response_id=str(payload.get("id") or ""),
            usage=usage,
        )


class AnthropicMessagesProvider:
    """Claude Messages API adapter."""

    name = "anthropic-api"

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-5",
        api_key: str | None = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        endpoint: str = "https://api.anthropic.com/v1/messages",
        timeout_seconds: float = 120.0,
        max_tokens: int = 8192,
        transport: JsonTransport = http_json_transport,
    ) -> None:
        self.model = model
        self.api_key = _require_secret(api_key, api_key_env)
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.transport = transport

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        previous_response_id: str | None = None,
        cwd: Path | None = None,
    ) -> ProviderResponse:
        del cwd
        if previous_response_id:
            raise ProviderError("previous_response_id is only supported by the OpenAI adapter")
        request: JsonObject = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            request["system"] = system_prompt
        payload = self.transport(
            self.endpoint,
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            request,
            self.timeout_seconds,
        )
        chunks = [
            str(block["text"])
            for block in payload.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        ]
        text = "\n".join(chunks).strip()
        if not text:
            raise ProviderError("Anthropic response did not contain text content")
        usage = _integer_usage(payload.get("usage"))
        return ProviderResponse(
            text=text,
            provider=self.name,
            model=str(payload.get("model") or self.model),
            response_id=str(payload.get("id") or ""),
            usage=usage,
        )


class OllamaChatProvider:
    """Ollama native chat API adapter."""

    name = "ollama-api"

    def __init__(
        self,
        *,
        model: str,
        endpoint: str = "http://127.0.0.1:11434/api/chat",
        timeout_seconds: float = 120.0,
        transport: JsonTransport = http_json_transport,
    ) -> None:
        if not model:
            raise ProviderError("--model is required for Ollama")
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        previous_response_id: str | None = None,
        cwd: Path | None = None,
    ) -> ProviderResponse:
        del cwd
        if previous_response_id:
            raise ProviderError("Ollama does not support previous_response_id")
        messages: list[JsonObject] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = self.transport(
            self.endpoint,
            {"Content-Type": "application/json"},
            {"model": self.model, "messages": messages, "stream": False},
            self.timeout_seconds,
        )
        message = payload.get("message", {})
        text = str(message.get("content") or "").strip() if isinstance(message, dict) else ""
        if not text:
            raise ProviderError("Ollama response did not contain message content")
        usage = {
            key: int(payload[key])
            for key in ("prompt_eval_count", "eval_count")
            if isinstance(payload.get(key), int)
        }
        return ProviderResponse(text=text, provider=self.name, model=self.model, usage=usage)


class OllamaEmbeddingProvider:
    """Optional semantic memory embedder using Ollama's native embed endpoint."""

    name = "ollama-embeddings"

    def __init__(
        self,
        *,
        model: str = "embeddinggemma",
        endpoint: str = "http://127.0.0.1:11434/api/embed",
        timeout_seconds: float = 120.0,
        transport: JsonTransport = http_json_transport,
    ) -> None:
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = self.transport(
            self.endpoint,
            {"Content-Type": "application/json"},
            {"model": self.model, "input": list(texts)},
            self.timeout_seconds,
        )
        raw = payload.get("embeddings")
        if not isinstance(raw, list) or len(raw) != len(texts):
            raise ProviderError("Ollama embedding response has an unexpected shape")
        vectors: list[list[float]] = []
        for vector in raw:
            if not isinstance(vector, list) or not vector:
                raise ProviderError("Ollama returned an empty embedding")
            vectors.append([float(value) for value in vector])
        return vectors


class SubprocessProvider:
    """Local AI client adapter that sends the complete prompt over stdin."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        command: Sequence[str],
        timeout_seconds: float = 300.0,
    ) -> None:
        self.name = name
        self.model = model
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds

    def complete(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        previous_response_id: str | None = None,
        cwd: Path | None = None,
    ) -> ProviderResponse:
        if previous_response_id:
            raise ProviderError("previous_response_id is only supported by the OpenAI adapter")
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n## Current task\n{prompt}"
        try:
            result = subprocess.run(
                self.command,
                input=full_prompt,
                text=True,
                capture_output=True,
                cwd=cwd,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ProviderError(f"client executable not found: {self.command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                f"{self.name} timed out after {self.timeout_seconds:g} seconds"
            ) from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-1000:]
            raise ProviderError(f"{self.name} exited {result.returncode}: {detail}")
        text = result.stdout.strip()
        if not text:
            raise ProviderError(f"{self.name} returned no output")
        return ProviderResponse(text=text, provider=self.name, model=self.model)


PROVIDER_NAMES = (
    "openai-api",
    "codex-api",
    "anthropic-api",
    "claude-api",
    "ollama-api",
    "codex-cli",
    "claude-cli",
    "ollama-cli",
)


def create_provider(
    name: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
    endpoint: str | None = None,
    executable: str | None = None,
    timeout_seconds: float = 120.0,
) -> AIProvider:
    """Create an API or local-client provider from CLI-friendly settings."""

    normalized = name.lower().strip()
    if normalized in {"openai-api", "codex-api"}:
        return OpenAIResponsesProvider(
            model=model or "gpt-5.6-terra",
            api_key=api_key,
            api_key_env=api_key_env or "OPENAI_API_KEY",
            endpoint=endpoint or "https://api.openai.com/v1/responses",
            timeout_seconds=timeout_seconds,
        )
    if normalized in {"anthropic-api", "claude-api"}:
        return AnthropicMessagesProvider(
            model=model or "claude-sonnet-5",
            api_key=api_key,
            api_key_env=api_key_env or "ANTHROPIC_API_KEY",
            endpoint=endpoint or "https://api.anthropic.com/v1/messages",
            timeout_seconds=timeout_seconds,
        )
    if normalized == "ollama-api":
        return OllamaChatProvider(
            model=model or "",
            endpoint=endpoint or "http://127.0.0.1:11434/api/chat",
            timeout_seconds=timeout_seconds,
        )
    if normalized == "codex-cli":
        command = [
            executable or "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--color",
            "never",
        ]
        if model:
            command.extend(["--model", model])
        command.append("-")
        return SubprocessProvider(
            name="codex-cli",
            model=model or "client-default",
            command=command,
            timeout_seconds=timeout_seconds,
        )
    if normalized == "claude-cli":
        selected_model = model or "claude-sonnet-5"
        return SubprocessProvider(
            name="claude-cli",
            model=selected_model,
            command=[
                executable or "claude",
                "--print",
                "--permission-mode",
                "plan",
                "--no-session-persistence",
                "--output-format",
                "text",
                "--model",
                selected_model,
            ],
            timeout_seconds=timeout_seconds,
        )
    if normalized == "ollama-cli":
        if not model:
            raise ProviderError("--model is required for Ollama")
        return SubprocessProvider(
            name="ollama-cli",
            model=model,
            command=[executable or "ollama", "run", model],
            timeout_seconds=timeout_seconds,
        )
    raise ProviderError(f"unknown provider {name!r}; choose one of {', '.join(PROVIDER_NAMES)}")

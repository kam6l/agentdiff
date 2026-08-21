"""OpenAI API provider detection and breaking change catalog."""

from __future__ import annotations

from agentdiff.api.models import APIChange, ChangeSeverity, ChangeType
from agentdiff.api.providers.base import APIProvider


class OpenAIProvider(APIProvider):
    """Provider for OpenAI Python SDK (v0.x legacy and v1.x modern)."""

    @property
    def name(self) -> str:
        return "openai"

    @property
    def library(self) -> str:
        return "openai"

    @property
    def import_names(self) -> frozenset[str]:
        return frozenset({"openai"})

    def get_known_changes(self) -> list[APIChange]:
        return [
            APIChange(
                change_id="openai-v1-chat-completion-create",
                provider="openai",
                title="Legacy openai.ChatCompletion.create replaced",
                change_type=ChangeType.REMOVAL,
                severity=ChangeSeverity.HIGH,
                target_symbol="openai.ChatCompletion.create",
                target_symbols=("openai.ChatCompletion.create",),
                breaking_version=">=1.0.0",
                description=(
                    "The global `openai.ChatCompletion.create()` method was removed in OpenAI"
                    " v1.0.0+. Instantiate `client = OpenAI()` and call"
                    " `client.chat.completions.create()`."
                ),
                migration_guide_url="https://github.com/openai/openai-python/discussions/742",
                replacement_symbol="client.chat.completions.create",
                replacement_code=(
                    "client = OpenAI()\n"
                    "response = client.chat.completions.create(\n"
                    "    model='gpt-4o', messages=messages\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-v1-completion-create",
                provider="openai",
                title="Legacy openai.Completion.create replaced by client.completions.create",
                change_type=ChangeType.DEPRECATION,
                severity=ChangeSeverity.HIGH,
                target_symbol="openai.Completion.create",
                target_symbols=("openai.Completion.create",),
                breaking_version=">=1.0.0",
                description=(
                    "The global `openai.Completion.create()` method was removed in OpenAI v1.0.0+."
                    " Use `client.completions.create()` with `gpt-3.5-turbo-instruct` or migrate"
                    " to `client.chat.completions.create()`."
                ),
                migration_guide_url="https://github.com/openai/openai-python/discussions/742",
                replacement_symbol="client.completions.create",
                replacement_code=(
                    "client = OpenAI()\n"
                    "response = client.completions.create(\n"
                    "    model='gpt-3.5-turbo-instruct', prompt=prompt\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-v1-embedding-create",
                provider="openai",
                title="Legacy openai.Embedding.create replaced by client.embeddings.create",
                change_type=ChangeType.REMOVAL,
                severity=ChangeSeverity.HIGH,
                target_symbol="openai.Embedding.create",
                target_symbols=("openai.Embedding.create",),
                breaking_version=">=1.0.0",
                description=(
                    "The global `openai.Embedding.create()` method was removed in OpenAI v1.0.0+."
                    " Use `client.embeddings.create()` with `text-embedding-3-small`."
                ),
                migration_guide_url="https://github.com/openai/openai-python/discussions/742",
                replacement_symbol="client.embeddings.create",
                replacement_code=(
                    "client = OpenAI()\n"
                    "response = client.embeddings.create(\n"
                    "    input=text, model='text-embedding-3-small'\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-v1-audio-transcribe",
                provider="openai",
                title="Legacy openai.Audio.transcribe replaced",
                change_type=ChangeType.REMOVAL,
                severity=ChangeSeverity.HIGH,
                target_symbol="openai.Audio.transcribe",
                target_symbols=("openai.Audio.transcribe",),
                breaking_version=">=1.0.0",
                description=(
                    "The global `openai.Audio.transcribe()` method was removed in OpenAI v1.0.0+."
                    " Use `client.audio.transcriptions.create()`."
                ),
                migration_guide_url="https://github.com/openai/openai-python/discussions/742",
                replacement_symbol="client.audio.transcriptions.create",
                replacement_code=(
                    "client = OpenAI()\n"
                    "response = client.audio.transcriptions.create(\n"
                    "    model='whisper-1', file=audio_file\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-v1-image-create",
                provider="openai",
                title="Legacy openai.Image.create replaced by client.images.generate",
                change_type=ChangeType.REMOVAL,
                severity=ChangeSeverity.HIGH,
                target_symbol="openai.Image.create",
                target_symbols=("openai.Image.create",),
                breaking_version=">=1.0.0",
                description=(
                    "The global `openai.Image.create()` method was removed in OpenAI v1.0.0+."
                    " Use `client.images.generate()` with `dall-e-3`."
                ),
                migration_guide_url="https://github.com/openai/openai-python/discussions/742",
                replacement_symbol="client.images.generate",
                replacement_code=(
                    "client = OpenAI()\n"
                    "response = client.images.generate(model='dall-e-3', prompt=prompt)"
                ),
            ),
            APIChange(
                change_id="openai-v1-model-list",
                provider="openai",
                title="Legacy openai.Model.list replaced by client.models.list",
                change_type=ChangeType.REMOVAL,
                severity=ChangeSeverity.MODERATE,
                target_symbol="openai.Model.list",
                target_symbols=("openai.Model.list",),
                breaking_version=">=1.0.0",
                description=(
                    "The global `openai.Model.list()` method was removed in OpenAI v1.0.0+."
                    " Use `client.models.list()`."
                ),
                migration_guide_url="https://github.com/openai/openai-python/discussions/742",
                replacement_symbol="client.models.list",
                replacement_code="client = OpenAI()\nmodels = client.models.list()",
            ),
            APIChange(
                change_id="openai-v1-global-api-key",
                provider="openai",
                title="Global openai.api_key setting deprecated in favor of client instantiation",
                change_type=ChangeType.DEPRECATION,
                severity=ChangeSeverity.MODERATE,
                target_symbol="openai.api_key",
                target_symbols=("openai.api_key",),
                breaking_version=">=1.0.0",
                description=(
                    "Setting `openai.api_key = '...'` globally is deprecated. Pass `api_key` to"
                    " `OpenAI(api_key=...)` or set the `OPENAI_API_KEY` environment variable."
                ),
                migration_guide_url="https://github.com/openai/openai-python/discussions/742",
                replacement_symbol="OpenAI(api_key=...)",
                replacement_code="client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])",
            ),
            APIChange(
                change_id="openai-deprecated-functions-parameter",
                provider="openai",
                title="`functions` deprecated in favor of `tools` and `tool_choice`",
                change_type=ChangeType.PARAMETER_REMOVAL,
                severity=ChangeSeverity.HIGH,
                target_symbol="client.chat.completions.create",
                target_symbols=(
                    "client.chat.completions.create",
                    "openai.ChatCompletion.create",
                ),
                target_parameter="functions",
                breaking_version=">=1.0.0",
                description=(
                    "The `functions` parameter in chat completions is deprecated. Use"
                    " `tools=[{'type': 'function', 'function': ...}]` and `tool_choice` instead."
                ),
                migration_guide_url="https://platform.openai.com/docs/guides/function-calling",
                replacement_symbol="tools",
                replacement_code=(
                    "response = client.chat.completions.create(\n"
                    "    model='gpt-4o',\n"
                    "    messages=messages,\n"
                    "    tools=[{'type': 'function', 'function': my_function_def}],\n"
                    "    tool_choice='auto',\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-deprecated-engine-parameter",
                provider="openai",
                title="`engine` parameter removed in favor of `model`",
                change_type=ChangeType.PARAMETER_REMOVAL,
                severity=ChangeSeverity.CRITICAL,
                target_symbol="client.completions.create",
                target_symbols=(
                    "client.chat.completions.create",
                    "client.completions.create",
                    "openai.ChatCompletion.create",
                    "openai.Completion.create",
                ),
                target_parameter="engine",
                breaking_version=">=1.0.0",
                description=(
                    "The legacy `engine` parameter has been removed from completion calls."
                    " Use `model` instead."
                ),
                migration_guide_url="https://platform.openai.com/docs/models",
                replacement_symbol="model",
                replacement_code=(
                    "response = client.chat.completions.create(\n"
                    "    model='gpt-4o', messages=messages\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-shutdown-model-davinci-003",
                provider="openai",
                title="Shutdown model `text-davinci-003`",
                change_type=ChangeType.MODEL_DEPRECATION,
                severity=ChangeSeverity.CRITICAL,
                target_symbol="client.completions.create",
                target_symbols=(
                    "client.chat.completions.create",
                    "client.completions.create",
                    "openai.ChatCompletion.create",
                    "openai.Completion.create",
                ),
                target_model="text-davinci-003",
                description=(
                    "`text-davinci-003` was shut down on January 4, 2024. Migrate to"
                    " `gpt-3.5-turbo-instruct` or chat models like `gpt-4o-mini`."
                ),
                migration_guide_url="https://platform.openai.com/docs/deprecations",
                replacement_symbol="gpt-3.5-turbo-instruct",
                replacement_code=(
                    "response = client.chat.completions.create(\n"
                    "    model='gpt-4o-mini',\n"
                    "    messages=[{'role': 'user', 'content': prompt}],\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-shutdown-model-code-davinci-002",
                provider="openai",
                title="Shutdown model `code-davinci-002`",
                change_type=ChangeType.MODEL_DEPRECATION,
                severity=ChangeSeverity.CRITICAL,
                target_symbol="client.completions.create",
                target_symbols=(
                    "client.chat.completions.create",
                    "client.completions.create",
                    "openai.ChatCompletion.create",
                    "openai.Completion.create",
                ),
                target_model="code-davinci-002",
                description=(
                    "`code-davinci-002` was shut down. Migrate to `gpt-4o` or `gpt-4o-mini`."
                ),
                migration_guide_url="https://platform.openai.com/docs/deprecations",
                replacement_symbol="gpt-4o-mini",
                replacement_code=(
                    "response = client.chat.completions.create(\n"
                    "    model='gpt-4o-mini', messages=messages\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-deprecated-snapshot-gpt35-0301",
                provider="openai",
                title="Deprecated snapshot `gpt-3.5-turbo-0301`",
                change_type=ChangeType.MODEL_DEPRECATION,
                severity=ChangeSeverity.HIGH,
                target_symbol="client.chat.completions.create",
                target_symbols=(
                    "client.chat.completions.create",
                    "client.completions.create",
                    "openai.ChatCompletion.create",
                    "openai.Completion.create",
                ),
                target_model="gpt-3.5-turbo-0301",
                description=(
                    "The `gpt-3.5-turbo-0301` snapshot has reached end of life."
                    " Migrate to `gpt-3.5-turbo` or `gpt-4o-mini`."
                ),
                migration_guide_url="https://platform.openai.com/docs/deprecations",
                replacement_symbol="gpt-4o-mini",
                replacement_code=(
                    "response = client.chat.completions.create(\n"
                    "    model='gpt-4o-mini', messages=messages\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-deprecated-snapshot-gpt4-0314",
                provider="openai",
                title="Deprecated snapshot `gpt-4-0314`",
                change_type=ChangeType.MODEL_DEPRECATION,
                severity=ChangeSeverity.HIGH,
                target_symbol="client.chat.completions.create",
                target_symbols=(
                    "client.chat.completions.create",
                    "client.completions.create",
                    "openai.ChatCompletion.create",
                    "openai.Completion.create",
                ),
                target_model="gpt-4-0314",
                description=(
                    "The `gpt-4-0314` snapshot has reached end of life."
                    " Migrate to `gpt-4o` or `gpt-4-turbo`."
                ),
                migration_guide_url="https://platform.openai.com/docs/deprecations",
                replacement_symbol="gpt-4o",
                replacement_code=(
                    "response = client.chat.completions.create(\n"
                    "    model='gpt-4o', messages=messages\n"
                    ")"
                ),
            ),
            APIChange(
                change_id="openai-chat-to-responses",
                provider="openai",
                title="Migrate from Chat Completions to Responses API",
                change_type=ChangeType.DEPRECATION,
                severity=ChangeSeverity.HIGH,
                target_symbol="client.chat.completions.create",
                target_symbols=("client.chat.completions.create",),
                breaking_version="",
                description=(
                    "The Chat Completions API is being superseded by the Responses API. "
                    "The Responses API provides a unified interface for chat, tool use, "
                    "and multi-turn conversations with better streaming and state management."
                ),
                migration_guide_url="https://platform.openai.com/docs/guides/responses-api/migration",
                replacement_symbol="client.responses.create",
                replacement_code=(
                    "response = client.responses.create(\n    model='gpt-4o', input=messages\n)"
                ),
            ),
        ]

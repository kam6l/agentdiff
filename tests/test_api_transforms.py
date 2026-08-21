"""Tests for migration transforms."""

from __future__ import annotations

import ast

from agentdiff.api.models import APIUsage
from agentdiff.api.transforms import (
    OpenAIChatToResponsesTransform,
    OpenAILegacyChatCompletionTransform,
    get_transform,
    get_transforms_for_usage,
)
from agentdiff.api.transforms.base import TransformContext


class TestTransformRegistry:
    """Test transform registry."""

    def test_openai_chat_to_responses_registered(self) -> None:
        transform = get_transform("openai-chat-to-responses")
        assert transform is not None
        assert isinstance(transform, OpenAIChatToResponsesTransform)
        assert transform.provider == "openai"
        assert "client.chat.completions.create" in transform.affected_symbols

    def test_openai_legacy_registered(self) -> None:
        transform = get_transform("openai-legacy-chat-completion")
        assert transform is not None
        assert isinstance(transform, OpenAILegacyChatCompletionTransform)
        assert "openai.ChatCompletion.create" in transform.affected_symbols

    def test_get_transforms_for_usage(self) -> None:
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="client.chat.completions.create",
            call_type="call",
            filepath="test.py",
            line_number=1,
        )
        transforms = get_transforms_for_usage(usage)
        assert len(transforms) >= 1
        assert any(t.transform_id == "openai-chat-to-responses" for t in transforms)


class TestOpenAIChatToResponsesTransform:
    """Test the Chat Completions to Responses API transform."""

    def test_simple_migration(self) -> None:
        code = """
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
)
print(response.choices[0].message.content)
"""
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="client.chat.completions.create",
            call_type="call",
            filepath="test.py",
            line_number=3,
        )
        transform = OpenAIChatToResponsesTransform()
        context = TransformContext(
            usage=usage,
            source_code=code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage,),
        )

        result = transform.transform(context)

        assert result.success
        assert "client.responses.create" in result.modified_code
        assert "client.chat.completions.create" not in result.modified_code
        assert "model=" in result.modified_code
        assert "input=" in result.modified_code

    def test_tools_require_review(self) -> None:
        code = """
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
    tools=[{"type": "function", "function": {"name": "test"}}],
    tool_choice="auto",
)
print(response.choices[0].message.content)
"""
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="client.chat.completions.create",
            call_type="call",
            filepath="test.py",
            line_number=3,
        )
        transform = OpenAIChatToResponsesTransform()
        context = TransformContext(
            usage=usage,
            source_code=code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage,),
        )

        assert transform.can_transform(context) is False
        assert "unsupported request parameters" in transform.explain_changes(context)

    def test_migration_preserves_other_params(self) -> None:
        code = """
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
    temperature=0.7,
    max_tokens=1000,
)
print(response.choices[0].message.content)
"""
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="client.chat.completions.create",
            call_type="call",
            filepath="test.py",
            line_number=3,
        )
        transform = OpenAIChatToResponsesTransform()
        context = TransformContext(
            usage=usage,
            source_code=code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage,),
        )

        result = transform.transform(context)

        assert result.success
        assert "temperature=0.7" in result.modified_code
        assert "max_output_tokens=1000" in result.modified_code
        assert "response.output_text" in result.modified_code

    def test_streaming_and_multimodal_require_review(self) -> None:
        code = """
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
    stream=True,
)
print(response.choices[0].message.content)
"""
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="client.chat.completions.create",
            call_type="call",
            filepath="test.py",
            line_number=3,
        )
        transform = OpenAIChatToResponsesTransform()
        context = TransformContext(usage, code, "test.py", None, (usage,))

        assert transform.can_transform(context) is False
        explanation = transform.explain_changes(context)
        assert "stream" in explanation
        assert "text-only literal" in explanation

    def test_async_call_and_output_are_migrated(self) -> None:
        code = """
async def ask(client, prompt: str) -> str:
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        store=False,
    )
    return response.choices[0].message.content
"""
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="client.chat.completions.create",
            call_type="call",
            filepath="test.py",
            line_number=3,
        )
        transform = OpenAIChatToResponsesTransform()
        context = TransformContext(usage, code, "test.py", None, (usage,))

        result = transform.transform(context)

        assert result.success
        assert "await client.responses.create" in result.modified_code
        assert "return response.output_text" in result.modified_code
        assert "store=False" in result.modified_code

    def test_unrelated_code_unchanged(self) -> None:
        code = """import openai
client = openai.OpenAI()

def other_function():
    return client.embeddings.create(model="text-embedding-3-small", input="test")
"""
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="client.embeddings.create",
            call_type="call",
            filepath="test.py",
            line_number=5,
        )
        transform = OpenAIChatToResponsesTransform()
        context = TransformContext(
            usage=usage,
            source_code=code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage,),
        )

        result = transform.transform(context)

        # Should not modify since it's not the target symbol
        assert result.success
        assert "Transform not applicable" in result.changes[0]
        assert result.modified_code.strip() == code.strip()


class TestOpenAILegacyChatCompletionTransform:
    """Test the legacy ChatCompletion.create to modern migration."""

    def test_legacy_migration(self) -> None:
        code = """
import openai

response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "hello"}],
)
"""
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="openai.ChatCompletion.create",
            call_type="call",
            filepath="test.py",
            line_number=4,
        )
        transform = OpenAILegacyChatCompletionTransform()
        context = TransformContext(
            usage=usage,
            source_code=code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage,),
        )

        assert transform.can_transform(context) is False
        assert "Needs review" in transform.explain_changes(context)

    def test_legacy_with_functions(self) -> None:
        code = """
import openai

response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "hello"}],
    functions=[{"name": "test", "parameters": {}}],
)
"""
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="openai.ChatCompletion.create",
            call_type="call",
            filepath="test.py",
            line_number=4,
        )
        transform = OpenAILegacyChatCompletionTransform()
        context = TransformContext(
            usage=usage,
            source_code=code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage,),
        )

        assert transform.can_transform(context) is False

    def test_syntax_preservation(self) -> None:
        """Ensure the transformed code is syntactically valid."""
        code = """
import openai

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "hello"},
    ],
    temperature=0.5,
)
"""
        usage = APIUsage(
            provider="openai",
            library="openai",
            symbol="openai.ChatCompletion.create",
            call_type="call",
            filepath="test.py",
            line_number=4,
        )
        transform = OpenAILegacyChatCompletionTransform()
        context = TransformContext(
            usage=usage,
            source_code=code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage,),
        )

        result = transform.transform(context)

        assert result.success
        assert result.modified_code.strip() == code.strip()
        ast.parse(result.modified_code)


class TestTransformIntegration:
    """Integration tests for transforms."""

    def test_multiple_usages_in_file(self) -> None:
        code = """
import openai
client = openai.OpenAI()

def ask(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content

def ask_again(prompt):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content
"""
        usage1 = APIUsage(
            provider="openai",
            library="openai",
            symbol="client.chat.completions.create",
            call_type="call",
            filepath="test.py",
            line_number=5,
        )
        usage2 = APIUsage(
            provider="openai",
            library="openai",
            symbol="client.chat.completions.create",
            call_type="call",
            filepath="test.py",
            line_number=11,
        )
        transform = OpenAIChatToResponsesTransform()

        # The file-level transform migrates both compatible usages atomically.
        context1 = TransformContext(
            usage=usage1,
            source_code=code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage1, usage2),
        )
        result1 = transform.transform(context1)
        assert result1.success

        assert result1.modified_code.count("client.responses.create") == 2
        assert result1.modified_code.count(".output_text") == 2
        assert "client.chat.completions.create" not in result1.modified_code

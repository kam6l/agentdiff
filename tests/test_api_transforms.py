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

    def test_migration_with_tools(self) -> None:
        code = """
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
    tools=[{"type": "function", "function": {"name": "test"}}],
    tool_choice="auto",
)
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
        assert "tools=" in result.modified_code
        assert "tool_choice=" in result.modified_code

    def test_migration_preserves_other_params(self) -> None:
        code = """
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hello"}],
    temperature=0.7,
    max_tokens=1000,
)
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
        assert "max_tokens=1000" in result.modified_code

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

        result = transform.transform(context)

        assert result.success
        assert "client.chat.completions.create" in result.modified_code
        assert "openai.ChatCompletion.create" not in result.modified_code

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

        result = transform.transform(context)

        assert result.success
        assert "client.chat.completions.create" in result.modified_code
        # functions should be converted to tools
        assert "tools=" in result.modified_code

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
        # Verify the result is valid Python
        ast.parse(result.modified_code)


class TestTransformIntegration:
    """Integration tests for transforms."""

    def test_multiple_usages_in_file(self) -> None:
        code = """
import openai
client = openai.OpenAI()

def ask(prompt):
    return client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )

def ask_tools(prompt):
    return client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        tools=[{"type": "function"}],
    )
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

        # Transform first usage
        context1 = TransformContext(
            usage=usage1,
            source_code=code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage1, usage2),
        )
        result1 = transform.transform(context1)
        assert result1.success

        # Transform second usage on the modified code
        context2 = TransformContext(
            usage=usage2,
            source_code=result1.modified_code,
            filepath="test.py",
            manifest=None,
            all_usages=(usage1, usage2),
        )
        result2 = transform.transform(context2)
        assert result2.success

        # Both should be migrated
        assert result2.modified_code.count("client.responses.create") == 2
        assert "client.chat.completions.create" not in result2.modified_code

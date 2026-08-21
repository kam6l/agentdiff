"""Fail-closed OpenAI API migration transforms.

The deterministic transform intentionally covers only the compatibility case
documented by OpenAI: non-streaming, non-tool, text-message requests whose
result is consumed through ``choices[0].message.content``. Everything else is
left for an external generator and the normal proof pipeline.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass

from agentdiff.api.transforms.base import (
    ASTMigrationTransform,
    TransformContext,
    register_transform,
)

_PARAMETER_MAP = {
    "model": "model",
    "messages": "input",
    "store": "store",
    "temperature": "temperature",
    "top_p": "top_p",
    "max_tokens": "max_output_tokens",
    "max_completion_tokens": "max_output_tokens",
}


def _is_chat_completions_create(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    completions = node.func.value
    chat = completions.value if isinstance(completions, ast.Attribute) else None
    return (
        node.func.attr == "create"
        and isinstance(completions, ast.Attribute)
        and completions.attr == "completions"
        and isinstance(chat, ast.Attribute)
        and chat.attr == "chat"
    )


def _client_expression(node: ast.Call) -> ast.expr | None:
    if not _is_chat_completions_create(node):
        return None
    assert isinstance(node.func, ast.Attribute)
    completions = node.func.value
    assert isinstance(completions, ast.Attribute)
    chat = completions.value
    assert isinstance(chat, ast.Attribute)
    client = chat.value
    if not isinstance(client, (ast.Name, ast.Attribute)):
        return None
    return client


def _is_simple_messages(node: ast.expr) -> bool:
    """Return true only for a literal list of text-message dictionaries."""

    if not isinstance(node, (ast.List, ast.Tuple)):
        return False
    for item in node.elts:
        if not isinstance(item, ast.Dict) or len(item.keys) != len(item.values):
            return False
        fields: dict[str, ast.expr] = {}
        for key, value in zip(item.keys, item.values, strict=True):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                return False
            fields[key.value] = value
        if set(fields) != {"role", "content"}:
            return False
        role = fields["role"]
        if not (
            isinstance(role, ast.Constant)
            and role.value in {"system", "developer", "user", "assistant"}
        ):
            return False
        if isinstance(fields["content"], (ast.Dict, ast.List, ast.Set, ast.Tuple)):
            return False
    return True


def _output_text_base(node: ast.Attribute) -> ast.Name | None:
    """Match ``name.choices[0].message.content`` exactly."""

    if node.attr != "content" or not isinstance(node.value, ast.Attribute):
        return None
    message = node.value
    if message.attr != "message" or not isinstance(message.value, ast.Subscript):
        return None
    choice = message.value
    if not isinstance(choice.slice, ast.Constant) or choice.slice.value != 0:
        return None
    choices = choice.value
    if (
        not isinstance(choices, ast.Attribute)
        or choices.attr != "choices"
        or not isinstance(choices.value, ast.Name)
    ):
        return None
    return choices.value


@dataclass(frozen=True, slots=True)
class _CompatibilityAnalysis:
    compatible: bool
    response_names: frozenset[str] = frozenset()
    reasons: tuple[str, ...] = ()


def _analyze(source: str) -> _CompatibilityAnalysis:
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return _CompatibilityAnalysis(False, reasons=(f"syntax error: {error}",))

    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    calls = [node for node in ast.walk(tree) if _is_chat_completions_create(node)]
    if not calls:
        return _CompatibilityAnalysis(False, reasons=("no Chat Completions call found",))

    response_names: set[str] = set()
    reasons: list[str] = []
    call_assignments: set[ast.Name] = set()
    for generic_call in calls:
        assert isinstance(generic_call, ast.Call)
        call = generic_call
        if _client_expression(call) is None:
            reasons.append("client expression is dynamic")
        if call.args:
            reasons.append("positional request arguments are ambiguous")
        keyword_names = [keyword.arg for keyword in call.keywords]
        if any(name is None for name in keyword_names):
            reasons.append("expanded keyword arguments are ambiguous")
        named = [name for name in keyword_names if name is not None]
        if len(named) != len(set(named)):
            reasons.append("duplicate request parameters are ambiguous")
        unsupported = sorted(set(named) - set(_PARAMETER_MAP))
        if unsupported:
            reasons.append("unsupported request parameters: " + ", ".join(unsupported))
        if "model" not in named or "messages" not in named:
            reasons.append("model and messages must be explicit keyword arguments")
        if "max_tokens" in named and "max_completion_tokens" in named:
            reasons.append("multiple token limits map to max_output_tokens")
        messages = next(
            (keyword.value for keyword in call.keywords if keyword.arg == "messages"), None
        )
        if messages is not None and not _is_simple_messages(messages):
            reasons.append("messages are not a statically proven text-only literal")

        value: ast.AST = call
        parent = parents.get(value)
        if isinstance(parent, ast.Await):
            value = parent
            parent = parents.get(value)
        target: ast.Name | None = None
        if isinstance(parent, ast.Assign) and len(parent.targets) == 1:
            candidate = parent.targets[0]
            target = candidate if isinstance(candidate, ast.Name) else None
        elif isinstance(parent, ast.AnnAssign):
            target = parent.target if isinstance(parent.target, ast.Name) else None
        if target is None:
            reasons.append("response must be assigned to one local name")
        else:
            response_names.add(target.id)
            call_assignments.add(target)

    output_names = {
        base.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and (base := _output_text_base(node)) is not None
    }
    for response_name in sorted(response_names - output_names):
        reasons.append(f"{response_name} is not read through choices[0].message.content")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or node.id not in response_names:
            continue
        if isinstance(node.ctx, ast.Store):
            if node not in call_assignments:
                reasons.append(f"{node.id} is reassigned")
            continue
        current: ast.AST = node
        while isinstance(parents.get(current), (ast.Attribute, ast.Subscript)):
            current = parents[current]
        if not (isinstance(current, ast.Attribute) and _output_text_base(current) is node):
            reasons.append(f"{node.id} has unsupported response-object consumers")

    return _CompatibilityAnalysis(
        not reasons,
        response_names=frozenset(response_names),
        reasons=tuple(dict.fromkeys(reasons)),
    )


class _ChatToResponsesTransformer(ast.NodeTransformer):
    """Rewrite only shapes accepted by :func:`_analyze`."""

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        base = _output_text_base(node)
        if base is not None:
            return ast.copy_location(
                ast.Attribute(value=copy.deepcopy(base), attr="output_text", ctx=node.ctx),
                node,
            )
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        if not _is_chat_completions_create(node):
            return self.generic_visit(node)
        client = _client_expression(node)
        if client is None:
            return node
        keywords = [
            ast.keyword(arg=_PARAMETER_MAP[keyword.arg], value=self.visit(keyword.value))
            for keyword in node.keywords
            if keyword.arg is not None
        ]
        responses = ast.Attribute(
            value=copy.deepcopy(client),
            attr="responses",
            ctx=ast.Load(),
        )
        create = ast.Attribute(value=responses, attr="create", ctx=ast.Load())
        return ast.copy_location(ast.Call(func=create, args=[], keywords=keywords), node)


class OpenAIChatToResponsesTransform(ASTMigrationTransform):
    """Migrate a proven-compatible Python Chat Completions text call."""

    transform_id = "openai-chat-to-responses"
    provider = "openai"
    affected_symbols = ("client.chat.completions.create",)

    def can_transform(self, context: TransformContext) -> bool:
        return (
            context.usage.symbol in self.affected_symbols
            and bool(context.source_code)
            and _analyze(context.source_code).compatible
        )

    def _create_transformer(self, context: TransformContext) -> ast.NodeTransformer:
        del context
        return _ChatToResponsesTransformer()

    def explain_changes(self, context: TransformContext) -> str:
        analysis = _analyze(context.source_code)
        if not analysis.compatible:
            return "Needs review: " + "; ".join(analysis.reasons)
        return (
            "Map chat.completions.create to responses.create, messages to input, "
            "token limits to max_output_tokens, and choices[0].message.content "
            "to output_text."
        )


class OpenAILegacyChatCompletionTransform(ASTMigrationTransform):
    """Registered compatibility marker for a migration that requires review."""

    transform_id = "openai-legacy-chat-completion"
    provider = "openai"
    affected_symbols = ("openai.ChatCompletion.create",)

    def can_transform(self, context: TransformContext) -> bool:
        del context
        return False

    def _create_transformer(self, context: TransformContext) -> ast.NodeTransformer:
        del context
        return ast.NodeTransformer()

    def explain_changes(self, context: TransformContext) -> str:
        del context
        return (
            "Needs review: the legacy call requires import/client construction and "
            "function/tool schema handling that cannot be inferred safely."
        )


register_transform(OpenAIChatToResponsesTransform())
register_transform(OpenAILegacyChatCompletionTransform())

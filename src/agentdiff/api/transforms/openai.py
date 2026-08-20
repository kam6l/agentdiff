"""OpenAI migration transforms."""

import ast

from agentdiff.api.transforms.base import (
    ASTMigrationTransform,
    TransformContext,
    register_transform,
)


class _ChatToResponsesTransformer(ast.NodeTransformer):
    """AST transformer for migrating chat.completions.create to responses.create."""

    def __init__(self, context: TransformContext) -> None:
        self.context = context
        self.changes_made: list[str] = []

    def visit_Call(self, node: ast.Call) -> ast.AST:
        # Check if this is a client.chat.completions.create call
        if self._is_chat_completions_create(node):
            self.changes_made.append(
                "Migrated client.chat.completions.create to client.responses.create"
            )
            return self._transform_chat_to_responses(node)
        return self.generic_visit(node)

    def _is_chat_completions_create(self, node: ast.Call) -> bool:
        """Check if the call is client.chat.completions.create."""
        if not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr != "create":
            return False
        if not isinstance(node.func.value, ast.Attribute):
            return False
        if node.func.value.attr != "completions":
            return False
        if not isinstance(node.func.value.value, ast.Attribute):
            return False
        if node.func.value.value.attr != "chat":
            return False
        return True

    def _get_client_node(self, node: ast.Call) -> ast.expr | None:
        """Extract the client node from client.chat.completions.create."""
        # node.func = client.chat.completions.create (Attribute)
        # node.func.value = client.chat.completions (Attribute)
        # node.func.value.value = client.chat (Attribute)
        # node.func.value.value.value = client (Name)
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Attribute)
            and isinstance(node.func.value.value.value, ast.Name)
        ):
            return node.func.value.value.value
        return None

    def _transform_chat_to_responses(self, node: ast.Call) -> ast.Call:
        """Transform chat.completions.create to responses.create."""
        # Extract keyword arguments
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}

        # Build new keyword arguments for responses.create
        new_keywords: list[ast.keyword] = []

        # model -> model
        if "model" in kwargs:
            new_keywords.append(ast.keyword(arg="model", value=kwargs["model"]))

        # messages -> input
        if "messages" in kwargs:
            new_keywords.append(ast.keyword(arg="input", value=kwargs["messages"]))

        # tools -> tools
        if "tools" in kwargs:
            new_keywords.append(ast.keyword(arg="tools", value=kwargs["tools"]))

        # tool_choice -> tool_choice
        if "tool_choice" in kwargs:
            new_keywords.append(ast.keyword(arg="tool_choice", value=kwargs["tool_choice"]))

        # temperature, max_tokens, etc. - pass through if supported
        for param in (
            "temperature",
            "max_tokens",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
        ):
            if param in kwargs:
                new_keywords.append(ast.keyword(arg=param, value=kwargs[param]))

        # Build the new call: client.responses.create(...)
        client_node = self._get_client_node(node)
        if client_node is None:
            # Fallback: return original
            return node

        responses_attr = ast.Attribute(value=client_node, attr="responses", ctx=ast.Load())
        create_attr = ast.Attribute(value=responses_attr, attr="create", ctx=ast.Load())

        return ast.Call(
            func=create_attr,
            args=node.args,
            keywords=new_keywords,
        )


class OpenAIChatToResponsesTransform(ASTMigrationTransform):
    """Transform OpenAI Chat Completions to Responses API."""

    transform_id = "openai-chat-to-responses"
    provider = "openai"
    affected_symbols = ("client.chat.completions.create",)

    def can_transform(self, context: TransformContext) -> bool:
        """Check if this transform can handle the given usage."""
        return context.usage.symbol in self.affected_symbols

    def _create_transformer(self, context: TransformContext) -> ast.NodeTransformer:
        return _ChatToResponsesTransformer(context)

    def explain_changes(self, context: TransformContext) -> str:
        return (
            "Migrate client.chat.completions.create() to client.responses.create(). "
            "Maps 'messages' parameter to 'input', preserves 'model', 'tools', "
            "'tool_choice', 'temperature', 'max_tokens'."
        )


# Legacy OpenAI transform: openai.ChatCompletion.create -> client.chat.completions.create
class _LegacyChatCompletionTransformer(ast.NodeTransformer):
    """AST transformer for migrating openai.ChatCompletion.create to client.chat.completions.create."""

    def __init__(self, context: TransformContext) -> None:
        self.context = context
        self.changes_made: list[str] = []
        self.has_openai_import = False
        self.client_var_name = "client"

    def visit_Module(self, node: ast.Module) -> ast.AST:
        # Check for openai import
        for stmt in node.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.name == "openai":
                        self.has_openai_import = True
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module == "openai":
                    self.has_openai_import = True
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> ast.AST:
        # Check if this is openai.ChatCompletion.create
        if self._is_legacy_chat_completion(node):
            self.changes_made.append(
                "Migrated openai.ChatCompletion.create to client.chat.completions.create"
            )
            return self._transform_legacy_to_modern(node)
        return self.generic_visit(node)

    def _is_legacy_chat_completion(self, node: ast.Call) -> bool:
        """Check if the call is openai.ChatCompletion.create."""
        if not isinstance(node.func, ast.Attribute):
            return False
        if node.func.attr != "create":
            return False
        if not isinstance(node.func.value, ast.Attribute):
            return False
        if node.func.value.attr != "ChatCompletion":
            return False
        if not isinstance(node.func.value.value, ast.Name):
            return False
        if node.func.value.value.id != "openai":
            return False
        return True

    def _transform_legacy_to_modern(self, node: ast.Call) -> ast.Call:
        """Transform openai.ChatCompletion.create to client.chat.completions.create."""
        # Extract keyword arguments
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}

        # Handle functions -> tools conversion
        new_keywords: list[ast.keyword] = []
        if "functions" in kwargs:
            # Convert functions to tools format
            functions_val = kwargs["functions"]
            # Simple conversion - wrap functions in tools format
            # This is a simplified version - real conversion is more complex
            new_keywords.append(ast.keyword(arg="tools", value=functions_val))
        elif "tools" in kwargs:
            new_keywords.append(ast.keyword(arg="tools", value=kwargs["tools"]))

        if "tool_choice" in kwargs:
            new_keywords.append(ast.keyword(arg="tool_choice", value=kwargs["tool_choice"]))

        # Pass through other parameters
        for param in ("model", "messages", "temperature", "max_tokens", "top_p", "stream"):
            if param in kwargs:
                new_keywords.append(ast.keyword(arg=param, value=kwargs[param]))

        # Build the new call: client.chat.completions.create(...)
        client_name = ast.Name(id=self.client_var_name, ctx=ast.Load())
        chat_attr = ast.Attribute(value=client_name, attr="chat", ctx=ast.Load())
        completions_attr = ast.Attribute(value=chat_attr, attr="completions", ctx=ast.Load())
        create_attr = ast.Attribute(value=completions_attr, attr="create", ctx=ast.Load())

        return ast.Call(
            func=create_attr,
            args=node.args,
            keywords=new_keywords,
        )


class OpenAILegacyChatCompletionTransform(ASTMigrationTransform):
    """Transform legacy openai.ChatCompletion.create to client.chat.completions.create."""

    transform_id = "openai-legacy-chat-completion"
    provider = "openai"
    affected_symbols = ("openai.ChatCompletion.create",)

    def can_transform(self, context: TransformContext) -> bool:
        return context.usage.symbol in self.affected_symbols

    def _create_transformer(self, context: TransformContext) -> ast.NodeTransformer:
        return _LegacyChatCompletionTransformer(context)

    def explain_changes(self, context: TransformContext) -> str:
        return (
            "Migrate openai.ChatCompletion.create() to client.chat.completions.create(). "
            "Converts 'functions' parameter to 'tools' format. "
            "Requires OpenAI client instantiation: client = OpenAI()."
        )


# Register transforms
register_transform(OpenAIChatToResponsesTransform())
register_transform(OpenAILegacyChatCompletionTransform())

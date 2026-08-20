"""Migration transforms for API changes."""

# Import provider-specific transforms to register them
from agentdiff.api.transforms import stripe  # noqa: F401
from agentdiff.api.transforms.base import (
    ASTMigrationTransform,
    MigrationTransform,
    TransformContext,
    TransformRegistry,
    TransformResult,
    get_transform,
    get_transforms_for_usage,
    list_transforms,
    register_transform,
)

# Import provider-specific transforms to register them
from agentdiff.api.transforms.openai import (
    OpenAIChatToResponsesTransform,
    OpenAILegacyChatCompletionTransform,
)

__all__ = [
    "ASTMigrationTransform",
    "MigrationTransform",
    "OpenAIChatToResponsesTransform",
    "OpenAILegacyChatCompletionTransform",
    "TransformContext",
    "TransformRegistry",
    "TransformResult",
    "get_transform",
    "get_transforms_for_usage",
    "list_transforms",
    "register_transform",
]

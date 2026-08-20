"""Base classes for API migration transforms."""

from __future__ import annotations

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentdiff.api.models import APIUsage


@dataclass(frozen=True, slots=True)
class TransformResult:
    """Result of applying a migration transform."""

    success: bool
    modified_code: str
    original_code: str
    filepath: str
    changes: tuple[str, ...]  # descriptions of changes made
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransformContext:
    """Context provided to transforms during migration."""

    usage: APIUsage
    source_code: str
    filepath: str
    manifest: Any  # APIChangeManifest - avoid circular import
    all_usages: tuple[APIUsage, ...]


class MigrationTransform(ABC):
    """Abstract base class for migration transforms."""

    @property
    @abstractmethod
    def transform_id(self) -> str:
        """Unique identifier for this transform."""
        ...

    @property
    @abstractmethod
    def provider(self) -> str:
        """API provider this transform applies to (e.g., 'openai', 'stripe')."""
        ...

    @property
    @abstractmethod
    def affected_symbols(self) -> tuple[str, ...]:
        """Symbols this transform can migrate."""
        ...

    @abstractmethod
    def can_transform(self, context: TransformContext) -> bool:
        """Check if this transform can handle the given usage."""
        ...

    @abstractmethod
    def transform(self, context: TransformContext) -> TransformResult:
        """Apply the migration transform to the source code."""
        ...

    def explain_changes(self, context: TransformContext) -> str:
        """Return human-readable description of what this transform does."""
        return f"Apply {self.transform_id} to {context.usage.symbol}"


class ASTMigrationTransform(MigrationTransform):
    """Base class for AST-based deterministic transforms."""

    def transform(self, context: TransformContext) -> TransformResult:
        """Parse source, apply AST transform, and return modified code."""
        # First check if this transform can handle the usage
        if not self.can_transform(context):
            return TransformResult(
                success=True,
                modified_code=context.source_code,
                original_code=context.source_code,
                filepath=context.filepath,
                changes=("Transform not applicable to this usage",),
            )

        try:
            tree = ast.parse(context.source_code, filename=context.filepath)
        except SyntaxError as e:
            return TransformResult(
                success=False,
                modified_code=context.source_code,
                original_code=context.source_code,
                filepath=context.filepath,
                changes=(f"Syntax error in source: {e}",),
                metadata={"error": str(e)},
            )

        # Apply the transform
        transformer = self._create_transformer(context)
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)

        # Convert back to source code
        try:
            modified_code = ast.unparse(new_tree)
        except (TypeError, ValueError, AttributeError, RecursionError) as e:
            return TransformResult(
                success=False,
                modified_code=context.source_code,
                original_code=context.source_code,
                filepath=context.filepath,
                changes=(f"Failed to unparse AST: {e}",),
                metadata={"error": str(e)},
            )

        if modified_code == context.source_code:
            return TransformResult(
                success=True,
                modified_code=modified_code,
                original_code=context.source_code,
                filepath=context.filepath,
                changes=("No changes needed",),
            )

        changes = self._describe_changes(context.source_code, modified_code, context)
        return TransformResult(
            success=True,
            modified_code=modified_code,
            original_code=context.source_code,
            filepath=context.filepath,
            changes=changes,
            metadata={"transform_id": self.transform_id},
        )

    @abstractmethod
    def _create_transformer(self, context: TransformContext) -> ast.NodeTransformer:
        """Create the AST node transformer for this migration."""
        ...

    def _describe_changes(
        self, original: str, modified: str, context: TransformContext
    ) -> tuple[str, ...]:
        """Describe the changes made."""
        orig_lines = original.splitlines()
        mod_lines = modified.splitlines()
        changes: list[str] = []

        # Simple diff - find changed lines
        for i, (orig, mod) in enumerate(zip(orig_lines, mod_lines, strict=False)):
            if orig != mod:
                changes.append(f"Line {i + 1}: {orig.strip()} -> {mod.strip()}")

        # Handle added/removed lines
        if len(mod_lines) > len(orig_lines):
            for i in range(len(orig_lines), len(mod_lines)):
                changes.append(f"Line {i + 1} added: {mod_lines[i].strip()}")
        elif len(orig_lines) > len(mod_lines):
            for i in range(len(mod_lines), len(orig_lines)):
                changes.append(f"Line {i + 1} removed: {orig_lines[i].strip()}")

        return tuple(changes) if changes else ("Code modified",)


class TransformRegistry:
    """Registry of available migration transforms."""

    def __init__(self) -> None:
        self._transforms: dict[str, MigrationTransform] = {}

    def register(self, transform: MigrationTransform) -> None:
        """Register a transform."""
        self._transforms[transform.transform_id] = transform

    def get(self, transform_id: str) -> MigrationTransform | None:
        """Get a transform by ID."""
        return self._transforms.get(transform_id)

    def get_for_usage(self, usage: APIUsage) -> list[MigrationTransform]:
        """Get all transforms that can handle a given usage."""
        return [t for t in self._transforms.values() if usage.symbol in t.affected_symbols]

    def list_all(self) -> list[MigrationTransform]:
        """List all registered transforms."""
        return list(self._transforms.values())


# Global registry
_transform_registry = TransformRegistry()


def register_transform(transform: MigrationTransform) -> None:
    """Register a transform globally."""
    _transform_registry.register(transform)


def get_transform(transform_id: str) -> MigrationTransform | None:
    """Get a transform by ID."""
    return _transform_registry.get(transform_id)


def get_transforms_for_usage(usage: APIUsage) -> list[MigrationTransform]:
    """Get all transforms that can handle a given usage."""
    return _transform_registry.get_for_usage(usage)


def list_transforms() -> list[MigrationTransform]:
    """List all registered transforms."""
    return _transform_registry.list_all()

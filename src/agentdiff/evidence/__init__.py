"""Normalized source and patch evidence used by proof and promotion."""

from .patch import (
    PatchBundle,
    PatchEntry,
    PatchManifest,
    SourceSnapshot,
    capture_patch,
    capture_source_snapshot,
    validate_source_snapshot,
)

__all__ = [
    "PatchBundle",
    "PatchEntry",
    "PatchManifest",
    "SourceSnapshot",
    "capture_patch",
    "capture_source_snapshot",
    "validate_source_snapshot",
]

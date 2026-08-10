"""Secure filesystem state capture for AgentDiff transactions."""

from .filesystem import (
    FileChange,
    FileRecord,
    FilesystemManifest,
    FilesystemScanner,
    diff_manifests,
    same_file_state,
)

__all__ = [
    "FileChange",
    "FileRecord",
    "FilesystemManifest",
    "FilesystemScanner",
    "diff_manifests",
    "same_file_state",
]

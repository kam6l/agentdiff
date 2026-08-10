"""Portable root-relative path validation and segment-aware glob matching."""

from __future__ import annotations

import fnmatch
import re
from functools import lru_cache
from pathlib import PurePosixPath

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def normalize_relative_path(value: str) -> str:
    """Return a portable POSIX relative path or raise ``ValueError``.

    Backslashes are accepted as separators so Windows-originated evidence is
    normalized consistently. Absolute POSIX, UNC, and drive-qualified Windows
    paths are rejected on every host.
    """

    raw = str(value)
    normalized = raw.replace("\\", "/")
    if (
        not normalized
        or "\x00" in normalized
        or normalized.startswith("/")
        or normalized.startswith("//")
        or _WINDOWS_DRIVE.match(normalized)
    ):
        raise ValueError("path must be a safe relative path")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path must be a safe relative path")
    return PurePosixPath(*parts).as_posix()


def glob_matches(subject: str, pattern: str) -> bool:
    """Match a path glob where ``*`` cannot cross ``/`` and ``**`` can."""

    subject_parts = tuple(subject.split("/"))
    pattern_parts = tuple(pattern.replace("\\", "/").split("/"))
    if not pattern_parts or any(part == "" for part in pattern_parts):
        return False

    @lru_cache(maxsize=None)
    def match(subject_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return subject_index == len(subject_parts)
        segment = pattern_parts[pattern_index]
        if segment == "**":
            return match(subject_index, pattern_index + 1) or (
                subject_index < len(subject_parts) and match(subject_index + 1, pattern_index)
            )
        return (
            subject_index < len(subject_parts)
            and fnmatch.fnmatchcase(subject_parts[subject_index], segment)
            and match(subject_index + 1, pattern_index + 1)
        )

    return match(0, 0)


def glob_could_match_descendant(directory: str, pattern: str) -> bool:
    """Return whether a glob can match ``directory`` or anything below it."""

    directory_parts = tuple(directory.split("/"))
    pattern_parts = tuple(pattern.replace("\\", "/").split("/"))
    if not pattern_parts or any(part == "" for part in pattern_parts):
        return False

    @lru_cache(maxsize=None)
    def prefix_matches(directory_index: int, pattern_index: int) -> bool:
        if directory_index == len(directory_parts):
            return True
        if pattern_index == len(pattern_parts):
            return False
        segment = pattern_parts[pattern_index]
        if segment == "**":
            return prefix_matches(directory_index, pattern_index + 1) or prefix_matches(
                directory_index + 1, pattern_index
            )
        return fnmatch.fnmatchcase(directory_parts[directory_index], segment) and prefix_matches(
            directory_index + 1, pattern_index + 1
        )

    return prefix_matches(0, 0)

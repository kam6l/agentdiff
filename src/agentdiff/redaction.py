"""Central redaction and terminal-safe display helpers."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

REDACTED = "<redacted>"
TRUNCATED = "<truncated>"
_SENSITIVE_KEY = re.compile(
    r"(?i)(?:api[-_ ]?key|access[-_ ]?key|private[-_ ]?key|auth(?:orization)?|"
    r"cookie|credential|pass(?:word|wd)?|secret|session|token)"
)


def fingerprint(value: str) -> str:
    """Return a stable one-way value marker suitable for state diffs."""

    digest = hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()
    return f"sha256:{digest}"


def is_sensitive_key(key: object) -> bool:
    """Return whether a mapping/flag key commonly carries credentials."""

    return bool(_SENSITIVE_KEY.search(str(key)))


def redact_argv(command: Iterable[str]) -> list[str]:
    """Redact common separate and ``--flag=value`` command-line secrets."""

    result: list[str] = []
    redact_next = False
    for raw in command:
        value = str(raw)
        if redact_next:
            result.append(REDACTED)
            redact_next = False
            continue
        if "=" in value:
            flag, _, _argument = value.partition("=")
            if flag.startswith("-") and is_sensitive_key(flag):
                result.append(f"{flag}={REDACTED}")
                continue
        result.append(value)
        if value.startswith("-") and is_sensitive_key(value):
            redact_next = True
    return result


def redact_data(
    value: Any,
    *,
    _depth: int = 0,
    max_depth: int = 12,
    max_items: int = 1000,
) -> Any:
    """Recursively redact sensitive mapping fields and bound hostile payloads."""

    if _depth >= max_depth:
        return TRUNCATED
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (raw_key, item) in enumerate(value.items()):
            if index >= max_items:
                result[TRUNCATED] = TRUNCATED
                break
            key = str(raw_key)
            result[key] = (
                REDACTED
                if is_sensitive_key(key)
                else redact_data(
                    item,
                    _depth=_depth + 1,
                    max_depth=max_depth,
                    max_items=max_items,
                )
            )
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result_list = [
            redact_data(
                item,
                _depth=_depth + 1,
                max_depth=max_depth,
                max_items=max_items,
            )
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            result_list.append(TRUNCATED)
        return result_list
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    return value


def safe_display(value: object) -> str:
    """Escape terminal controls while preserving ordinary Unicode and newlines."""

    result: list[str] = []
    for character in str(value):
        if character in {"\n", "\t"}:
            result.append(character)
            continue
        if unicodedata.category(character).startswith("C"):
            codepoint = ord(character)
            if codepoint <= 0xFF:
                result.append(f"\\x{codepoint:02x}")
            elif codepoint <= 0xFFFF:
                result.append(f"\\u{codepoint:04x}")
            else:
                result.append(f"\\U{codepoint:08x}")
            continue
        result.append(character)
    return "".join(result)

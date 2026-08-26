"""Canonical serialization and strict validation helpers for maintenance data."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


def canonical_sha256(value: object) -> str:
    """Return a stable digest for a JSON-compatible value."""

    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("value is not canonically JSON serializable") from error
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object with string keys")
    return value


def reject_unknown(
    value: Mapping[str, Any],
    allowed: frozenset[str],
    *,
    field: str,
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{field} contains unknown fields: {', '.join(unknown)}")


def clean_text(
    value: object,
    *,
    field: str,
    required: bool = False,
    max_length: int = 4096,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = value.strip()
    if required and not cleaned:
        raise ValueError(f"{field} is required")
    if "\x00" in cleaned:
        raise ValueError(f"{field} cannot contain NUL characters")
    if len(cleaned) > max_length:
        raise ValueError(f"{field} exceeds the {max_length} character limit")
    return cleaned


def clean_identifier(value: object, *, field: str) -> str:
    cleaned = clean_text(value, field=field, required=True, max_length=128)
    if not _IDENTIFIER.fullmatch(cleaned):
        raise ValueError(
            f"{field} must start with a lowercase letter and contain only "
            "lowercase letters, digits, '.', '_' or '-'"
        )
    return cleaned


def clean_string_tuple(
    value: object,
    *,
    field: str,
    max_items: int = 1000,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list of strings")
    if len(value) > max_items:
        raise ValueError(f"{field} exceeds the {max_items} item limit")
    cleaned = tuple(
        clean_text(item, field=f"{field} item", required=True, max_length=2048) for item in value
    )
    return tuple(sorted(set(cleaned)))


def clean_confidence(value: object, *, field: str = "confidence") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{field} must be between 0.0 and 1.0")
    return 0.0 if normalized == 0.0 else normalized


def clean_int_range(
    value: object,
    *,
    field: str,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            raise ValueError(f"{field} must be at least {minimum}")
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return value


def clean_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def clean_timestamp(value: object, *, field: str, required: bool = True) -> str:
    cleaned = clean_text(value, field=field, required=required, max_length=64)
    if not cleaned:
        return ""
    candidate = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat()

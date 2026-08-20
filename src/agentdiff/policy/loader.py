"""Strict policy loaders.

Loading from a Python mapping uses only the standard library. YAML is imported
lazily by :func:`load_policy_file` so embedding applications do not need PyYAML.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import (
    BLAST_RADIUS_WEIGHT_KEYS,
    SUPPORTED_POLICY_VERSIONS,
    FilesystemPolicy,
    LimitsPolicy,
    NetworkMode,
    NetworkPolicy,
    Policy,
    PolicyAction,
    ProcessPolicy,
    ProofPolicy,
    RollbackPolicy,
    ScoringPolicy,
)


class PolicyValidationError(ValueError):
    """Raised when policy data does not conform to the supported schema."""


class PolicyLoadError(RuntimeError):
    """Raised when a policy file cannot be decoded."""


def _reject_unknown(mapping: Mapping[Any, object], allowed: frozenset[str], path: str = "") -> None:
    unknown = sorted(
        (key for key in mapping if not isinstance(key, str) or key not in allowed),
        key=lambda key: str(key),
    )
    if unknown:
        key = unknown[0]
        key_path = f"{path}.{key}" if path else str(key)
        raise PolicyValidationError(f"unknown policy key: {key_path}")


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PolicyValidationError(f"{path} must be a mapping")
    return value


def _patterns(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PolicyValidationError(f"{path} must be a list of strings")
    return tuple(value)


def _commands(value: object, path: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        raise PolicyValidationError(f"{path} must be a list of command sequences")
    commands: list[tuple[str, ...]] = []
    for index, item in enumerate(value):
        if not isinstance(item, list) or any(not isinstance(arg, str) for arg in item):
            raise PolicyValidationError(f"{path}[{index}] must be a list of strings")
        commands.append(tuple(item))
    return tuple(commands)


def _action(value: object, path: str) -> PolicyAction:
    try:
        return PolicyAction(value)
    except (TypeError, ValueError) as exc:
        raise PolicyValidationError(f"{path} must be one of: allow, review, deny") from exc


def _optional_limit(value: object, path: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PolicyValidationError(f"{path} must be a non-negative integer")
    return value


def load_policy(data: Mapping[str, Any]) -> Policy:
    """Load policy schema version 1 or 2 from an in-memory mapping."""
    root = _mapping(data, "policy")
    _reject_unknown(
        root,
        frozenset(
            {
                "version",
                "filesystem",
                "process",
                "network",
                "limits",
                "rollback",
                "scoring",
                "proof",
            }
        ),
    )
    version = root.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise PolicyValidationError("version is required and must be an integer (1 or 2)")
    if version not in SUPPORTED_POLICY_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_POLICY_VERSIONS))
        raise PolicyValidationError(
            f"unsupported policy version: {version}; supported versions: {supported}"
        )

    filesystem_data = _mapping(root.get("filesystem", {}), "filesystem")
    process_data = _mapping(root.get("process", {}), "process")
    network_data = _mapping(root.get("network", {}), "network")
    limits_data = _mapping(root.get("limits", {}), "limits")
    rollback_data = _mapping(root.get("rollback", {}), "rollback")
    scoring_data = _mapping(root.get("scoring", {}), "scoring")
    proof_data = _mapping(root.get("proof", {}), "proof")

    _reject_unknown(
        filesystem_data,
        frozenset({"allow_write", "review", "deny", "default"}),
        "filesystem",
    )
    _reject_unknown(
        process_data,
        frozenset({"allow", "review", "deny", "default"}),
        "process",
    )
    _reject_unknown(network_data, frozenset({"mode"}), "network")
    _reject_unknown(
        limits_data,
        frozenset({"files_changed", "files_deleted", "processes_spawned", "duration_seconds"}),
        "limits",
    )
    _reject_unknown(
        rollback_data,
        frozenset({"enabled", "max_backup_file_mb", "backup_max_file_mb"}),
        "rollback",
    )
    _reject_unknown(scoring_data, frozenset({"weights"}), "scoring")
    _reject_unknown(
        proof_data,
        frozenset({"image", "network", "setup", "build", "tests", "trusted_digests"}),
        "proof",
    )

    scoring_weights = _mapping(scoring_data.get("weights", {}), "scoring.weights")
    _reject_unknown(scoring_weights, BLAST_RADIUS_WEIGHT_KEYS, "scoring.weights")
    normalized_weights: list[tuple[str, int]] = []
    for name, raw_weight in sorted(scoring_weights.items()):
        if isinstance(raw_weight, bool) or not isinstance(raw_weight, int) or raw_weight < 0:
            raise PolicyValidationError(f"scoring.weights.{name} must be a non-negative integer")
        normalized_weights.append((name, raw_weight))

    requested_mode = network_data.get("mode", NetworkMode.OBSERVE.value)
    try:
        network_mode = NetworkMode(requested_mode)
    except (TypeError, ValueError) as exc:
        raise PolicyValidationError(
            f"unsupported network.mode {requested_mode!r}; supported modes: observe, off"
        ) from exc

    if "max_backup_file_mb" in rollback_data and "backup_max_file_mb" in rollback_data:
        raise PolicyValidationError(
            "rollback.max_backup_file_mb and rollback.backup_max_file_mb cannot both be set"
        )
    max_backup_file_mb = rollback_data.get(
        "max_backup_file_mb",
        rollback_data.get("backup_max_file_mb", 25),
    )
    if (
        isinstance(max_backup_file_mb, bool)
        or not isinstance(max_backup_file_mb, int)
        or max_backup_file_mb < 0
    ):
        raise PolicyValidationError("rollback.max_backup_file_mb must be a non-negative integer")
    rollback_enabled = rollback_data.get("enabled", True)
    if not isinstance(rollback_enabled, bool):
        raise PolicyValidationError("rollback.enabled must be a boolean")

    proof_network = proof_data.get("network", False)
    if not isinstance(proof_network, bool):
        raise PolicyValidationError("proof.network must be a boolean")
    proof_image = proof_data.get("image")
    if proof_image is not None and not isinstance(proof_image, str):
        raise PolicyValidationError("proof.image must be a string or null")

    proof_policy = ProofPolicy(
        image=proof_image,
        network=proof_network,
        setup=_commands(proof_data.get("setup", []), "proof.setup"),
        build=_commands(proof_data.get("build", []), "proof.build"),
        tests=_commands(proof_data.get("tests", []), "proof.tests"),
        trusted_digests=_patterns(proof_data.get("trusted_digests", []), "proof.trusted_digests"),
    )

    return Policy(
        version=version,
        filesystem=FilesystemPolicy(
            allow_write=_patterns(filesystem_data.get("allow_write", []), "filesystem.allow_write"),
            review=_patterns(filesystem_data.get("review", []), "filesystem.review"),
            deny=_patterns(filesystem_data.get("deny", []), "filesystem.deny"),
            default=_action(
                filesystem_data.get("default", PolicyAction.REVIEW.value), "filesystem.default"
            ),
        ),
        process=ProcessPolicy(
            allow=_patterns(process_data.get("allow", []), "process.allow"),
            review=_patterns(process_data.get("review", []), "process.review"),
            deny=_patterns(process_data.get("deny", []), "process.deny"),
            default=_action(
                process_data.get("default", PolicyAction.REVIEW.value), "process.default"
            ),
        ),
        network=NetworkPolicy(mode=network_mode),
        limits=LimitsPolicy(
            files_changed=_optional_limit(limits_data.get("files_changed"), "limits.files_changed"),
            files_deleted=_optional_limit(limits_data.get("files_deleted"), "limits.files_deleted"),
            processes_spawned=_optional_limit(
                limits_data.get("processes_spawned"), "limits.processes_spawned"
            ),
            duration_seconds=_optional_limit(
                limits_data.get("duration_seconds"), "limits.duration_seconds"
            ),
        ),
        rollback=RollbackPolicy(
            enabled=rollback_enabled,
            max_backup_file_mb=max_backup_file_mb,
        ),
        scoring=ScoringPolicy(weights=tuple(normalized_weights)),
        proof=proof_policy,
    )


def load_policy_file(path: str | Path) -> Policy:
    """Load a policy from a YAML or JSON file."""
    candidate = Path(path)
    if not candidate.is_file():
        raise FileNotFoundError(f"policy file not found: {path}")
    raw = candidate.read_text(encoding="utf-8")
    try:
        import yaml  # lazy import

        if yaml is None:
            raise ImportError("PyYAML not installed")
        loader = getattr(yaml, "SafeLoader", None)
        parsed = yaml.load(raw, Loader=loader) if loader is not None else yaml.safe_load(raw)
    except (ImportError, ModuleNotFoundError):
        import json

        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            raise PolicyLoadError(
                "PyYAML is required to load policy files; install it with 'pip install PyYAML'"
            ) from None
    except (OSError, ValueError, TypeError) as exc:
        raise PolicyLoadError(f"failed to parse policy file {path}: {exc}") from exc

    if not isinstance(parsed, dict):
        raise PolicyValidationError("policy root must be a mapping")
    return load_policy(parsed)


# Compatibility alias
load_policy_mapping = load_policy

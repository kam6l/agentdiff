"""Tests for the versioned deterministic policy schema and engine."""

import sys
from pathlib import Path

import pytest

from agentdiff.policy import (
    NetworkMode,
    PolicyAction,
    PolicyEngine,
    PolicyLoadError,
    PolicyValidationError,
    load_policy,
    load_policy_file,
    policy_to_dict,
)


def test_load_policy_from_mapping_without_yaml_dependency() -> None:
    policy = load_policy(
        {
            "version": 1,
            "filesystem": {
                "allow_write": ["src/**", "tests/**"],
                "review": ["pyproject.toml"],
                "deny": [".env", ".env.*"],
                "default": "review",
            },
            "process": {
                "allow": ["python", "pytest"],
                "default": "deny",
            },
            "network": {"mode": "observe"},
            "limits": {
                "files_changed": 20,
                "files_deleted": 0,
                "processes_spawned": 8,
                "duration_seconds": 900,
            },
            "rollback": {"enabled": True, "max_backup_file_mb": 25},
            "scoring": {"weights": {"sensitive_path": 40}},
        }
    )

    assert policy.version == 1
    assert policy.filesystem.allow_write == ("src/**", "tests/**")
    assert policy.filesystem.default is PolicyAction.REVIEW
    assert policy.process.allow == ("python", "pytest")
    assert policy.process.default is PolicyAction.DENY
    assert policy.network.mode is NetworkMode.OBSERVE
    assert policy.limits.files_deleted == 0
    assert policy.rollback.backup_max_file_mb == 25
    assert policy.rollback.enabled is True
    assert dict(policy.scoring.weights)["sensitive_path"] == 40


@pytest.mark.parametrize(
    ("mapping", "unknown_path"),
    [
        ({"version": 1, "filesystem_typo": {}}, "filesystem_typo"),
        (
            {"version": 1, "filesystem": {"allow_writes": ["src/**"]}},
            "filesystem.allow_writes",
        ),
        ({"version": 1, "process": {"allowed": ["python"]}}, "process.allowed"),
        ({"version": 1, "network": {"enforce": True}}, "network.enforce"),
        ({"version": 1, "limits": {"file_changed": 1}}, "limits.file_changed"),
        ({"version": 1, "rollback": {"max_file_mb": 1}}, "rollback.max_file_mb"),
        ({"version": 1, "scoring": {"weights": {"mystery": 1}}}, "scoring.weights.mystery"),
    ],
)
def test_policy_rejects_unknown_keys(mapping: dict[str, object], unknown_path: str) -> None:
    with pytest.raises(PolicyValidationError, match=unknown_path):
        load_policy(mapping)


def test_policy_rejects_unsupported_network_mode_with_clear_error() -> None:
    with pytest.raises(
        PolicyValidationError,
        match=r"unsupported network\.mode 'block'; supported modes: observe, off",
    ):
        load_policy({"version": 1, "network": {"mode": "block"}})


def test_rollback_size_accepts_the_initial_unreleased_alias_but_serializes_canonical_key() -> None:
    policy = load_policy({"version": 1, "rollback": {"backup_max_file_mb": 7}})

    assert policy.rollback.max_backup_file_mb == 7
    assert policy_to_dict(policy)["rollback"] == {
        "enabled": True,
        "max_backup_file_mb": 7,
    }


def test_rollback_size_aliases_cannot_both_be_set() -> None:
    with pytest.raises(PolicyValidationError, match="cannot both be set"):
        load_policy(
            {
                "version": 1,
                "rollback": {"max_backup_file_mb": 7, "backup_max_file_mb": 8},
            }
        )


def test_policy_rejects_unsupported_schema_version_with_clear_error() -> None:
    with pytest.raises(
        PolicyValidationError,
        match="unsupported policy version: 2; supported versions: 1",
    ):
        load_policy({"version": 2})


def test_file_loader_reports_optional_pyyaml_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy_path = tmp_path / "agentdiff.yaml"
    policy_path.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)

    with pytest.raises(
        PolicyLoadError,
        match="PyYAML is required to load policy files; install it with 'pip install PyYAML'",
    ):
        load_policy_file(policy_path)


def test_filesystem_policy_precedence_and_explanation_are_deterministic() -> None:
    policy = load_policy(
        {
            "version": 1,
            "filesystem": {
                "allow_write": ["**"],
                "review": ["pyproject.toml"],
                "deny": [".env", ".env.*"],
                "default": "review",
            },
        }
    )
    engine = PolicyEngine(policy)

    denied = engine.decide_path(".env")
    reviewed = engine.decide_path("pyproject.toml")
    allowed = engine.decide_path("src/auth.py")

    assert denied.action is PolicyAction.DENY
    assert denied.rule == "filesystem.deny[0]"
    assert denied.pattern == ".env"
    assert denied.to_dict()["policy_version"] == 1
    assert denied.to_dict()["phase"] == "post_run"
    assert reviewed.action is PolicyAction.REVIEW
    assert reviewed.rule == "filesystem.review[0]"
    assert allowed.action is PolicyAction.ALLOW
    assert allowed.rule == "filesystem.allow_write[0]"


def test_command_policy_matches_basename_and_deny_wins() -> None:
    engine = PolicyEngine(
        load_policy(
            {
                "version": 1,
                "process": {
                    "allow": ["python*"],
                    "deny": ["python-danger"],
                    "default": "deny",
                },
            }
        )
    )

    assert engine.decide_command(["/usr/bin/python3", "script.py"]).action is PolicyAction.ALLOW
    denied = engine.decide_command(["/tmp/python-danger"])
    assert denied.action is PolicyAction.DENY
    assert denied.rule == "process.deny[0]"
    assert denied.to_dict()["policy_version"] == 1
    assert denied.to_dict()["phase"] == "preflight"


@pytest.mark.parametrize("path", ["../escape", "/absolute", "", "."])
def test_policy_rejects_unsafe_paths(path: str) -> None:
    engine = PolicyEngine(load_policy({"version": 1}))
    with pytest.raises(ValueError, match="safe relative path"):
        engine.decide_path(path)


def test_filesystem_globs_are_segment_aware() -> None:
    engine = PolicyEngine(
        load_policy(
            {
                "version": 1,
                "filesystem": {
                    "allow_write": ["src/*"],
                    "default": "deny",
                },
            }
        )
    )

    assert engine.decide_path("src/module.py").action is PolicyAction.ALLOW
    assert engine.decide_path("src/nested/module.py").action is PolicyAction.DENY


@pytest.mark.parametrize("path", ["C:/escape", "C:\\escape", "C:escape", "//server/share"])
def test_policy_rejects_nonportable_absolute_paths(path: str) -> None:
    engine = PolicyEngine(load_policy({"version": 1, "filesystem": {"default": "allow"}}))
    with pytest.raises(ValueError, match="safe relative path"):
        engine.decide_path(path)


def test_policy_serialization_is_normalized_and_json_safe() -> None:
    policy = load_policy({"version": 1, "network": {"mode": "off"}})
    serialized = policy_to_dict(policy)

    assert serialized["version"] == 1
    assert serialized["network"] == {"mode": "off"}
    assert serialized["filesystem"]["default"] == "review"

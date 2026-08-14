"""Tests for AgentDiff Cortex: SkillSynthesizer, ContextCompressor, and SelfHealer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from agentdiff.cortex import (
    AgentMemoryStore,
    ContextCompressor,
    ContextPacker,
    SelfHealer,
    SkillSynthesizer,
)


@pytest.fixture
def mock_capsule() -> dict[str, Any]:
    return {
        "run_id": "run-test-1234",
        "task": "Refactor user authentication session handler",
        "argv": ["python", "-m", "pytest", "tests/test_auth.py"],
        "policy_decision": "ALLOW",
        "blast_radius": {"score": 14, "level": "low"},
        "mutations": {
            "created": [{"path": "src/auth/session.py"}],
            "modified": [{"path": "src/auth/handler.py"}],
            "deleted": [],
        },
    }


def test_skill_synthesizer_generates_valid_contract(
    tmp_path: Path, mock_capsule: dict[str, Any]
) -> None:
    synthesizer = SkillSynthesizer(root=tmp_path)
    skill = synthesizer.synthesize(mock_capsule, title="Auth Session Refactoring")

    assert skill.skill_id == "auth-session-refactoring"
    assert skill.title == "Auth Session Refactoring"
    assert skill.task_intent == "Refactor user authentication session handler"
    assert "src/auth/session.py" in skill.safe_paths
    assert skill.verification_recipe == "pytest"

    # Check Markdown formatting
    md = skill.to_markdown()
    assert "# Skill: Auth Session Refactoring" in md
    assert "src/auth/session.py" in md
    assert "pytest" in md

    # Check file saved
    skill_file = tmp_path / ".agentdiff" / "skills" / "auth-session-refactoring.md"
    assert skill_file.exists()
    assert "name: auth-session-refactoring" in skill_file.read_text(encoding="utf-8")


def test_skill_synthesizer_listing(tmp_path: Path, mock_capsule: dict[str, Any]) -> None:
    synthesizer = SkillSynthesizer(root=tmp_path)
    synthesizer.synthesize(mock_capsule, title="Skill Alpha")
    mock_capsule["task"] = "Update database schema migration"
    synthesizer.synthesize(mock_capsule, title="Skill Beta")

    skills = synthesizer.list_skills()
    assert len(skills) == 2
    skill_ids = [s.skill_id for s in skills]
    assert "skill-alpha" in skill_ids
    assert "skill-beta" in skill_ids


def test_context_compressor_trajectory_compression(mock_capsule: dict[str, Any]) -> None:
    card = ContextCompressor.compress_trajectory(
        task=str(mock_capsule["task"]),
        run_id=str(mock_capsule["run_id"]),
        mutations=mock_capsule["mutations"],
        policy_decision="ALLOW",
        blast_radius=14,
        argv=mock_capsule["argv"],
    )

    assert card.run_id == "run-test-1234"
    assert card.outcome == "ALLOW"
    assert card.blast_radius == 14
    assert "src/auth/session.py" in card.modified_symbols_or_files
    prompt_str = card.to_prompt_block()
    assert "Refactor user authentication" in prompt_str
    assert "ALLOW" in prompt_str


def test_agent_memory_store_recording_and_fragility(
    tmp_path: Path, mock_capsule: dict[str, Any]
) -> None:
    store = AgentMemoryStore(root=tmp_path)
    card = ContextCompressor.compress_trajectory(
        task=str(mock_capsule["task"]),
        run_id=str(mock_capsule["run_id"]),
        mutations=mock_capsule["mutations"],
        policy_decision="DENY",
        blast_radius=68,
    )

    paths = ["config/db.env", "src/auth/handler.py"]
    store.record_episode(card, collateral_paths=paths, model_name="claude-3.7")
    stats = store.get_stats()

    assert stats["total_episodes"] == 1
    assert stats["fragile_paths_tracked"] == 2
    assert "claude-3.7" in stats["models_benchmarked"]
    assert stats["model_stats"]["claude-3.7"]["avg_blast_radius"] == 68.0

    # Ensure persisted file exists
    assert (tmp_path / ".agentdiff" / "memory.json").exists()


def test_context_packer_packs_skills_and_fragility(
    tmp_path: Path, mock_capsule: dict[str, Any]
) -> None:
    synthesizer = SkillSynthesizer(root=tmp_path)
    synthesizer.synthesize(mock_capsule, title="Auth Session Refactoring")

    store = AgentMemoryStore(root=tmp_path)
    card = ContextCompressor.compress_trajectory(
        task="Break auth",
        run_id="run-2",
        mutations={},
        policy_decision="DENY",
        blast_radius=80,
    )
    store.record_episode(card, collateral_paths=["config/secrets.env"])

    pack = ContextPacker.pack(task_prompt="Refactor user authentication endpoints", root=tmp_path)

    assert "AGENTDIFF CONTEXT MEMORY PACK" in pack
    assert "Auth Session Refactoring" in pack
    assert "config/secrets.env" in pack


def test_self_healer_remediation_payload() -> None:
    capsule_deny = {
        "run_id": "run-deny-999",
        "task": "Fix security vulnerability",
        "policy_decision": "DENY",
        "blast_radius": {"score": 75},
        "mutations": {
            "created": [],
            "modified": [{"path": ".env", "decision": "deny"}],
            "deleted": [],
        },
    }

    payload = SelfHealer.generate_remediation(capsule_deny)

    assert payload["status"] == "REMEDIATION_REQUIRED"
    assert payload["run_id"] == "run-deny-999"
    assert payload["blast_radius_score"] == 75
    assert ".env" in payload["collateral_files_to_revert"]
    assert "agentdiff rollback run-deny-999 --safe-only" in payload["recovery_command"]

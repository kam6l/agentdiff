from __future__ import annotations

from agentdiff.policy import PolicyAction
from agentdiff.scoring import (
    BlastRadiusScorer,
    BlastRadiusWeights,
    MutationRisk,
    RiskLevel,
)


def test_empty_run_has_zero_low_blast_radius() -> None:
    result = BlastRadiusScorer().score([])

    assert result.score == 0
    assert result.level is RiskLevel.LOW
    assert result.counts["files_changed"] == 0
    assert result.components == []


def test_denied_sensitive_file_has_explainable_high_risk() -> None:
    result = BlastRadiusScorer().score(
        [MutationRisk(path=".env", change_type="modified", decision=PolicyAction.DENY)]
    )

    assert result.score == 65
    assert result.level is RiskLevel.HIGH
    assert result.counts["unexpected_files"] == 1
    assert result.counts["sensitive_files"] == 1
    assert {component.name for component in result.components} == {
        "denied_mutation",
        "sensitive_path",
    }


def test_denied_sensitive_deletion_is_critical() -> None:
    result = BlastRadiusScorer().score(
        [MutationRisk(path="secrets/key.pem", change_type="deleted", decision="deny")]
    )

    assert result.score == 75
    assert result.level is RiskLevel.CRITICAL
    assert result.counts["files_deleted"] == 1


def test_score_components_include_dependencies_processes_ports_and_budgets() -> None:
    result = BlastRadiusScorer().score(
        [
            MutationRisk(
                path="pyproject.toml",
                change_type="modified",
                decision="review",
                mode_changed=True,
            ),
            MutationRisk(path="src/unexpected.py", change_type="created", decision="review"),
        ],
        orphan_processes=1,
        opened_ports=2,
        budget_violations=1,
    )

    assert result.score == 60
    assert result.level is RiskLevel.HIGH
    assert result.counts["dependency_changes"] == 1
    assert result.counts["orphan_processes"] == 1
    assert result.counts["ports_opened"] == 2
    assert result.counts["budget_violations"] == 1
    names = {component.name for component in result.components}
    assert {"review_mutation", "dependency_change", "mode_change"} <= names
    assert {"orphan_process", "opened_port", "budget_violation"} <= names


def test_score_is_capped_and_custom_weights_are_deterministic() -> None:
    custom = BlastRadiusWeights(sensitive_path=90, denied_mutation=20)
    result = BlastRadiusScorer(custom).score(
        [MutationRisk(path=".env", change_type="modified", decision="deny")]
    )

    assert result.raw_score == 110
    assert result.score == 100
    assert result.level is RiskLevel.CRITICAL
    assert result.to_dict()["components"][0]["points"] > 0


def test_threshold_boundaries() -> None:
    scorer = BlastRadiusScorer()

    assert scorer.level_for(20) is RiskLevel.LOW
    assert scorer.level_for(21) is RiskLevel.MODERATE
    assert scorer.level_for(40) is RiskLevel.MODERATE
    assert scorer.level_for(41) is RiskLevel.HIGH
    assert scorer.level_for(70) is RiskLevel.HIGH
    assert scorer.level_for(71) is RiskLevel.CRITICAL

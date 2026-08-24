"""Focused tests for evidence-preserving post-merge outcomes."""

from __future__ import annotations

from agentdiff.delivery import SealedDeliveryIdentity
from agentdiff.outcome import (
    OutcomeCheck,
    OutcomeCheckResult,
    OutcomeCheckStatus,
    OutcomeEvidence,
    OutcomeState,
    PostMergeContext,
    PostMergeOutcomeEvaluator,
    PostMergeVerifier,
)


def _context() -> PostMergeContext:
    return PostMergeContext(
        merged_commit_sha="merge-a",
        delivery_identity=SealedDeliveryIdentity("base-a", "patch-a", "proof-a"),
        pull_request_number=42,
    )


def test_all_checks_pass_yields_healthy_and_preserves_evidence() -> None:
    evidence = OutcomeEvidence(
        source="deployment-api",
        summary="deployment completed",
        digest="sha256:deployment",
        reference="deployments/123",
    )
    verifier = PostMergeVerifier(
        (
            OutcomeCheck(
                "deployment",
                lambda _context, _timeout: OutcomeCheckResult(
                    "deployment",
                    "deployment",
                    OutcomeCheckStatus.PASS,
                    evidence=(evidence,),
                ),
                kind="deployment",
            ),
            OutcomeCheck("health", lambda _context, _timeout: True, kind="health-endpoint"),
        )
    )

    result = verifier.verify(_context())

    assert result.state is OutcomeState.HEALTHY
    assert result.maintenance_complete is True
    assert result.automatic_production_rollback is False
    assert result.checks[0].evidence == (evidence,)
    assert result.to_dict()["checks"][0]["evidence"][0]["digest"] == "sha256:deployment"


def test_explicit_failure_detects_regression_without_default_rollback() -> None:
    result = PostMergeVerifier(
        (
            OutcomeCheck("deployment", lambda _context, _timeout: True),
            OutcomeCheck(
                "error-rate",
                lambda _context, _timeout: {
                    "status": "FAIL",
                    "evidence": {
                        "source": "metrics",
                        "summary": "error rate exceeded threshold",
                        "digest": "sha256:metrics-window",
                    },
                },
                kind="error-rate",
            ),
        )
    ).verify(_context())

    assert result.state is OutcomeState.REGRESSION_DETECTED
    assert result.stop_remaining_campaign is True
    assert result.notify_human is True
    assert result.prepare_revert is False
    assert result.automatic_production_rollback is False
    assert "STOP_REMAINING_CAMPAIGN" in result.recommended_actions
    assert "PREPARE_REVERT_FOR_REVIEW" not in result.recommended_actions


def test_prepare_revert_is_review_only_and_never_automatic_rollback() -> None:
    result = PostMergeVerifier((OutcomeCheck("canary", lambda _context, _timeout: False),)).verify(
        _context(), prepare_revert_on_regression=True
    )

    assert result.state is OutcomeState.REGRESSION_DETECTED
    assert result.prepare_revert is True
    assert "PREPARE_REVERT_FOR_REVIEW" in result.recommended_actions
    assert result.automatic_production_rollback is False


def test_timeout_unavailable_or_invalid_evidence_is_inconclusive() -> None:
    def timeout(_context: PostMergeContext, _seconds: float) -> bool:
        raise TimeoutError("telemetry budget")

    timed_out = PostMergeVerifier((OutcomeCheck("latency", timeout),)).verify(_context())
    unavailable = PostMergeOutcomeEvaluator().evaluate(
        _context(),
        (
            OutcomeCheckResult(
                "health",
                "health-endpoint",
                OutcomeCheckStatus.UNAVAILABLE,
                evidence=(OutcomeEvidence("health", "endpoint unavailable"),),
            ),
        ),
    )

    assert timed_out.state is OutcomeState.INCONCLUSIVE
    assert timed_out.checks[0].status is OutcomeCheckStatus.TIMEOUT
    assert unavailable.state is OutcomeState.INCONCLUSIVE
    assert unavailable.checks[0].evidence[0].summary == "endpoint unavailable"
    assert unavailable.automatic_production_rollback is False


def test_empty_or_budget_truncated_check_set_is_inconclusive() -> None:
    empty = PostMergeVerifier(()).verify(_context())
    bounded = PostMergeVerifier(
        (
            OutcomeCheck("one", lambda _context, _timeout: True),
            OutcomeCheck("two", lambda _context, _timeout: True),
        ),
        max_checks=1,
    ).verify(_context())

    assert empty.state is OutcomeState.INCONCLUSIVE
    assert bounded.state is OutcomeState.INCONCLUSIVE
    assert bounded.complete is False
    assert len(bounded.checks) == 1
    assert "post-merge check-count budget reached" in bounded.reasons


def test_mismatched_plugin_result_id_is_invalid_and_evidence_is_retained() -> None:
    evidence = OutcomeEvidence("canary", "wrong subject returned")
    result = PostMergeVerifier(
        (
            OutcomeCheck(
                "expected",
                lambda _context, _timeout: OutcomeCheckResult(
                    "other",
                    "canary",
                    OutcomeCheckStatus.PASS,
                    evidence=(evidence,),
                ),
            ),
        )
    ).verify(_context())

    assert result.state is OutcomeState.INCONCLUSIVE
    assert result.checks[0].status is OutcomeCheckStatus.INVALID
    assert result.checks[0].evidence == (evidence,)

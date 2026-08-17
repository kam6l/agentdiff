"""Deterministic proof-plan discovery and bounded test-result parsing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .plan import (
    TrustedVerificationPlan,
    select_trusted_verification_plan,
)

if TYPE_CHECKING:
    from agentdiff.policy import Policy

# Compatibility alias
VerificationPlan = TrustedVerificationPlan


def select_verification_plan(root: Path, policy: Policy) -> VerificationPlan:
    """Select verification plan for a workspace root and policy."""
    return select_trusted_verification_plan(root, policy)


def parse_test_counts(output: str) -> tuple[int | None, int | None]:
    """Parse common pytest/npm summaries for reporting only, never verdict logic."""
    passed = re.search(r"(?i)(\d+)\s+passed", output)
    failed = re.search(r"(?i)(\d+)\s+failed", output)
    if passed:
        passed_count = int(passed.group(1))
        failed_count = int(failed.group(1)) if failed else 0
        return passed_count, passed_count + failed_count
    return None, None

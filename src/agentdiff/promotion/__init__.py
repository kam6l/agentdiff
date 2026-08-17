"""Fail-closed, crash-consistent host promotion."""

from .engine import PromotionEngine
from .journal import JournalEntry, JournalState, PromotionJournal
from .lock import PromotionLockError, WorkspaceLease
from .models import (
    PromotionAction,
    PromotionConflict,
    PromotionPlan,
    PromotionPlanEntry,
    PromotionReport,
)
from .recovery import PromotionRecovery, RecoveryReport
from .staging import PromotionStager

__all__ = [
    "JournalEntry",
    "JournalState",
    "PromotionAction",
    "PromotionConflict",
    "PromotionEngine",
    "PromotionJournal",
    "PromotionLockError",
    "PromotionPlan",
    "PromotionPlanEntry",
    "PromotionRecovery",
    "PromotionReport",
    "PromotionStager",
    "RecoveryReport",
    "WorkspaceLease",
]

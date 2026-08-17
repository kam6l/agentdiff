"""Fail-closed, crash-consistent host promotion."""

from .engine import PromotionEngine
from .journal import (
    EntryState,
    JournalEntry,
    JournalLoadOutcome,
    JournalLoadResult,
    JournalState,
    PromotionJournal,
)
from .lock import PromotionLockError, WorkspaceLease
from .models import (
    PromotionAction,
    PromotionConflict,
    PromotionPlan,
    PromotionPlanEntry,
    PromotionReport,
)
from .recovery import PromotionRecovery, PromotionRecoveryError, RecoveryReport
from .staging import PromotionStager

__all__ = [
    "EntryState",
    "JournalEntry",
    "JournalLoadOutcome",
    "JournalLoadResult",
    "JournalState",
    "PromotionAction",
    "PromotionConflict",
    "PromotionEngine",
    "PromotionJournal",
    "PromotionLockError",
    "PromotionPlan",
    "PromotionPlanEntry",
    "PromotionRecovery",
    "PromotionRecoveryError",
    "PromotionReport",
    "PromotionStager",
    "RecoveryReport",
    "WorkspaceLease",
]

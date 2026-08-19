"""Proof-driven automatic repair loop and the Human Attention Router."""

from .loop import (
    RepairLoop,
    RepairOutcome,
    build_repair_prompt,
    default_repair_command_builder,
    detect_scope_change,
)
from .packet import FailurePacket
from .router import HumanAttentionRouter, RoutingDecision

__all__ = [
    "FailurePacket",
    "HumanAttentionRouter",
    "RepairLoop",
    "RepairOutcome",
    "RoutingDecision",
    "build_repair_prompt",
    "default_repair_command_builder",
    "detect_scope_change",
]

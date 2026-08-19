"""Local zero-touch sidecar: daemon, client, notifications, and agent adapter."""

from .adapters import WrapRunner, WrapSummary
from .client import SidecarClient, SidecarError, ensure_sidecar
from .notify import Notification, Notifier

__all__ = [
    "Notification",
    "Notifier",
    "SidecarClient",
    "SidecarError",
    "WrapRunner",
    "WrapSummary",
    "ensure_sidecar",
]

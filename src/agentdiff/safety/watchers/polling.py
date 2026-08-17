"""Pure-polling fallback event source (no OS event backend)."""

from __future__ import annotations


class PollingEventSource:
    """Event source that never produces events.

    Used when no platform event backend is available or when a backend
    failed to start. The hybrid watcher then relies on its scheduled full
    reconciliation cadence, which is always authoritative.
    """

    backend = "polling"

    def start(self) -> None:
        return None

    def drain(self) -> list[str | None]:
        return []

    def stop(self) -> None:
        return None

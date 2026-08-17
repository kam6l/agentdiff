"""Event-source backend contracts for the hybrid safety watcher."""

from __future__ import annotations

from typing import Protocol


class EventSource(Protocol):
    """A filesystem event source feeding dirty-path hints.

    Events are strictly acceleration hints. A failing or unsupported source
    must raise from :meth:`start` so the watcher can degrade to polling;
    it must never silently stop observing.
    """

    backend: str

    def start(self) -> None:
        """Begin delivering events to :meth:`drain`."""
        ...

    def drain(self) -> list[str | None]:
        """Return paths modified since the previous drain (or ``None`` events)."""
        ...

    def stop(self) -> None:
        """Stop event delivery and release resources."""
        ...

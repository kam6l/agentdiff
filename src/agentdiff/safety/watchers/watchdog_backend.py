"""Optional watchdog-based filesystem event source.

``watchdog`` is imported lazily and kept optional: when it is not installed,
or its observer cannot start on the platform, :class:`WatchdogEventSource`
raises and the hybrid watcher degrades to polling instead of pretending it
has live event hints. Events remain hints only; every security verdict is
computed from authoritative full captures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class WatchdogEventSource:
    """Drain ``watchdog`` filesystem events into dirty-path hints."""

    backend = "watchdog"

    def __init__(self, root: str | Path) -> None:
        try:
            from watchdog.events import FileSystemEventHandler  # type: ignore[import-not-found]
            from watchdog.observers import Observer  # type: ignore[import-not-found]
        except ImportError as error:  # pragma: no cover - depends on environment
            raise RuntimeError("watchdog is not installed") from error
        self._observer_class = Observer
        self._handler_class = FileSystemEventHandler
        self.root = Path(root).resolve()
        self._observer: Any | None = None
        self._pending: list[str | None] = []

    def _make_handler(self, sink):
        handler_class = self._handler_class

        class _Handler(handler_class):
            def on_any_event(self, event) -> None:
                source = getattr(event, "src_path", None)
                if isinstance(source, str):
                    sink.append(source)
                else:
                    sink.append(None)

        return _Handler()

    def start(self) -> None:
        if self._observer is not None:
            return
        handler = self._make_handler(self._pending)
        observer = self._observer_class(timeout=0.2)
        observer.schedule(handler, str(self.root), recursive=True)
        try:
            observer.start()
        except OSError as error:
            raise RuntimeError(f"watchdog observer failed to start: {error}") from error
        self._observer = observer

    def drain(self) -> list[str | None]:
        pending = self._pending
        self._pending = []
        return pending

    def stop(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            finally:
                self._observer = None

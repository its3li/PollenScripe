"""Status plumbing shared by the worker threads and the Qt UI thread."""

from __future__ import annotations

import queue
import threading
from collections import deque

from .config import APP_NAME


def log(message: str) -> None:
    print(f"[{APP_NAME}] {message}", flush=True)


class StatusBus:
    """Thread-safe channel from the worker threads to the Qt UI thread.

    Status text and window commands are queued because their order matters. The
    audio level is a plain attribute instead: only the newest value is ever
    interesting, and attribute assignment is atomic under the GIL, so the
    realtime audio callback never blocks on a lock the UI thread might hold.
    """

    def __init__(self) -> None:
        self.status: queue.Queue[tuple[str, str]] = queue.Queue()
        self.commands: queue.Queue[str] = queue.Queue()
        self._level = 0.0

    def set_status(self, state: str, detail: str = "") -> None:
        self.status.put((state, detail))

    def show(self) -> None:
        self.commands.put("show")

    def hide(self, delay_ms: int = 0) -> None:
        self.commands.put(f"hide:{delay_ms}")

    def toggle(self) -> None:
        self.commands.put("toggle")

    def set_level(self, level: float) -> None:
        self._level = level

    def level(self) -> float:
        return self._level


class History:
    """Recent transcripts, so a paste that went astray is still recoverable."""

    def __init__(self, size: int) -> None:
        self._items: deque[str] = deque(maxlen=max(0, size))
        self._lock = threading.Lock()

    def add(self, text: str) -> None:
        if not self._items.maxlen:
            return
        with self._lock:
            self._items.appendleft(text)

    def items(self) -> list[str]:
        with self._lock:
            return list(self._items)

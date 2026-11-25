"""Ajan akışı deposu: tek JSON dosyası (CM_STORAGE=file, varsayılan). Davranış önceki AgentFeed ile aynıdır."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable

from .file_memory import write_atomic


def load_events(path: Path) -> tuple[dict, ...]:
    if not path.exists():
        return ()
    try:
        return tuple(json.loads(path.read_text(encoding="utf-8")).get("events", []))
    except (json.JSONDecodeError, OSError):
        return ()


class FileFeedRepository:
    def __init__(self, path: Path, max_events: Callable[[], int]):
        self.path = Path(path)
        self._max_events = max_events
        self._lock = threading.Lock()
        self._events = load_events(self.path)

    def events(self, after: int = 0) -> list[dict]:
        with self._lock:
            return [o for o in self._events if o["n"] > after]

    def append(self, build: Callable[[int], dict]) -> dict:
        with self._lock:
            o = build((self._events[-1]["n"] + 1) if self._events else 1)
            self._commit((*self._events, o)[-self._max_events():])
            return o

    def update(self, n: int, fields: dict) -> dict | None:
        with self._lock:
            old = next((x for x in self._events if x["n"] == n), None)
            if old is None:
                return None
            new = {**old, **fields}
            self._commit(tuple(new if x is old else x for x in self._events))
            return new

    def reset(self) -> None:
        with self._lock:
            self._commit(())

    def _commit(self, events: tuple[dict, ...]) -> None:
        write_atomic(self.path, {"events": list(events)})
        self._events = events

"""Hafıza deposu: tek JSON dosyası (CM_STORAGE=file, varsayılan). Davranış önceki MemoryBook ile aynıdır.

Dosya açılışta bir kez okunur; her yazımda bütün dosya atomik olarak (geçici dosya + os.replace) yeniden yazılır.
Süreçler arası paylaşım yoktur: her süreç kendi kopyasıyla çalışır (çok süreçli kurulum için CM_STORAGE=dynamodb).
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Callable

from .base import MemoryState, Mutation, MutationFn, apply_mutation

LOG_KEEP = 500


def load_state(path: Path, run_id: str) -> MemoryState:
    if not path.exists():
        return MemoryState()
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return MemoryState()          # bozuk/yarım dosya: ilk ensure() hafızayı yeniden tohumlar
    if d.get("run_id") != run_id:
        return MemoryState()
    return MemoryState(seed_day=d.get("seed_day"), entries=tuple(d.get("entries", [])), log=tuple(d.get("log", [])))


def write_atomic(path: Path, document: dict) -> None:
    """Geçici dosyaya yaz, sonra yerine taşı (eşzamanlı okuyucu yarım dosya görmez)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class FileMemoryRepository:
    def __init__(self, path: Path, run_id: str):
        self.path = Path(path)
        self.run_id = run_id
        self._lock = threading.Lock()
        self._state = load_state(self.path, run_id)

    def state(self) -> MemoryState:
        return self._state

    def seed(self, day: int, make_entries: Callable[[], list[dict]], *, force: bool) -> int:
        with self._lock:
            if not force and self._state.seed_day is not None:
                return len(self._state.entries)
            self._commit(MemoryState(seed_day=day, entries=tuple(make_entries()), log=()))
            return len(self._state.entries)

    def mutate(self, fn: MutationFn) -> Mutation | None:
        with self._lock:
            m = fn(self._state)
            if m is not None:
                self._commit(apply_mutation(self._state, m))
            return m

    def _commit(self, state: MemoryState) -> None:
        write_atomic(self.path, {"app_data": True, "run_id": self.run_id, "seed_day": state.seed_day,
                                 "entries": list(state.entries), "log": list(state.log[-LOG_KEEP:])})
        self._state = state

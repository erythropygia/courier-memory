"""Depo arayüzleri: MemoryBook ve AgentFeed iş kurallarını bilir, depolar yalnız kalıcılığı ve eşzamanlılığı.

Hafıza yazımları `mutate(fn)` ile yapılır: depo güncel durumu verir, `fn` saf bir fonksiyon olarak değişikliği
(`Mutation`) döndürür, depo onu atomik işler. DynamoDB deposu çakışmada `fn`'i taze durumla yeniden çağırır.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class StorageConflictError(RuntimeError):
    """Eşzamanlı yazımlar yüzünden değişiklik art arda denemelerde işlenemedi."""


@dataclass(frozen=True)
class MemoryState:
    seed_day: int | None = None
    entries: tuple[dict, ...] = ()
    log: tuple[dict, ...] = ()

    def find(self, entry_id: str) -> dict | None:
        return next((e for e in self.entries if e["id"] == entry_id), None)


@dataclass(frozen=True)
class Mutation:
    """Tek kaydın yeni hali + günlük satırı. created=True: kayıt yeni (aynı kimlikle var olmamalı)."""
    entry: dict
    log: dict
    created: bool = False


def apply_mutation(state: MemoryState, m: Mutation) -> MemoryState:
    """Değişikliği uygulanmış yeni durum (girdi durumu değişmez)."""
    if m.created:
        entries = (*state.entries, m.entry)
    else:
        entries = tuple(m.entry if e["id"] == m.entry["id"] else e for e in state.entries)
    return MemoryState(seed_day=state.seed_day, entries=entries, log=(*state.log, m.log))


MutationFn = Callable[[MemoryState], "Mutation | None"]


class MemoryRepository(Protocol):
    def state(self) -> MemoryState: ...

    def seed(self, day: int, make_entries: Callable[[], list[dict]], *, force: bool) -> int:
        """force=False (ensure): tohumlanmışsa dokunmaz. force=True (reset): kayıtları tohumla değiştirir."""

    def mutate(self, fn: MutationFn) -> Mutation | None: ...


class FeedRepository(Protocol):
    def events(self, after: int = 0) -> list[dict]: ...

    def append(self, build: Callable[[int], dict]) -> dict:
        """build(n) olayı üretir; n bir önceki olayın numarası + 1'dir."""

    def update(self, n: int, fields: dict) -> dict | None: ...

    def reset(self) -> None: ...


class UsageSink(Protocol):
    def record(self, row: dict) -> None: ...

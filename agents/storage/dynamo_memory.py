"""Hafıza deposu: DynamoDB (CM_STORAGE=dynamodb). Anahtar düzeni için bkz. dynamo_keys.

Okuma: her okumada META tutarlı okunur (CM_DYNAMODB_SYNC_SECONDS > 0 ise en çok o kadar saniyede bir); sürüm
değiştiyse önbellek yalnız değişen girişlerle güncellenir. Yazma: tek kayıt + LOG + META.version artışı tek
TransactWriteItems'ta, META.version koşuluyla (iyimser kilit). Çakışmada güncel durum okunur ve iş kuralı
(`fn`) taze durumla yeniden çalışır: upsert'te iki süreç aynı adres/türe aynı anda yazsa da tek kayıt oluşur,
geri bildirim sayaçları kaybolmaz, kimlikler çakışmaz.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from .base import MemoryState, Mutation, MutationFn, apply_mutation
from .dynamo_keys import memory_meta_key
from .dynamo_memory_seed import new_generation, seed_generation
from .dynamo_memory_sync import EMPTY, Snapshot, entry_item, log_item, refresh
from .dynamo_table import DynamoTable, encode, put_op, retry_conflicts, update_op


def _meta_op(run_id: str, snap: Snapshot, generation: str, next_seq: int) -> dict:
    version = snap.version + 1
    if snap.generation is None:            # tohumlanmamış hafızaya ilk yazım: META yoktur
        item = {**memory_meta_key(run_id), **encode({"run_id": run_id, "generation": generation, "seed_day": None,
                                                     "version": version, "next_seq": next_seq, "entry_count": 0})}
        return put_op(item, exists=False)
    return update_op(memory_meta_key(run_id), {"version": version, "next_seq": next_seq},
                     {"generation": snap.generation, "version": snap.version})


def commit(t: DynamoTable, run_id: str, snap: Snapshot, m: Mutation) -> Snapshot:
    """Değişikliği tek işlemde yazar ve yeni Snapshot'ı döndürür; META değişmişse Conflict."""
    gen = snap.generation or new_generation()
    eid = m.entry["id"]
    seq = snap.next_seq if m.created else snap.seqs[eid]
    next_seq = snap.next_seq + (1 if m.created else 0)
    version = snap.version + 1
    t.transact([_meta_op(run_id, snap, gen, next_seq),
                put_op(entry_item(run_id, gen, m.entry, seq), exists=not m.created),
                put_op(log_item(run_id, gen, version, m.log), exists=False)])
    return Snapshot(generation=gen, version=version, next_seq=next_seq, seqs={**snap.seqs, eid: seq},
                    state=apply_mutation(snap.state, m))


class DynamoMemoryRepository:
    def __init__(self, table: DynamoTable, run_id: str, sync_seconds: float = 0.0):
        self.table = table
        self.run_id = run_id
        self.sync_seconds = sync_seconds
        self._lock = threading.Lock()
        self._snap = EMPTY
        self._checked_at = float("-inf")

    def state(self) -> MemoryState:
        return self._sync().state

    def seed(self, day: int, make_entries: Callable[[], list[dict]], *, force: bool) -> int:
        snap = seed_generation(self.table, self.run_id, day, make_entries, force)
        if snap is not None:
            self._install(snap)
        return len(self._sync(force=True).state.entries)

    def mutate(self, fn: MutationFn) -> Mutation | None:
        return retry_conflicts(lambda: self._mutate_once(fn))

    def _mutate_once(self, fn: MutationFn) -> Mutation | None:
        snap = self._sync(force=True)
        m = fn(snap.state)
        if m is None:
            return None
        self._install(commit(self.table, self.run_id, snap, m))
        return m

    def _sync(self, force: bool = False) -> Snapshot:
        """META'yı okuyup önbelleği eşitler. Ağ çağrısı kilit dışında yapılır (okuyucu iş parçacıkları beklemez)."""
        with self._lock:
            snap, fresh = self._snap, time.monotonic() - self._checked_at < self.sync_seconds
        if fresh and not force:
            return snap
        meta = self.table.get(memory_meta_key(self.run_id))
        new = refresh(self.table, self.run_id, snap, meta)
        with self._lock:
            self._checked_at = time.monotonic()
        self._install(new)
        return new

    def _install(self, snap: Snapshot) -> None:
        """Kendi yazımımızın sonucunu önbelleğe al (daha yeni bir eşitleme varsa ona dokunma)."""
        with self._lock:
            if snap.generation != self._snap.generation or snap.version >= self._snap.version:
                self._snap = snap

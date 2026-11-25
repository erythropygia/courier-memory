"""Hafıza tohumlama (ensure/reset) ve eski nesillerin silinmesi.

Tohum yeni bir nesil bölümüne BatchWriteItem ile yazılır, sonra META tek koşullu PutItem ile o nesle geçirilir.
- ensure: META'da seed_day varsa hiçbir şey yazılmaz (idempotent; yarışı kaybeden süreç kendi bölümünü siler).
- reset: aynı gün tohumlanmış ve hiç değişmemişse (version == 0) atlanır; değilse yeniden tohumlanır.
Önceki nesil bir reset boyunca tutulur (o anda tam yükleme yapan süreçler için); ondan önceki silinir.
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Callable

from boto3.dynamodb.conditions import Attr

from .base import MemoryState, StorageConflictError
from .dynamo_keys import PK, memory_meta_key, memory_partition
from .dynamo_memory_sync import Snapshot, entry_item
from .dynamo_table import MAX_ATTEMPTS, Conflict, DynamoTable, decode, encode, purge_partition


def new_generation() -> str:
    return uuid.uuid4().hex[:16]


def is_seeded(meta: dict | None) -> bool:
    return meta is not None and meta.get("seed_day") is not None


def can_skip(meta: dict | None, day: int, force: bool) -> bool:
    if not is_seeded(meta):
        return False
    return not force or (decode(meta["seed_day"]) == day and int(meta.get("version", 0)) == 0)


def meta_item(run_id: str, generation: str, day: int | None, count: int, previous: str | None) -> dict:
    return {**memory_meta_key(run_id), **encode({"run_id": run_id, "generation": generation, "seed_day": day,
                                                 "version": 0, "next_seq": count, "entry_count": count,
                                                 "previous_generation": previous, "seeded_at": round(time.time(), 3)})}


def expected_meta(meta: dict | None):
    """META'nın okunduğu haliyle durduğu koşulu (yoksa: hiç yok)."""
    if meta is None:
        return Attr(PK).not_exists()
    return Attr("generation").eq(meta["generation"]) & Attr("version").eq(meta["version"])


def purge(t: DynamoTable, run_id: str, generation: str | None) -> None:
    if generation:
        purge_partition(t, memory_partition(run_id, generation))


def _switch(t: DynamoTable, run_id: str, gen: str, day: int, entries: list[dict], meta: dict | None,
            force: bool) -> dict | None:
    """META'yı yeni nesle geçirir; çakışmada META'yı yeniden okur.

    Döner: {"previous": geçişten önceki META} ya da (ensure yarışı kaybedildiyse) None. Yanıtı kaybolmuş ama
    uygulanmış bir deneme (META zaten bizim neslimizde) başarı sayılır; bölümümüz asla silinmez.
    """
    for attempt in range(MAX_ATTEMPTS):
        previous = meta["generation"] if meta else None
        try:
            t.put_if(meta_item(run_id, gen, day, len(entries), previous), expected_meta(meta))
            return {"previous": meta}
        except Conflict:
            now = t.get(memory_meta_key(run_id))
            if now is not None and now.get("generation") == gen:
                return {"previous": meta}
            if not force and is_seeded(now):
                return None
            meta = now
            time.sleep(random.random() * min(1.0, 0.02 * 2 ** attempt))
    raise StorageConflictError("DynamoDB: hafıza tohumu eşzamanlı yazımlar yüzünden işlenemedi")


def seed_generation(t: DynamoTable, run_id: str, day: int, make_entries: Callable[[], list[dict]],
                    force: bool) -> Snapshot | None:
    """Yeni nesil tohumlar ve kurulu Snapshot'ı döndürür; atlandıysa ya da yarış kaybedildiyse None."""
    meta = t.get(memory_meta_key(run_id))
    if can_skip(meta, day, force):
        return None
    entries = list(make_entries())
    gen = new_generation()
    try:
        t.batch_put(entry_item(run_id, gen, e, i) for i, e in enumerate(entries))
        switched = _switch(t, run_id, gen, day, entries, meta, force)
    except Exception:
        purge(t, run_id, gen)             # yarım kalmış tohum bölümü artık bırakılmaz
        raise
    if switched is None:
        purge(t, run_id, gen)
        return None
    old = switched["previous"]
    purge(t, run_id, old.get("previous_generation") if old else None)
    return Snapshot(generation=gen, version=0, next_seq=len(entries), seqs={e["id"]: i for i, e in enumerate(entries)},
                    state=MemoryState(seed_day=day, entries=tuple(entries), log=()))

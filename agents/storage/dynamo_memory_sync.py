"""Hafıza önbelleğini tablo ile eşitler: nesil değiştiyse tam yükleme, sürüm arttıysa yalnız yeni LOG kayıtları.

Önbellek bir `Snapshot`tır (değişmez). META.version, son işlenmiş değişikliğin sırasıdır; LOG#{v} kaydı ile ilgili
giriş aynı işlemde yazıldığından, (önbellek sürümü, META sürümü] aralığındaki LOG'lar eksiksiz okunur ve yalnız
işaret ettikleri girişler BatchGetItem ile (tutarlı) yeniden alınır.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .base import MemoryState
from .dynamo_keys import PK, SK, entry_key, log_sk, memory_partition
from .dynamo_table import DynamoTable, decode, encode, payload


@dataclass(frozen=True)
class Snapshot:
    generation: str | None = None
    version: int = 0
    next_seq: int = 0
    seqs: Mapping[str, int] = field(default_factory=dict)      # giriş kimliği → ekleme sırası (_seq)
    state: MemoryState = field(default_factory=MemoryState)


EMPTY = Snapshot()
LOG_KEEP = 500          # tam yüklemede okunan son günlük satırı (dosya deposu da diskte 500 tutar)
ENTRY_RANGE = ("ENTRY#", "ENTRY$")     # "$" "#"dan hemen sonra gelir: tüm ENTRY# anahtarları


def entry_item(run_id: str, generation: str, entry: dict, seq: int) -> dict:
    return {**encode(entry), **entry_key(run_id, generation, entry["id"]), "_seq": seq}


def log_item(run_id: str, generation: str, version: int, record: dict) -> dict:
    return {**encode(record), PK: memory_partition(run_id, generation), SK: log_sk(version)}


def _seq(item: dict) -> int:
    return int(item["_seq"])


def full_load(t: DynamoTable, run_id: str, meta: dict) -> Snapshot:
    """META okunduktan sonra bölüm sorgulanır: girişler en az META sürümü kadar yenidir; günlük o sürümde kesilir
    (yalnız son LOG_KEEP satır; eski LOG öğeleri tabloda kalır ama belleğe alınmaz)."""
    gen, version = meta["generation"], int(meta["version"])
    pk = memory_partition(run_id, gen)
    entries = sorted(t.query(pk, *ENTRY_RANGE), key=_seq)
    logs = t.query(pk, log_sk(max(1, version - LOG_KEEP + 1)), log_sk(version)) if version > 0 else []
    return Snapshot(generation=gen, version=version, next_seq=int(meta.get("next_seq", 0)),
                    seqs={i["id"]: _seq(i) for i in entries},
                    state=MemoryState(seed_day=decode(meta.get("seed_day")), entries=tuple(payload(i) for i in entries),
                                      log=tuple(payload(i) for i in logs)))


def incremental(t: DynamoTable, run_id: str, snap: Snapshot, meta: dict) -> Snapshot:
    gen, version = snap.generation, int(meta["version"])
    pk = memory_partition(run_id, gen)
    logs = t.query(pk, log_sk(snap.version + 1), log_sk(version))
    ids = list(dict.fromkeys(i["record"] for i in logs))
    items = t.batch_get([entry_key(run_id, gen, x) for x in ids])
    if len(logs) != version - snap.version or len(items) != len(ids):
        return full_load(t, run_id, meta)              # beklenmeyen boşluk: güvenli yol
    fresh = {i["id"]: i for i in items}
    kept = tuple(payload(fresh[e["id"]]) if e["id"] in fresh else e for e in snap.state.entries)
    added = sorted((i for i in items if i["id"] not in snap.seqs), key=_seq)
    state = MemoryState(seed_day=decode(meta.get("seed_day")), entries=(*kept, *(payload(i) for i in added)),
                        log=(*snap.state.log, *(payload(i) for i in logs)))
    return Snapshot(generation=gen, version=version, next_seq=int(meta.get("next_seq", 0)),
                    seqs={**snap.seqs, **{i["id"]: _seq(i) for i in added}}, state=state)


def refresh(t: DynamoTable, run_id: str, snap: Snapshot, meta: dict | None) -> Snapshot:
    if meta is None:
        return EMPTY
    if meta["generation"] != snap.generation:
        return full_load(t, run_id, meta)
    if int(meta["version"]) <= snap.version:
        return snap
    return incremental(t, run_id, snap, meta)

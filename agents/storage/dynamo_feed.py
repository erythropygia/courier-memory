"""Ajan akışı deposu: DynamoDB (CM_STORAGE=dynamodb). Anahtar düzeni için bkz. dynamo_keys.

Ekleme: FEED/META.seq koşullu artırılır ve EVENT#{n} aynı TransactWriteItems'ta yazılır; böylece süreçler arası
numaralar boşluksuz ve sıralıdır (okuyucu `after` ile kaldığı yerden devam edebilir). Güncelleme: tek UpdateItem
(alan başına SET; farklı alanlara eşzamanlı güncellemeler birbirini ezmez). Okuma: META + aralık sorgusu
(son MAX_EVENTS olay), tutarlı okuma. Reset: yeni nesil; önceki nesil bir reset boyunca tutulur, öncekiler silinir.
"""
from __future__ import annotations

from typing import Callable

from boto3.dynamodb.conditions import Attr

from .dynamo_keys import INITIAL_GENERATION, PK, SK, event_key, event_sk, feed_meta_key, feed_partition
from .dynamo_memory_seed import new_generation
from .dynamo_table import Conflict, DynamoTable, encode, payload, purge_partition, put_op, retry_conflicts, update_op

RESERVED_FIELDS = (PK, SK, "_seq")


def _seq_op(meta: dict | None, n: int) -> dict:
    if meta is None:
        return put_op({**feed_meta_key(), "generation": INITIAL_GENERATION, "seq": n}, exists=False)
    return update_op(feed_meta_key(), {"seq": n}, {"generation": meta["generation"], "seq": meta["seq"]})


class DynamoFeedRepository:
    def __init__(self, table: DynamoTable, max_events: Callable[[], int]):
        self.table = table
        self._max_events = max_events

    def _meta(self) -> dict | None:
        return self.table.get(feed_meta_key())

    def events(self, after: int = 0) -> list[dict]:
        meta = self._meta()
        if meta is None:
            return []
        seq = int(meta["seq"])
        lo = max(int(after), seq - self._max_events())
        if lo >= seq:
            return []
        items = self.table.query(feed_partition(meta["generation"]), event_sk(lo + 1), event_sk(seq))
        return [payload(i) for i in items]

    def append(self, build: Callable[[int], dict]) -> dict:
        return retry_conflicts(lambda: self._append_once(build))

    def _append_once(self, build: Callable[[int], dict]) -> dict:
        meta = self._meta()
        n = (int(meta["seq"]) if meta else 0) + 1
        gen = meta["generation"] if meta else INITIAL_GENERATION
        event = build(n)
        item = {**encode(event), **event_key(gen, n)}
        self.table.transact([_seq_op(meta, n), put_op(item, exists=False)])
        return event

    def update(self, n: int, fields: dict) -> dict | None:
        bad = [k for k in fields if k in RESERVED_FIELDS]
        if bad:
            raise ValueError(f"Akış olayında değiştirilemeyen alan: {', '.join(bad)}")
        meta = self._meta()
        if meta is None:
            return None
        key = event_key(meta["generation"], int(n))
        if not fields:
            item = self.table.get(key)
            return payload(item) if item else None
        return self._set_fields(key, fields)

    def _set_fields(self, key: dict, fields: dict) -> dict | None:
        from botocore.exceptions import ClientError

        names = {f"#f{i}": k for i, k in enumerate(fields)}
        values = {f":x{i}": encode(v) for i, v in enumerate(fields.values())}
        expr = "SET " + ", ".join(f"#f{i} = :x{i}" for i in range(len(fields)))

        def once() -> dict | None:
            try:
                resp = self.table.table.update_item(Key=key, UpdateExpression=expr, ConditionExpression=Attr(PK).exists(),
                                                    ExpressionAttributeNames=names, ExpressionAttributeValues=values,
                                                    ReturnValues="ALL_NEW")
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code")
                if code == "ConditionalCheckFailedException":
                    return None                    # olay yok
                if code == "TransactionConflictException":
                    raise Conflict(code) from e    # öğe o anda bir işlemde: yeniden dene
                raise
            return payload(resp["Attributes"])

        return retry_conflicts(once)

    def reset(self) -> None:
        retry_conflicts(self._reset_once)

    def _reset_once(self) -> None:
        meta = self._meta()
        cond = Attr(PK).not_exists() if meta is None else Attr("generation").eq(meta["generation"])
        gen = new_generation()
        item = {**feed_meta_key(), "generation": gen, "seq": 0, "previous_generation": meta["generation"] if meta else None}
        try:
            self.table.put_if(item, cond)
        except Conflict:
            now = self._meta()
            if now is None or now.get("generation") != gen:   # yanıtı kaybolmuş ama uygulanmış deneme değilse
                raise
        self._purge(meta.get("previous_generation") if meta else None)

    def _purge(self, generation: str | None) -> None:
        if generation:
            purge_partition(self.table, feed_partition(generation))

"""DynamoDB tablo erişimi: tembel istemci, tür dönüşümü, sayfalı sorgu, toplu yazım/okuma, koşullu işlem.

boto3 yalnız ilk çağrıda içe aktarılır ve istemci ilk kullanımda kurulur (file modunda hiç yüklenmez).
Sayılar DynamoDB'de Decimal'dır: yazarken float → Decimal, okurken tam sayı → int, diğerleri → float.
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from decimal import Decimal
from typing import Any, Callable, Iterable, TypeVar

from .base import StorageConflictError
from .dynamo_keys import PK, SK

T = TypeVar("T")
log = logging.getLogger(__name__)
MAX_ATTEMPTS = 16
BATCH_GET_LIMIT = 100
INTERNAL = (PK, SK, "_seq")
CONFLICT_CODES = ("ConditionalCheckFailed", "TransactionConflict")


class Conflict(Exception):
    """Koşullu yazım başka bir sürecin yazımıyla çakıştı; durum yeniden okunup denenmeli."""


def is_conflict_error(e: Exception) -> bool:
    """Tekil PutItem/UpdateItem için çakışma: koşul tutmadı ya da öğe o anda başka bir işlemin içinde."""
    code = (getattr(e, "response", None) or {}).get("Error", {}).get("Code", "")
    return code in ("ConditionalCheckFailedException", "TransactionConflictException")


def encode(value: Any) -> Any:
    """Python değeri → DynamoDB'ye yazılabilir değer (float yerine Decimal; tuple → list)."""
    return json.loads(json.dumps(value, ensure_ascii=False), parse_float=Decimal)


def decode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() and value.as_tuple().exponent >= 0 else float(value)
    if isinstance(value, dict):
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode(v) for v in value]
    return value


def payload(item: dict) -> dict:
    """Tablo öğesinden uygulama verisi: anahtar ve iç alanlar çıkarılır, sayılar dönüştürülür."""
    return decode({k: v for k, v in item.items() if k not in INTERNAL})


def put_op(item: dict, *, exists: bool) -> dict:
    """TransactWriteItems Put adımı; koşul: öğe var (exists=True) ya da yok.

    İşlem adımlarında boto3 koşul kurucuları (Attr) kullanılamaz (yer tutucuları üst düzeye taşır), bu yüzden
    ifadeler burada açıkça yazılır.
    """
    fn = "attribute_exists" if exists else "attribute_not_exists"
    return {"Put": {"Item": item, "ConditionExpression": f"{fn}(#pk)", "ExpressionAttributeNames": {"#pk": PK}}}


def update_op(key: dict, sets: dict, expect: dict) -> dict:
    """TransactWriteItems Update adımı: `sets` alanlarını yazar; `expect` alanları okunan değerlere eşit olmalı."""
    names = {f"#s{i}": k for i, k in enumerate(sets)} | {f"#e{i}": k for i, k in enumerate(expect)}
    values = {f":s{i}": v for i, v in enumerate(sets.values())} | {f":e{i}": v for i, v in enumerate(expect.values())}
    return {"Update": {"Key": key, "UpdateExpression": "SET " + ", ".join(f"#s{i} = :s{i}" for i in range(len(sets))),
                       "ConditionExpression": " AND ".join(f"#e{i} = :e{i}" for i in range(len(expect))),
                       "ExpressionAttributeNames": names, "ExpressionAttributeValues": values}}


def retry_conflicts(op: Callable[[], T], attempts: int = MAX_ATTEMPTS) -> T:
    """Çakışmada üstel geri çekilme + rastgele bekleme ile yeniden dener."""
    for i in range(attempts):
        try:
            return op()
        except Conflict:
            time.sleep(random.random() * min(1.0, 0.02 * 2 ** i))
    raise StorageConflictError(f"DynamoDB: eşzamanlı yazım {attempts} denemede işlenemedi")


class DynamoTable:
    def __init__(self, name: str, region: str | None = None):
        self.name = name
        self.region = region
        self._table = None
        self._lock = threading.Lock()

    @property
    def table(self):
        if self._table is None:
            with self._lock:
                if self._table is None:
                    import boto3
                    from botocore.config import Config

                    cfg = Config(retries={"mode": "standard", "max_attempts": 5}, connect_timeout=5, read_timeout=10)
                    session = boto3.session.Session()     # varsayılan oturum iş parçacıkları arasında güvenli değil
                    self._table = session.resource("dynamodb", region_name=self.region, config=cfg).Table(self.name)
        return self._table

    @property
    def client(self):
        """Tür dönüşümünü otomatik yapan alt düzey istemci (resource.meta.client)."""
        return self.table.meta.client

    def get(self, key: dict) -> dict | None:
        return self.table.get_item(Key=key, ConsistentRead=True).get("Item")

    def query(self, pk: str, lo: str | None = None, hi: str | None = None, keys_only: bool = False) -> list[dict]:
        """Bir bölümün öğeleri (SK sıralı, tutarlı okuma); lo ve hi verilirse SK aralığı [lo, hi]."""
        from boto3.dynamodb.conditions import Key

        cond = Key(PK).eq(pk)
        if lo is not None and hi is not None:
            cond = cond & Key(SK).between(lo, hi)
        kw: dict = {"TableName": self.name, "KeyConditionExpression": cond, "ConsistentRead": True}
        if keys_only:
            kw.update(ProjectionExpression="#pk, #sk", ExpressionAttributeNames={"#pk": PK, "#sk": SK})
        pages = self.client.get_paginator("query").paginate(**kw)
        return [item for page in pages for item in page.get("Items", [])]

    def batch_put(self, items: Iterable[dict]) -> int:
        n = 0
        with self.table.batch_writer() as w:
            for item in items:
                w.put_item(Item=item)
                n += 1
        return n

    def batch_delete(self, keys: Iterable[dict]) -> int:
        n = 0
        with self.table.batch_writer(overwrite_by_pkeys=[PK, SK]) as w:
            for key in keys:
                w.delete_item(Key=key)
                n += 1
        return n

    def batch_get(self, keys: list[dict]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(keys), BATCH_GET_LIMIT):
            out.extend(self._batch_get_chunk(keys[i:i + BATCH_GET_LIMIT]))
        return out

    def _batch_get_chunk(self, keys: list[dict]) -> list[dict]:
        out: list[dict] = []
        request = {self.name: {"Keys": keys, "ConsistentRead": True}}
        for attempt in range(MAX_ATTEMPTS):
            resp = self.client.batch_get_item(RequestItems=request)
            out.extend(resp.get("Responses", {}).get(self.name, []))
            request = resp.get("UnprocessedKeys") or {}
            if not request:
                return out
            time.sleep(random.random() * min(1.0, 0.05 * 2 ** attempt))
        raise StorageConflictError("DynamoDB: BatchGetItem işlenmemiş anahtarları bitiremedi")

    def transact(self, ops: list[dict]) -> None:
        """TransactWriteItems; koşul tutmazsa Conflict. ops: [{"Put"|"Update": {...}}] (TableName eklenir)."""
        items = [{kind: {"TableName": self.name, **spec}} for op in ops for kind, spec in op.items()]
        try:
            self.client.transact_write_items(TransactItems=items)
        except self.client.exceptions.TransactionCanceledException as e:
            codes = [r.get("Code") for r in e.response.get("CancellationReasons", [])]
            if any(c in CONFLICT_CODES for c in codes):
                raise Conflict(codes) from e
            raise

    def put_if(self, item: dict, condition) -> None:
        """Koşullu PutItem; koşul tutmazsa ya da öğe başka bir işlemdeyse Conflict."""
        from botocore.exceptions import ClientError

        try:
            self.table.put_item(Item=item, ConditionExpression=condition)
        except ClientError as e:
            if is_conflict_error(e):
                raise Conflict(e.response["Error"]["Code"]) from e
            raise

def purge_partition(t: DynamoTable, pk: str) -> None:
    """Bir bölümü siler (eski nesiller). En iyi çaba: hata yalnız uyarıdır, veri yeni nesilde güvendedir."""
    try:
        t.batch_delete([{PK: i[PK], SK: i[SK]} for i in t.query(pk, keys_only=True)])
    except Exception as e:  # noqa: BLE001 - temizlik ana işlemi bozmamalı
        log.warning("Eski DynamoDB bölümü silinemedi (%s): %s", pk, e)

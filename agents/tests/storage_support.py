"""Depolama testleri için ortak yardımcılar: küçük sahte çalıştırma ve moto üzerinde DynamoDB tablosu.

Gerçek AWS'ye gidilmez: her test `mock_aws` bağlamında sahte kimlikle çalışır.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

TEST_TABLE = "cm-test"
TEST_REGION = "eu-central-1"
FAKE_ENV = {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing", "AWS_SESSION_TOKEN": "testing",
            "AWS_SECURITY_TOKEN": "testing", "AWS_DEFAULT_REGION": TEST_REGION, "AWS_REGION": TEST_REGION}
SEED_DAY = 30


def _seed_entries() -> list[dict]:
    rows = [(3, "safety", 1, None), (5, "bell", 2, None), (5, "park", 1, None), (8, "roadwork", 3, 35), (9, "reception", 1, None)]
    return [{"id": f"M{900 + i:05d}", "address": a, "kind": k, "text": f"tohum {k}", "sources": s, "first_day": 20,
             "last_day": 28, "temporary": ttl is not None, "ttl_until": ttl} for i, (a, k, s, ttl) in enumerate(rows)]


@dataclass
class FakeRun:
    """MemoryBook'un kullandığı RunData yüzeyi: run_id, addr_kind, memory_snapshot(day)."""
    run_id: str = "fake-run"
    addr_kind: list = field(default_factory=lambda: ["house"] * 20)
    snapshot_calls: int = 0

    def memory_snapshot(self, day: int) -> list[dict]:
        self.snapshot_calls += 1
        return [dict(e, last_day=min(e["last_day"], day)) for e in _seed_entries()]


def _serialize_moto_calls(monkeypatch) -> None:
    """moto'nun DynamoDB arka ucu kilitsizdir (başarısız işlemde tabloyu kopyasından geri yükler); gerçek DynamoDB'de
    her çağrı atomiktir. Bunu taklit etmek için tek tek API çağrıları sıraya alınır; bizim oku-değiştir-yaz
    döngülerimiz yine iş parçacıkları arasında iç içe geçer (eşzamanlılık testleri bunu sınar)."""
    from moto.dynamodb.responses import DynamoHandler

    lock = threading.Lock()
    original = DynamoHandler.call_action

    def call_action(self):
        with lock:
            return original(self)

    monkeypatch.setattr(DynamoHandler, "call_action", call_action)


@contextmanager
def moto_table(monkeypatch, name: str = TEST_TABLE) -> Iterator[None]:
    """moto ile sahte DynamoDB; tabloyu dağıtım betiğiyle aynı şemayla kurar ve CM_STORAGE=dynamodb yapar."""
    from moto import mock_aws

    for k, v in FAKE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CM_STORAGE", "dynamodb")
    monkeypatch.setenv("CM_DYNAMODB_TABLE", name)
    _serialize_moto_calls(monkeypatch)
    with mock_aws():
        import boto3

        from agents.storage.dynamo_keys import table_definition

        boto3.client("dynamodb", region_name=TEST_REGION).create_table(**table_definition(name))
        yield


def file_env(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("CM_STORAGE", "file")
    return tmp_path / "live_memory.json"

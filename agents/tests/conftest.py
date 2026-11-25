"""Depolama testleri: aynı davranış senaryoları her iki arka uçta (file, dynamodb/moto) koşar."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from agents.tests.storage_support import FakeRun, file_env, moto_table


@dataclass
class Storage:
    """Aynı depoya bağlanan yeni MemoryBook/AgentFeed örnekleri üretir (her örnek ayrı bir süreç gibi)."""
    backend: str
    memory_path: Path
    run: FakeRun

    def book(self, run: FakeRun | None = None):
        from agents.memorybook import MemoryBook

        return MemoryBook(run or self.run, self.memory_path)

    def feed(self):
        from agents.feed import AgentFeed

        return AgentFeed(self.memory_path.with_name("agent_feed.json"))


@pytest.fixture(params=["file", "dynamodb"])
def storage(request, monkeypatch, tmp_path):
    path = file_env(monkeypatch, tmp_path)
    if request.param == "file":
        yield Storage("file", path, FakeRun())
        return
    with moto_table(monkeypatch):
        yield Storage("dynamodb", path, FakeRun())


@pytest.fixture
def dynamo(monkeypatch, tmp_path):
    """Yalnız DynamoDB'ye özgü davranışlar (süreçler arası görünürlük, eşzamanlılık, tohum idempotentliği)."""
    path = file_env(monkeypatch, tmp_path)
    with moto_table(monkeypatch):
        yield Storage("dynamodb", path, FakeRun())

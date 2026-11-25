"""API uçtan uca CM_STORAGE=dynamodb ile (moto): sıfırlama, Değerlendirme Ajanı, akış, geri bildirim, yeni süreç."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agents.tests.storage_support import moto_table


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CM_LLM_MODE", "mock")
    monkeypatch.setenv("CM_MEMORY_FILE", str(tmp_path / "mem.json"))
    from api import main

    with moto_table(monkeypatch):
        main.sv.cache_clear()
        yield TestClient(main.app), main
        main.sv.cache_clear()          # sonraki testler dosya arka ucuyla yeni Services kursun


def test_dynamodb_backed_demo_flow(client):
    c, main = client
    d = c.get("/api/meta").json()["critical"]["day"]
    assert c.post("/api/demo/reset", json={"day": d}).json()["ok"]
    total = c.get("/api/memory/summary", params={"day": d}).json()["total"]
    assert total > 100 and c.get("/api/status").json()["memory_seed_day"] == d
    r = c.post("/api/review/run", json={"day": d}).json()
    assert r["report"]["summary"]
    ev = c.get("/api/feed", params={"agent": "review"}).json()["events"]
    assert any(e["type"] == "report" for e in ev)
    pending = [e for e in ev if e["status"] == "awaiting_approval"]
    if pending:
        ok = c.post("/api/review/decision", json={"day": d, "n": pending[0]["n"], "decision": "approve"}).json()
        assert ok["status"] == "approved"
    rec = c.get("/api/memory", params={"day": d}).json()["entries"][0]
    fb = c.post("/api/memory/feedback", json={"day": d, "record": rec["id"], "valid": True}).json()
    assert fb["ok"] and fb["record"]["sources"] == rec["sources"] + 1
    assert not Path(os.environ["CM_MEMORY_FILE"]).exists()          # durum dosyaya değil tabloya yazıldı

    main.sv.cache_clear()                                         # yeni süreç: durum tablodan okunur
    again = c.get("/api/memory", params={"day": d}).json()["entries"]
    assert next(e for e in again if e["id"] == rec["id"])["sources"] == rec["sources"] + 1
    assert any(e["type"] == "report" for e in c.get("/api/feed", params={"agent": "review"}).json()["events"])

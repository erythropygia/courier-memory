"""Değerlendirme Ajanı, Bölge Ajanı, ajan akışı, gerçek gün ve demo sıfırlama uçları (mock)."""
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["CM_LLM_MODE"] = "mock"
    os.environ["CM_MEMORY_FILE"] = str(tmp_path_factory.mktemp("m") / "mem.json")
    from api import main
    main.sv.cache_clear()
    return TestClient(main.app)


def _day(client):
    return client.get("/api/meta").json()["critical"]["day"]


def test_review_feed_and_decision(client):
    d = _day(client)
    assert client.post("/api/demo/reset", json={"day": d}).json()["ok"]
    r = client.post("/api/review/run", json={"day": d}).json()
    assert r["report"]["summary"] and r["trace"][-1]["type"] == "done"
    assert client.get("/api/review").json()["last_report"]["day"] == d
    ev = client.get("/api/feed", params={"agent": "review"}).json()["events"]
    assert any(e["type"] == "report" for e in ev)
    pending = [e for e in ev if e["status"] == "awaiting_approval"]
    if pending:
        ok = client.post("/api/review/decision", json={"day": d, "n": pending[0]["n"], "decision": "approve"}).json()
        assert ok["status"] == "approved"
        assert client.post("/api/review/decision", json={"day": d, "n": pending[0]["n"], "decision": "approve"}).status_code == 409
    assert client.post("/api/review/decision", json={"day": d, "n": 10**6, "decision": "undo"}).status_code == 404


def test_region_branch_and_run(client):
    d = _day(client)
    b = client.get("/api/region/branch", params={"day": d}).json()
    assert b["layer"] == "branch" and b["manager_summary"]
    r = client.post("/api/region/run", json={"day": d}).json()
    assert r["manager_summary"] and r["mode"] == "mock"
    assert "agent_report" in client.get("/api/region/branch", params={"day": d}).json()


def test_real_day_endpoints(client):
    g = client.get("/api/real-day/2026-05-05").json()
    assert g["stops"] and g["rates"]["fail_unfamiliar"] > g["rates"]["fail_familiar"]
    m = client.get("/api/real-day/2026-05-05/memory").json()
    assert m["expected_fails"]["memory"] <= m["expected_fails"]["memoryless"]
    k = client.get(f"/api/real-day/2026-05-05/cluster/{g['clusters'][0]['id']}").json()
    assert k["stop"] == len(k["stops"]) and k["cluster_card"]["courier_card"]
    t = client.get("/api/real-day/2026-05-05/transfer").json()
    assert t["after"]["courier"] == t["before"]["courier"] - 1
    assert client.get("/api/real-day/2026-05-06").status_code == 404
    assert client.get("/api/real-day/xx").status_code == 422
    assert client.get("/api/real-day/2026-05-05/cluster/999").status_code == 404

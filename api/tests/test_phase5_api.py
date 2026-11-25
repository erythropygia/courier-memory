"""Faz 5 API: sabah ayrıştırma planı ve indirme okutması (gönderi → raf talimatı)."""
import pytest
from fastapi.testclient import TestClient

import api.main as M


@pytest.fixture
def c(monkeypatch):
    monkeypatch.setenv("CM_LLM_MODE", "mock")
    M.sv.cache_clear()
    yield TestClient(M.app)
    M.sv.cache_clear()


def test_morning_plan_and_scan(c):
    day = M.sv().run.meta["critical"]["day"]
    r = c.get(f"/api/morning/{day}")
    assert r.status_code == 200
    s = r.json()
    assert s["plan"]["shelf_count"] > 0 and s["summary"]["enabled"]
    leaving = [x for x in s["departures"] if x["departure"] is not None and x["departure_current"] is not None]
    assert leaving and all(x["departure"] < x["departure_current"] for x in leaving)               # okutmada ayrıştırma → daha erken çıkış
    g = s["example_shipments"][0]
    o = c.post("/api/morning/scan", json={"day": day, "shipment": g}).json()
    assert not o["exception"] and isinstance(o["shelf"], int) and 1 <= o["load_order"] <= o["stop"]
    assert o["load_order"] == o["stop"] - o["stop_order"] + 1
    e = c.post("/api/morning/scan", json={"day": day, "shipment": f"G{day}-0-1"}).json()
    assert e["exception"] and e["shelf"] == "flexible"

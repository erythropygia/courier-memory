"""Faz 2b API: teslim zamanı analizi uç noktaları (Faz 3b arayüzü kullanır)."""
import pytest
from fastapi.testclient import TestClient

import api.main as M


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setenv("CM_LLM_MODE", "mock")
    M.sv.cache_clear()
    from agents.delivery_time import time_source
    cl = TestClient(M.app)
    time_source(M.sv().run).reset()
    yield cl
    time_source(M.sv().run).reset()
    M.sv.cache_clear()


def _reset(c):
    """Canlı hafıza örnek gününün simülasyon hafızasına döner (paylaşılan kitap başka günden tohumlanmış olabilir)."""
    day = M.sv().run.meta["time_example"]["day"]
    assert c.post("/api/memory/reset", json={"day": day}).status_code == 200


def test_time_example(c):
    _reset(c)
    r = c.get("/api/time/example")
    assert r.status_code == 200
    j = r.json()
    ex = j["example"]
    assert j["app_data"] and len(ex["history"]) >= 6 and ex["finding"]["text"]
    assert j["agent"]["finding"]["text"] == ex["finding"]["text"]              # ajan aynı kayıttan aynı bulguyu çıkarır
    assert j["route"]["change"]["address"] == ex["address"] and j["route"]["same_as_sim"] is True
    assert len(j["agent"]["table"]["slots"]) == 5 and j["hidden_truth"]["profile"]
    assert j["summary"]["carried_stops"]["stop"] > 0


def test_time_day_and_address(c):
    ex = c.get("/api/time/example").json()["example"]
    g = c.get(f"/api/time/{ex['day']}").json()
    assert g["window_finding"] > 0 and g["selection"]["min_confidence"] == "mid" and g["findings"][0]["text"]
    assert {"address", "label", "bad_slot", "good_slot", "level", "cluster", "courier"} <= set(g["findings"][0])
    assert c.get(f"/api/time/{ex['day']}?min_confidence=high").json()["window_finding"] <= g["window_finding"]
    a = c.get(f"/api/time/{ex['day']}/address/{ex['address']}").json()
    assert a["finding"]["address"] == ex["address"] and len(a["history"]) == len(ex["history"])
    assert sum(x["attempt"] for x in a["table"]["slots"]) <= len(a["history"])
    assert c.get("/api/time/9999").status_code == 404
    assert c.get(f"/api/time/{ex['day']}/address/99999999").status_code == 404
    assert c.get(f"/api/time/{ex['day']}?min_confidence=cok").status_code == 422


def test_route_no_time_comparison(c):
    _reset(c)
    ex = c.get("/api/time/example").json()["example"]
    r = c.get(f"/api/route/{ex['day']}/{ex['courier']}").json()
    k = r["comparison"]
    assert k["diff"]["time_carried"] >= 1 and k["no_time"] is not None
    assert k["memory"]["expected_absence"] < k["no_time"]["expected_absence"]
    assert any(x["kind"] == "time_preference" for x in r["constraints"]) and r["time_findings"]

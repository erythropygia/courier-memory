"""Faz 2c API: sert kısıt ve kaydırılamayan bulgu alternatifleri (geriye uyumlu yeni alanlar)."""
import pytest
from fastapi.testclient import TestClient

import api.main as M


@pytest.fixture
def c(monkeypatch):
    monkeypatch.setenv("CM_LLM_MODE", "mock")
    M.sv.cache_clear()
    from agents.delivery_time import time_source
    cl = TestClient(M.app)
    time_source(M.sv().run).reset()
    yield cl
    time_source(M.sv().run).reset()
    M.sv.cache_clear()


def _reset(c, key="time_example"):
    day = M.sv().run.meta[key]["day"]
    assert c.post("/api/memory/reset", json={"day": day}).status_code == 200


def test_time_example_constraint_fields(c):
    _reset(c)
    j = c.get("/api/time/example").json()
    ex = j["example"]
    assert ex["route"]["overtime_min"]["memory"] == 0 and ex["change"]["extra_min"] <= 0.05
    assert j["constraint"]["violation"] == 0 and j["constraint"]["tolerance_min"] == 0
    k = j["example_constraint"]
    assert k and k["option"] in ("transfer", "next_day", "evening_delivery_point") and k["decision"] == "manager" and k["text"]


def test_time_alternatives_endpoint(c):
    _reset(c, "time_example_constraint")
    k = c.get("/api/time/example").json()["example_constraint"]
    j = c.get(f"/api/time/{k['day']}/alternatives").json()
    assert j["unshiftable"] >= 1 and j["constraint"]["shift_end"] == "17:48"
    x = next(x for x in j["proposals"] if x["address"] == k["address"])
    assert x["option"] == k["option"] and x["sms_text"] and x["text"]
    assert c.get("/api/time/9999/alternatives").status_code == 404


def test_route_constraint_fields(c):
    _reset(c)
    ex = c.get("/api/time/example").json()["example"]
    r = c.get(f"/api/route/{ex['day']}/{ex['courier']}").json()
    k = r["comparison"]["route_constraint"]
    assert k["after_min"] <= k["border_min"] + 0.01 and "time_unshiftable" in r
    assert "time_unshiftable" in r["comparison"]["diff"]

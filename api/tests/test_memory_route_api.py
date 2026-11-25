"""Uç noktaları: rota karşılaştırma, kim gitsin, hasat (soru → simüle cevap → hafıza → rota), öğrenme eğrisi."""
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


def test_route_and_candidates(client):
    c = client.get("/api/meta").json()["critical"]
    d, hero = c["day"], c["courier"]
    r = client.get(f"/api/route/{d}/{hero}").json()
    assert r["plan_source"] == "simulation_plan" and r["constraint_source"] == "memory"
    k = r["comparison"]
    assert set(k) >= {"memoryless", "memory", "diff", "simulation"} and k["simulation"]["memory"]["minutes"] > 0
    assert client.get(f"/api/route/{d}/NONE").status_code == 404
    a = client.get(f"/api/orchestrator/candidates/{d}").json()
    assert a["capacity"]["shortfall"] == len(a["candidates"]["proposed"]) and a["candidates"]["tie"] is False
    assert c.get("memory_gain", {}).get("mins") is not None


def test_harvest_flow(client):
    d = client.get("/api/meta").json()["critical"]["day"]
    assert client.get(f"/api/harvest/{d}").status_code == 404
    h = client.post("/api/harvest/plan", json={"day": d}).json()
    assert h["questions"] and h["trace"][0]["type"] == "start"
    q = h["questions"][0]
    x = client.post("/api/harvest/simulate-answer", json={"question_id": q["id"]}).json()
    assert x["question"]["status"] == "answered" and x["question"]["simulate"] is True
    assert client.post("/api/harvest/answer", json={"question_id": q["id"], "text": "tekrar"}).status_code == 409
    assert client.post("/api/harvest/answer", json={"question_id": "YOK", "text": "x"}).status_code == 404
    q2 = h["questions"][1]
    y = client.post("/api/harvest/answer", json={"question_id": q2["id"], "text": "Zil bozuk, telefonla arayın."}).json()
    assert y["memory"]["type"] == "bell" and y["memory"]["address"]["id"] == q2["address"]
    lst = client.get(f"/api/harvest/{d}").json()
    assert sum(1 for s in lst["questions"] if s["status"] == "answered") == 2


def test_learning_and_summary(client):
    o = client.get("/api/summary").json()
    assert o["learning"] and o["ablation"] and o["learning_same_route"] and o["summary"]["memory_routing"]["daily"]
    g = client.get("/api/learning").json()
    assert g["first_week_paired_diff_C_minus_D"]["preventable_fails"][1] > 0      # %95 aralığın alt ucu > 0: ayrışıyor
    assert {"C", "D", "D_memoryless"} <= set(g["series"])
    assert o["sweep"]["headline"]["D_vs_C_pp"]["share_gt_0"] > 0.9

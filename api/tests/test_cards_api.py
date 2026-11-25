"""Faz 2d API: /api/cards, /api/approach, /api/note ile bilgi türü."""
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


def test_cards_and_approach_flow(client):
    m = client.get("/api/meta").json()
    d, c = m["critical"]["day"], m["critical"]["courier"]
    client.post("/api/memory/reset", json={"day": d})
    L = client.get(f"/api/cards/{d}/{c}").json()
    assert L["stops_with_cards"] == len(L["stops"]) and all(x["cards"] for x in L["stops"])
    full = client.get(f"/api/cards/{d}/{c}?all=true").json()["stops"]
    assert len(full) == L["stop"]
    s = next(x for x in full if not x["cards"])
    n = client.post("/api/note", json={"day": d, "courier": c, "lat": s["lat"], "lng": s["lng"],
                                      "text": "arabayı arka sokağa park edin, giriş kodu 7788"}).json()
    assert n["type"] == "park" and "7788" not in n["hint"] and n["personal_data_redacted"] is True
    y = client.post("/api/approach", json={"day": d, "courier": c, "lat": s["lat"] + 0.002, "lng": s["lng"],
                                           "next_order": s["order"]}).json()
    assert y["moment"] == "approaching" and y["cards"][0]["type"] == "park" and y["to_speak"]
    y2 = client.post("/api/approach", json={"day": d, "courier": c, "lat": s["lat"], "lng": s["lng"], "next_order": s["order"],
                                            "shown": [k["id"] for k in y["cards"]]}).json()
    assert y2["moment"] == "at_door" and y2["cards"] == []


def test_card_errors(client):
    m = client.get("/api/meta").json()
    d, c = m["critical"]["day"], m["critical"]["courier"]
    assert client.get(f"/api/cards/{d}/YOK").status_code == 404
    assert client.get(f"/api/cards/0/{c}").status_code == 404
    assert client.post("/api/approach", json={"day": d, "courier": c, "lat": 0, "lng": 0, "next_order": 10_000}).status_code == 422
    assert client.post("/api/approach", json={"day": d, "courier": c, "lat": 95, "lng": 0}).status_code == 422
    empty = client.post("/api/approach", json={"day": d, "courier": c, "lat": 0, "lng": 0}).json()
    assert empty["stop"] is None and empty["cards"] == []

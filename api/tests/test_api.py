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


def test_static_endpoints(client):
    m = client.get("/api/meta").json()
    assert m["app_data"] is True and m["critical"]["day"] in m["eval_days"]
    assert client.get("/api/status").json()["mode"] == "mock"
    o = client.get("/api/summary").json()
    assert set(o["summary"]["arms"]) == {"A", "B", "C", "D"}
    d = m["critical"]["day"]
    assert client.get(f"/api/day/D/{d}").json()["arm"] == "D"
    assert client.get("/api/day/D/0").status_code == 404


def test_agent_flow(client):
    m = client.get("/api/meta").json()
    d, c = m["critical"]["day"], m["critical"]["courier"]
    r = client.post("/api/assignment/propose", json={"day": d}).json()
    assert len(r["assignment"]) > 0 and r["rationale"] and r["total"]["expected_fails"] < r["comparison"]["history_blind_expected_fails"]
    q = client.post("/api/assignment/ask", json={"day": d, "question": f"{m['critical']['courier_name']} gelmezse ne olur?"}).json()
    assert q["assignment"] is not None and all(x["courier"] != c for x in q["assignment"])
    assert client.post("/api/assignment/approve", json={"day": d, "assignment": [{"cluster": x["cluster"], "courier": x["courier"]} for x in r["assignment"]]}).json()["ok"]
    b = client.get(f"/api/briefing/{d}/{c}").json()
    assert b["morning_briefing"] and b["route"]["courier"] == c
    s = b["route"]["stops"][3]
    n = client.post("/api/note", json={"day": d, "courier": c, "text": "zil bozuk Ayşe hanım çok huysuz 0555 000 00 00 arayın",
                                      "lat": s[1], "lng": s[2], "minute": s[4]}).json()
    assert n["status"] in ("saved", "updated") and n["type"] == "bell" and n["personal_data_redacted"] is True
    assert "Ayşe" not in (n["hint"] or "") and "0555" not in (n["hint"] or "")
    g = client.post("/api/note", json={"day": d, "courier": c, "text": "trafik berbattı bugün"}).json()
    assert g["status"] == "noise"
    e = client.get(f"/api/memory?day={d}&address={n['address']['id']}").json()["entries"]
    kid = next(x["id"] for x in e if x["kind"] == "bell")
    assert client.post("/api/memory/feedback", json={"day": d, "record": kid, "valid": False}).json()["ok"]
    assert all(x["id"] != kid for x in client.get(f"/api/memory?day={d}&address={n['address']['id']}").json()["entries"])
    assert client.get("/api/speech?text=merhaba").status_code == 501


def test_economics_endpoint(client):
    e = client.get("/api/economics").json()
    assert e["llm"]["daily_tl"] > 0 and e["gain"]["vs_C"]["return_multiple"] is not None
    e2 = client.get("/api/economics?model_memory=anthropic.claude-haiku-5-5").json()
    assert e2["llm"]["daily_tl"] < e["llm"]["daily_tl"]
    assert client.get("/api/economics?model_memory=offline").status_code == 400
    o = client.get("/api/summary").json()
    assert o["long_term"] is not None and o["calibration"] is not None

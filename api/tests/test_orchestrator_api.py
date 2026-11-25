"""Orkestratör uç noktaları: başlat → iz akışı (SSE ve poll) → senaryo sorusu → insan onayı → kesin plan."""
import json
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


def read_sse(resp) -> list[tuple[str, dict]]:
    out, ev = [], None
    for line in resp.iter_lines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: "):
            out.append((ev, json.loads(line[6:])))
    return out


def test_orchestrator_flow(client):
    d = client.get("/api/meta").json()["critical"]["day"]
    assert client.get(f"/api/plan/{d}").status_code == 404
    k = client.post("/api/orchestrator/start", json={"day": d, "manager_review": True}).json()   # müdür acil durum bildirdi
    kid = k["session_id"]
    with client.stream("GET", f"/api/orchestrator/session/{kid}/stream") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        evs = read_sse(r)
    tips = [t for t, _ in evs]
    assert tips[0] == "start" and tips[-2:] == ["awaiting_approval", "last"] and "tool" in tips and "result" in tips
    assert evs[-1][1]["status"] == "awaiting_approval"
    p = client.get(f"/api/orchestrator/session/{kid}?after=3").json()
    assert p["status"] == "awaiting_approval" and p["events"][0]["i"] == 3 and p["total_event"] == len(evs) - 1
    o = p["proposal"]
    assert o["borrowed"] and not o["idle_couriers"]
    q = client.post(f"/api/orchestrator/session/{kid}/ask", json={"question": f"{o['borrowed'][0]['name']} gelmezse ne olur?"}).json()
    assert q["response"] and len(q["alternatives"]) == 2 and q["trace"][-1]["type"] == "response"
    assert client.post(f"/api/orchestrator/session/{kid}/decision", json={"decision": "belki"}).status_code == 400
    res = client.post(f"/api/orchestrator/session/{kid}/decision", json={"decision": "approval", "note": "eligible"}).json()
    assert res["status"] == "finalized"
    assert client.get(f"/api/plan/{d}").json()["assignment"] == o["assignment"]
    assert client.post(f"/api/orchestrator/session/{kid}/decision", json={"decision": "approval"}).status_code == 400
    assert client.post(f"/api/orchestrator/session/{kid}/ask", json={"question": "Onur gelmezse?"}).status_code == 409
    last = client.get(f"/api/orchestrator/session/{kid}").json()["events"][-2:]
    assert [e["type"] for e in last] == ["human_decision", "done"] and last[0]["note"] == "eligible"


def test_sync_plan_and_errors(client):
    d = client.get("/api/meta").json()["critical"]["day"]
    r = client.post("/api/orchestrator/plan", json={"day": d}).json()                        # acil durum yok: temassız
    assert r["status"] == "finalized" and [e["type"] for e in r["events"][-2:]] == ["auto_decision", "done"] and r["escalation"] == []
    assert client.get(f"/api/plan/{d}").json()["assignment"] == r["proposal"]["assignment"]
    assert client.post(f"/api/orchestrator/session/{r['session_id']}/decision", json={"decision": "approval"}).status_code == 400
    r = client.post("/api/orchestrator/plan", json={"day": d, "manager_review": True}).json()
    assert r["status"] == "awaiting_approval" and r["events"][-1]["type"] == "awaiting_approval"
    assert client.get("/api/orchestrator/session/NONE").status_code == 404
    assert client.post("/api/orchestrator/plan", json={"day": 0}).status_code == 404
    assert client.get("/api/status").json()["models"]["orchestrator"]

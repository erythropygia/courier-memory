"""Canlı akış (api/live.py): tek koşu, çok izleyici; sekiz adım, temassız kapı, şifre sızmaz; göreli yönlendirme."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from api import live as L
from api.main import app


@pytest.fixture()
def fast(monkeypatch):
    monkeypatch.setattr(L, "TEMPO_ORCH", 0)
    monkeypatch.setattr(L, "TEMPO_REPLAY", 0)
    monkeypatch.setattr(L, "STEP_GAP", 0)
    monkeypatch.setattr(L, "LIVE", L.Live())
    import api.main as M
    monkeypatch.setattr(M, "LIVE", L.LIVE)
    yield L.LIVE
    day = M.meta()["critical"]["day"]
    TestClient(app).post("/api/demo/reset", json={"day": day})        # canlı hafıza koşu öncesine döner (diğer testler etkilenmez)


def wait(c, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = c.get("/api/live").json()
        if s["status"] != "running":
            return s
        time.sleep(0.2)
    raise AssertionError("canlı akış bitmedi")


def test_live_chain_runs_once_and_broadcasts_eight_steps(fast):
    c = TestClient(app)
    assert c.get("/api/live").json()["status"] == "idle"
    r = c.post("/api/live/start")
    assert r.status_code == 200 and r.json()["status"] == "running"
    assert c.post("/api/live/start").status_code == 409            # koşu sürerken ikinci başlatma yok
    s = wait(c)
    assert s["status"] == "done"
    ev = s["events"]
    types = [e["t"] for e in ev]
    assert types[0] == "run" and types[-1] == "end"
    assert [e["i"] for e in ev if e["t"] == "step"] == list(range(8))
    assert not [e for e in ev if e["t"] == "step_error"], [e for e in ev if e["t"] == "step_error"]
    res = {e["i"]: e["out"] for e in ev if e["t"] == "result"}
    assert len(res) == 8
    assert res[1]["auto"] is True                                  # demo günü: zincir temassız
    tools = [e["e"]["tool"] for e in ev if e["t"] == "ev" and e["e"]["type"] == "tool"]
    assert "core_assignment" in tools and len(tools) >= 20
    assert all(e["run"] == s["run_id"] and e["n"] == k for k, e in enumerate(ev))
    assert "2580" not in (res[3]["hint"] or "")                    # hafızaya şifre yazılmaz
    side = [e for e in ev if e["t"] == "side"]
    assert side and side[-1]["memory"]["total"] >= 1
    assert len(json.dumps(ev, ensure_ascii=False)) < 2_000_000        # telefona giden toplam veri sınırlı


def test_pull_restarts_viewer_on_new_run(fast):
    fast.start(target=lambda run: fast.emit("run"))
    time.sleep(0.1)
    evs, run, n, _ = fast.pull(None, 0)
    assert [e["t"] for e in evs] == ["run"] and n == 1
    assert fast.pull(run, n)[0] == []
    fast.status = "done"
    fast.start(target=lambda run: fast.emit("run"))
    time.sleep(0.1)
    evs, run2, _, _ = fast.pull(run, n)
    assert run2 == run + 1 and evs[0]["t"] == "run" and evs[0]["n"] == 0


@pytest.mark.parametrize("name", ["story", "flow", "demo"])
def test_trailing_slash_redirect_stays_relative(name):
    c = TestClient(app)
    for q in ("", "?n=//evil.example"):
        r = c.get(f"/{name}{q}", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == f"{name}/"

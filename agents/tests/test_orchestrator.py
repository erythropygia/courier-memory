"""Orkestratör: akış, araç sözleşmeleri, mock iz determinizmi, canlı yol ile aynı iz biçimi, insan onayı."""
import json

import pytest

from agents import Services
from agents.trace import Trace
from agents.llm import LLM
from agents.orchestrator import FINISH_PLAN, DayTools, SessionStore
from agents.route import RouteConstraint, RoutePlanner

PLAN_FLOW = ["start", "decision", "tool:read_volume", "result:read_volume", "decision", "tool:capacity_gap", "result:capacity_gap",
             "decision", "tool:neighbor_candidates", "result:neighbor_candidates", "decision", "tool:core_assignment", "result:core_assignment"]


@pytest.fixture
def sv(tmp_path):
    return Services.create(mode="mock", memory_file=tmp_path / "mem.json")


@pytest.fixture
def day(sv):
    return sv.run.meta["critical"]["day"]


def seq(events):
    return [e["type"] + (f":{e['tool']}" if e.get("tool") else "") for e in events]


def test_plan_flow_on_busy_day(sv, day):
    r = sv.orchestrator.plan(day)
    s = seq(r["trace"])
    assert s[:len(PLAN_FLOW)] == PLAN_FLOW
    assert s[-3:] == [f"tool:{FINISH_PLAN}", "proposal", "awaiting_approval"] and "tool:compute_route" in s
    assert all(e["source"] == "rule" for e in r["trace"]) and [e["i"] for e in r["trace"]] == list(range(len(r["trace"])))
    by = {e["tool"]: e["data"] for e in r["trace"] if e["type"] == "result"}
    gap = by["capacity_gap"]["shortfall"]
    assert by["read_volume"]["density"] == "busy" and gap > 0
    o = r["proposal"]
    assert len(o["borrowed"]) == gap                                  # açık kadar ödünç, fazlası değil
    assert o["idle_couriers"] == [] and not o["distributed_clusters"]
    assert len({x["courier"] for x in o["assignment"]}) == len(o["assignment"]) == by["capacity_gap"]["required_courier_day"]
    assert o["total"] == by["core_assignment"]["total"]           # öneri sayıları araçtan
    assert o["total"]["expected_fails"] < o["comparison"]["history_blind_expected_fails"]
    assert o["rationale"] and o["questions"] and r["status"] == "awaiting_approval" and r["degraded"] is False
    sim = {int(k): v for k, v in sv.run.assign_input("D", day)["chosen"].items()}
    assert {x["cluster"]: x["courier"] for x in o["assignment"]} == sim      # brifing/anlık görüntü ile tutarlı
    c = by["neighbor_candidates"]
    assert c["tie"] is False and len({x["plan_cost"] for x in c["candidates"]}) == len(c["candidates"])   # kim gitsin: eşitlik yok


def test_mock_trace_is_deterministic(sv, day, tmp_path):
    a = sv.orchestrator.plan(day)
    b = Services.create(mode="mock", memory_file=tmp_path / "m2.json").orchestrator.plan(day)
    assert json.dumps(a["trace"], sort_keys=True, ensure_ascii=False) == json.dumps(b["trace"], sort_keys=True, ensure_ascii=False)


def test_quiet_day_borrows_nobody(sv):
    quiet = next(d for d in sv.run.eval_days if not DayTools(sv.run, None, d).neighbors)
    r = sv.orchestrator.plan(quiet)
    assert "tool:neighbor_candidates" not in seq(r["trace"]) and r["proposal"]["borrowed"] == []


def test_tool_contracts(sv, day):
    ar = sv.orchestrator.tools(day)
    k = ar.capacity_gap({})
    assert set(k) >= {"required_courier_day", "local_available", "shortfall", "extra", "open_clusters", "neighbor_candidate_count", "shortfall_unclosed"}
    assert len(k["open_clusters"]) == k["shortfall"] and k["shortfall_unclosed"]["over_band_min"] > 0
    c = ar.neighbor_candidates({"need": 2, "exclude": [], "current_borrowed": []})
    assert len(c["proposed"]) == 2 and [x["order"] for x in c["candidates"]] == list(range(1, len(c["candidates"]) + 1))
    for x in c["candidates"]:
        assert 0 <= x["familiar_share"] <= 1 and 0 <= x["memory_coverage"] <= 1 and x["source_branch"]
    full = ar.core_assignment({"borrowed": c["proposed"], "exclude": [], "pin": []})
    short = ar.core_assignment({"borrowed": c["proposed"][:1], "exclude": [], "pin": []})
    assert not full["distributed_clusters"] and len(short["distributed_clusters"]) == 1
    assert short["total"]["over_band_min"] > full["total"]["over_band_min"]          # açık kapanmazsa fazla süre
    assert short["total"]["courier_count"] == full["total"]["courier_count"] - 1
    with pytest.raises(ValueError):
        ar.core_assignment({"borrowed": ["K01"], "exclude": [], "pin": []})        # yerel kurye ödünç olamaz
    with pytest.raises(ValueError):
        ar.evaluate_plan([], [{"cluster_id": 0, "courier_id": "K01"}, {"cluster_id": 1, "courier_id": "K01"}])
    r = ar.compute_route({"cluster_id": full["assignment"][0]["cluster"], "courier_id": full["assignment"][0]["courier"]})
    assert r["constraint_source"] == "memory" and r["comparison"]["memory"]["stop"] == r["stop"]   # hafıza kısıtı
    assert r["expected_min"] > 0 and r["estimated_return"] > r["start"]
    assert full["eta_model"]["history_route"] > 0


def test_route_constraint_hook(sv, day):
    """Rota aracının takılma noktası: kısıt kaynağı rota aracının çıktısına girer."""
    class One:
        name = "attempt"

        def constraints(self, d, addresses):
            return [RouteConstraint(address=int(addresses[0]), kind="closed_window", window=(720, 810), source="M1")]

    ar = DayTools(sv.run, sv.book, day, planner=RoutePlanner(sv.run, One()))
    k = ar.capacity_gap({})
    r = ar.compute_route({"cluster_id": ar.kid[0], "courier_id": ar.local[0]})
    assert r["constraint_source"] == "attempt" and r["constraints"][0]["kind"] == "closed_window" and k["required_courier_day"]


def test_whatif_gives_meaningful_difference(sv, day):
    o = sv.orchestrator.plan(day)["proposal"]
    who = o["borrowed"][0]["name"]
    q = sv.orchestrator.ask(day, f"{who} gelmezse ne olur?", o)
    assert len(q["alternatives"]) == 2 and q["new_proposal"] is not None
    none = next(a for a in q["alternatives"] if a["name"] == "Kimse gelmezse")
    assert none["diff"]["over_band_min"] > 0 and none["diff"]["courier_count"] == -1
    assert seq(q["trace"])[0] == "start" and seq(q["trace"])[-2:] == ["tool:respond", "response"]
    two = sv.orchestrator.ask(day, f"{o['borrowed'][0]['name']} ve {o['borrowed'][1]['name']} gelmezse?", o)   # iki isim (D7)
    assert all(o["borrowed"][i]["id"] in two["alternatives"][-1]["plan_change"]["exclude"] for i in (0, 1))


class ScriptLLM(LLM):
    def __init__(self, responses):
        super().__init__(mode="live")
        self.responses = list(responses)

    def _call(self, agent, req):
        return self.responses.pop(0)


def script_from_trace(events):
    """Mock izinden, aynı araçları aynı sırayla çağıran bir 'canlı' yanıt dizisi kurar."""
    out, texts, n = [], [], 0
    for e in events:
        if e["type"] == "decision":
            texts.append(e["text"])
        elif e["type"] == "tool":
            n += 1
            content = [{"type": "text", "text": t} for t in texts] + [{"type": "tool_use", "id": f"t{n}", "name": e["tool"], "input": e["input"]}]
            out.append({"stop_reason": "tool_use", "content": content})
            texts = []
    return out


def test_live_path_produces_same_trace_format(sv, day):
    mock = sv.orchestrator.plan(day)
    sv.orchestrator.llm = ScriptLLM(script_from_trace(mock["trace"]))
    live = sv.orchestrator.plan(day)
    assert live["degraded"] is False and live["mode"] == "live"
    strip = lambda evs: [{k: v for k, v in e.items() if k not in ("source", "mod")} for e in evs]  # noqa: E731
    assert strip(live["trace"]) == strip(mock["trace"])
    assert all(e["source"] == "llm" for e in live["trace"])


def test_replay_without_cassette_falls_back_with_trace(tmp_path, day):
    s = Services.create(mode="replay", memory_file=tmp_path / "m.json")
    s.orchestrator.llm.cassette_dir = tmp_path / "offline"
    r = s.orchestrator.plan(day)
    t = seq(r["trace"])
    assert r["degraded"] is True and t[1] == "fallback" and t[2:2 + len(PLAN_FLOW) - 1] == PLAN_FLOW[1:]
    assert r["proposal"]["borrowed"]


def test_human_approval(sv, day):
    dep = SessionStore(sv.orchestrator)
    k = dep.start(day, background=False)
    assert k.status == "awaiting_approval" and seq(k.trace.events)[-1] == "awaiting_approval" and k.trace.events[0]["type"] == "start"
    res = dep.decision(k.id, "approval")
    assert res["status"] == "finalized" and dep.plans[day]["assignment"] == k.result["proposal"]["assignment"]
    assert seq(k.trace.events)[-2:] == ["human_decision", "done"] and k.trace.events[-2]["source"] == "human"
    with pytest.raises(ValueError):
        dep.decision(k.id, "approval")                                   # ikinci karar yok

    k2 = dep.start(day, background=False)
    rows = k2.result["proposal"]["assignment"]
    edit = [{"cluster": r["cluster"], "courier": r["courier"]} for r in rows]
    edit[0]["courier"], edit[1]["courier"] = edit[1]["courier"], edit[0]["courier"]
    res = dep.decision(k2.id, "edit", edit, "iki kümeyi değiştirdim")
    assert res["status"] == "finalized" and res["changed_clusters"] == sorted([rows[0]["cluster"], rows[1]["cluster"]])
    assert "Müdür düzenledi" in res["plan"]["rationale"][-1]

    k3 = dep.start(day, background=False)
    with pytest.raises(ValueError):
        dep.decision(k3.id, "edit", [{"cluster": rows[0]["cluster"], "courier": "YOK"}])
    assert dep.decision(k3.id, "ret")["status"] == "rejected"


def test_trace_listener_streams_in_order():
    seen = []
    trace = Trace(seen.append)
    trace.emit("start", day=1)
    trace.emit("decision", text="x")
    assert [e["i"] for e in seen] == [0, 1] and trace.since(1)[0]["type"] == "decision"

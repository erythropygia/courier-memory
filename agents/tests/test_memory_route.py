"""Hafıza rotayı değiştirir (simülatörle aynı fonksiyon), brifing onaylı planı ve EtaModel'i okur, hasat ajanı."""
import pytest

from agents import Services
from agents.briefing import hint_today_valid
from agents.memory import parse_window
from agents.harvest import DAILY_MAX, PER_COURIER
from agents.orchestrator import SessionStore
from agents.tests.test_orchestrator import ScriptLLM, script_from_trace, seq


@pytest.fixture
def sv(tmp_path):
    return Services.create(mode="mock", memory_file=tmp_path / "mem.json")


@pytest.fixture
def day(sv):
    return sv.run.meta["critical"]["day"]


def test_route_tool_matches_simulator(sv, day):
    """Ajanın rota aracı, simülatör kol D'nin yürüttüğü hafızalı sırayı birebir üretir (aynı hafıza, aynı fonksiyon)."""
    sv.book.reset(day)
    ar = sv.orchestrator.tools(day)
    chosen = sv.run.assign_input("D", day)["chosen"]
    rows = [ar.compute_route({"cluster_id": k, "courier_id": chosen[str(k)]}) for k in ar.kid]
    assert all(r["same_as_sim"] for r in rows)
    assert sum(r["comparison"]["diff"]["carried"] + r["comparison"]["diff"]["deferred"] for r in rows) > 0
    for r in rows:
        k = r["comparison"]
        assert sorted(k["memory"]["order"]) == sorted(set(k["memoryless"]["order"]) - {c["address"] for c in r["changes"] if c["type"] == "deferred"})
        assert k["memory"]["window_matching"] <= k["memoryless"]["window_matching"]


def test_live_memory_moves_route(sv, day):
    """Kurye notu (öğle arası) hafızaya girince aynı aracın rotası değişir: durak pencere dışına taşınır."""
    sv.book.reset(day)
    snap = sv.run.snapshot("D", day)
    F = {k: i for i, k in enumerate(snap["stop_fields"])}
    ar = sv.orchestrator.tools(day)
    # taşıma yalnız rota süresini (öğle beklemesi dahil) artırmıyorsa yapılır; uygun ilk adayı ararız.
    # Aday: planlayıcının BEKLENEN varışı öğle arasının ortasına düşen, hafızasız durak (gerçekleşen varış plandan sapar).
    moved, tried = [], 0
    for r in snap["routes"]:
        if moved or tried >= 12:
            break
        before = ar.compute_route({"cluster_id": r["route"], "courier_id": r["courier"]})
        h = before["comparison"]["memory"]
        pick = [x for x, t in zip(h["order"][3:-3], h["expected_arrival"][3:-3]) if 735 <= t < 795 and not sv.book.for_address(x, day)]
        if not pick:
            continue
        a = pick[0]
        tried += 1
        res = sv.memory.process(day, r["courier"], "burası öğlen 12 ile 1.5 arası kapalı", address_id=a)
        assert res["status"] == "saved" and res["type"] == "lunch_break"
        after = ar.compute_route({"cluster_id": r["route"], "courier_id": r["courier"]})
        k = after["comparison"]["route_constraint"]
        assert k["after_min"] <= k["border_min"] + 0.01                       # taşınsa da taşınmasa da rota uzamaz
        moved = [c for c in after["changes"] if c["type"] == "window" and c["address"] == a]
        if moved:
            break
    assert moved and not after["same_as_sim"] and before["same_as_sim"]
    assert not (720 <= moved[0]["new_arrival"] < 810) and moved[0]["extra_min"] <= 0.05


def test_briefing_reads_approved_plan_eta_and_filters(sv, day):
    dep = SessionStore(sv.orchestrator)
    k = dep.start(day, background=False)
    assert k.status == "finalized"                                      # temassız: acil durum yok
    sv.briefing.plans = dep.plans
    hero = sv.run.meta["critical"]["courier"]
    b = sv.briefing.prepare(day, hero)
    row = next(x for x in dep.plans[day]["assignment"] if x["courier"] == hero)
    assert b["plan_source"] == "approved_plan" and b["expected_min"] == row["expected_min"]
    assert b["estimated_return"] in b["morning_briefing"]
    assert day % 6 != 5 and not any("umartesi" in kc["sentence"] for kc in b["door_sentences"])        # D1
    assert not hint_today_valid("saturday_closed", 2, 600) and hint_today_valid("saturday_closed", 5, 600)
    assert not hint_today_valid("lunch_break", 2, 600) and hint_today_valid("lunch_break", 2, 700)


def test_harvest_flow_and_answers(sv, day):
    r = sv.harvest.plan(day)
    t = seq(r["trace"])
    assert t[0] == "start" and t[-2:] == ["tool:harvest_plan", "done"] and "tool:memory_gaps" in t and "tool:save_questions" in t
    qs = r["questions"]
    assert 0 < len(qs) <= DAILY_MAX
    per = {}
    for q in qs:
        per[q["courier"]] = per.get(q["courier"], 0) + 1
    assert max(per.values()) <= PER_COURIER and len({q["address"] for q in qs}) == len(qs)
    assert all(sv.run.courier_kind(q["courier"]) != "borrowed" for q in qs if q["reason"] == "gap")
    hip = [q for q in qs if q["reason"] == "hypothesis"]
    for q in hip:                                                  # hipotez teyitsiz hafızaya yazılmaz
        assert not any(e["kind"] == q["hypothesis_type"] for e in sv.book.for_address(q["address"], day))
    n0 = len(sv.book.entries)
    out = [sv.harvest.simulate_answer(q["id"]) for q in qs[:8]]
    assert all(x["question"]["status"] == "answered" and x["question"]["simulate"] for x in out)
    written = [x for x in out if x["memory"]["status"] in ("saved", "updated")]
    assert written and len(sv.book.entries) > n0
    assert any(e.get("source") == "harvest" or "harvest" in (e.get("source_list") or []) for e in sv.book.entries)
    with pytest.raises(ValueError):
        sv.harvest.reply(qs[0]["id"], "repeat")


def test_harvest_live_path_same_trace(sv, day):
    mock = sv.harvest.plan(day)
    sv2 = Services.create(mode="mock", memory_file=sv.book.path.with_name("m2.json"))
    sv2.harvest.agent.llm = ScriptLLM(script_from_trace(mock["trace"]))
    live = sv2.harvest.plan(day)
    strip = lambda evs: [{k: v for k, v in e.items() if k not in ("source", "mod")} for e in evs]  # noqa: E731
    assert live["degraded"] is False and strip(live["trace"]) == strip(mock["trace"])
    assert [q["id"] for q in live["questions"]] == [q["id"] for q in mock["questions"]]


def test_parse_window():
    assert parse_window("öğlen 12 ile 1.5 arası kapalı") == [720, 810]
    assert parse_window("12:30-14:00 arası açılmıyor") == [750, 840]
    assert parse_window("zil bozuk") is None

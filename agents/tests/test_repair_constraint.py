"""Sert kısıt (rota uzamaz, bant aşılmaz, vardiya sonrasına kaydırma yok) yayımlanan çalıştırmada; kaydırılamayan bulgu
için ajan alternatifi (simülatörle aynı fonksiyon), Orkestratör izi ve demo örnekleri."""
import json

import pytest

from agents import Services
from agents.delivery_time import time_source
from agents.tests.test_orchestrator import seq


@pytest.fixture
def sv(tmp_path):
    s = Services.create(mode="mock", memory_file=tmp_path / "mem.json")
    time_source(s.run).reset()
    yield s
    time_source(s.run).reset()


def _routes(sv):
    for day in sv.run.eval_days:
        for r in sv.run.snapshot("D", day)["routes"]:
            if r.get("plan"):
                yield day, r


def test_repair_does_not_extend_route_or_exceed_band(sv):
    """Kol D'nin tüm rotaları: onarım (pencere + zaman) sonrası beklenen süre ≤ onarım öncesi + tolerans, km ≤ + km toleransı;
    bant içindeki rota bandı aşmaz, bant üstündeki rota uzamaz."""
    cfg = sv.run.meta["band"][1]
    n = 0
    for _, r in _routes(sv):
        L = r["plan"]["limits"]
        assert L is not None
        n += 1
        assert L["after_min"] <= L["before_min"] + L["tolerance_min"] + 0.01
        assert L["after_km"] <= L["before_km"] + L["tolerance_km"] + 0.001
        assert L["after_min"] <= (cfg if L["before_min"] <= cfg else L["before_min"]) + 0.01
    assert n == 408


def test_shifted_stop_within_shift(sv):
    se = 540 + sv.run.meta["band"][1]
    z = [c for _, r in _routes(sv) for c in r["plan"]["changes"] if c["type"] == "time"]
    assert z and all(c["new_arrival"] <= max(se, c["old_arrival"]) + 1 for c in z)


def test_counterfactual_overtime_and_expected_duration_do_not_increase(sv):
    """Aynı rota karşı-olgusu (zaman onarımı var ↔ yok): beklenen rota süresi artmaz (her çalıştırmada, sert); gerçekleşen fazla
    mesai demo + uzun dönem birlikte (80 gün) artmaz. Gerçekleşen yürütme plandan sapar (yabancı kurye, kuryenin kendi bildiği öğle
    arası): tek rotada artış olabilir, `overtime_route` bunu raporlar."""
    sums = [(sv.run.file("summary.json"), len(sv.run.eval_days))]
    ud = sv.run.dir / "long_term" / "summary.json"
    assert ud.exists()
    u = json.loads(ud.read_text(encoding="utf-8"))
    sums.append((u, u["time_analysis"]["day"]))
    tot = 0.0
    for s, n in sums:
        za = s["time_analysis"]
        assert za["constraint"]["violation"] == 0 and za["constraint"]["new_over_band"] == 0
        assert za["diff_daily"]["expected_duration_min"] <= za["constraint"]["tolerance_min"] + 0.05
        tot += za["diff_daily"]["overtime_min"] * n
    assert tot <= 0.0


def test_agent_alternatives_match_simulator(sv):
    """Kaydırılamayan bulgu alternatifleri: ajanın aracı (snapshot + teslim kaydı) = simülatörün kol D'de ürettiği (time.json)."""
    zj = sv.run.file("time.json")["alternatives"]
    ex = sv.run.meta.get("time_example_constraint")
    assert ex, "yayımlanmış çalıştırmada kısıt örneği yok"
    days = sorted({int(ex["day"])} | {int(d) for d in list(zj)[:2]})
    for day in days:
        sv.book.reset(day)
        ar = sv.orchestrator.tools(day)
        out = ar.time_alternatives({})
        sim = [(x["address"], x["option"], x.get("target")) for x in zj.get(str(day), [])]
        assert [(x["address"], x["option"], x.get("target")) for x in ar._zalt] == sim
        assert out["unshiftable"] == len(sim)
        assert all(x["text"] and x["sms"] and x["decision"] == "manager" for x in ar._zalt)


def test_unshiftable_finding_yields_alternative_in_trace(sv):
    """Mock kurallı yedek: delivery_time_analysis → apply_time_constraint → time_alternatives (aynı iz biçimi); öneride müdür kararı."""
    ex = sv.run.meta["time_example_constraint"]
    day = int(ex["day"])
    sv.book.reset(day)
    o = sv.orchestrator.plan(day)
    t = seq(o["trace"])
    i_u, i_alt = t.index("tool:apply_time_constraint"), t.index("tool:time_alternatives")
    assert i_u < i_alt and "result:time_alternatives" in t
    za = o["proposal"]["time_alternatives"]
    assert za and any(x["address"] == ex["address"] and x["option"] == ex["option"] for x in za)
    assert any("kısıt yüzünden" in r for r in o["proposal"]["risks"])
    assert any("uzatamaz" in e["text"] for e in o["trace"] if e["type"] == "decision")


def test_route_tool_shows_constraint_and_unshiftable(sv):
    ex = sv.run.meta["time_example_constraint"]
    day = int(ex["day"])
    sv.book.reset(day)
    ar = sv.orchestrator.tools(day)
    r = ar.compute_route({"cluster_id": int(ex["source"]), "courier_id": ex["courier"]})
    assert r["same_as_sim"]
    k = r["comparison"]["route_constraint"]
    assert k["after_min"] <= k["border_min"] + 0.01
    assert any(x["address"] == ex["address"] and x["reason"] == ex["reason"] for x in r["time_unshiftable"])


def test_demo_example_same_route_without_overtime(sv):
    """Yeni demo örneği: aynı rota içinde, rota süresi artmadan, rota fazla mesaiye girmeden, vardiya içinde; zamansızda alıcı yok,
    zaman-farkında teslim."""
    ex = sv.run.meta["time_example"]
    assert ex["result"]["no_time"]["result"] == "recipient_absent" and ex["result"]["memory"]["result"] == "delivery"
    ro = ex["route"]
    assert ro["overtime_min"]["memory"] == 0 and ro["limits"]["after_min"] <= ro["limits"]["before_min"] + 0.01
    assert ex["change"]["extra_min"] <= 0.05 and ex["result"]["memory"]["arrival"] <= ro["shift_end"]
    k = sv.run.meta["time_example_constraint"]
    assert k["option"] in ("transfer", "next_day", "evening_delivery_point") and k["text"] and k["sms_text"]
    if k["option"] == "transfer":
        assert k["extra_min_total"] <= 0.05 and k["target_duration_after"] <= sv.run.meta["band"][1]

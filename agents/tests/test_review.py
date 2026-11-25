"""Değerlendirme Ajanı (öz-iyileştirme), Bölge Ajanı ve gerçek gün servisi."""
import pytest

from agents import Services
from agents.region import RegionStats
from agents.real_day import RealDay
from agents.review import AUTO_MAX, PARAM_LIMITS


@pytest.fixture
def sv(tmp_path):
    s = Services.create(mode="mock", memory_file=tmp_path / "mem.json")
    s.book.reset(s.run.meta["critical"]["day"])
    return s


def test_morning_review_trend_actions_report(sv):
    day = sv.run.meta["critical"]["day"]
    r = sv.review.morning_review(day)
    eg = next(e for e in r["trace"] if e["type"] == "result" and e["tool"] == "trend")["data"]
    assert {x["measure"] for x in eg["measures"]} == {"first_attempt", "unfamiliar_fail", "hinted_fail", "duration_error_min"}
    assert all(x["direction"] in ("good", "bad", "stable") for x in eg["measures"])
    assert r["report"]["summary"] and [e["type"] for e in r["trace"]][-1] == "done"
    for name, (lo, hi) in PARAM_LIMITS.items():
        assert lo <= r["params"][name] <= hi
    event = sv.feed.items(agent="review")
    auto = [o for o in event if o["status"] == "applied"]
    assert len(auto) <= AUTO_MAX and any(o["type"] == "report" for o in event)
    assert all(o["type"] == "proposal" for o in event if o["status"] == "awaiting_approval")       # atama yalnız öneri


def test_guardrail_and_undo(sv):
    day = sv.run.meta["critical"]["day"]
    sv.review.morning_review(day)
    acted = [o for o in sv.feed.items(agent="review") if o["type"] in ("record_dropped", "flagged_for_confirmation")]
    if not acted:
        pytest.skip("bu veride şüpheli kayıt yok")
    o = acted[0]
    e = sv.book.get(o["record"])
    assert e.get("needs_confirmation") or e.get("status") == "dropped"
    sv.review.decision(o["n"], "undo", day)
    e = sv.book.get(o["record"])
    assert e["status"] == "active" and not e.get("needs_confirmation")
    with pytest.raises(ValueError):
        sv.review.decision(o["n"], "undo", day)                                     # ikinci kez geri alınamaz
    # aynı kayıt bir sonraki koşuda tekrar teyide alınabilir ama zaten teyitteyse ikinci kez alınmaz
    assert sv.book.flag_for_confirmation(o["record"], day, "attempt") and not sv.book.flag_for_confirmation(o["record"], day, "attempt")


def test_region_layers(sv):
    day = sv.run.meta["critical"]["day"]
    b = RegionStats(sv.run, sv.book, day)
    s = b.branch_layer()
    assert s["summary"]["block"] > 0 and s["manager_summary"] and all(x["level"] in ("low", "mid", "high") for x in s["blocks"])
    r = sv.run.snapshot("D", day)["routes"][0]
    F = {k: i for i, k in enumerate(sv.run.snapshot("D", day)["stop_fields"])}
    k = b.cluster_card([(x[F["lat"]], x[F["lng"]]) for x in r["stops"]], [bool(x[F["unfamiliar"]]) for x in r["stops"]], r["courier_name"],
                     [["park"]] + [[] for _ in r["stops"][1:]])
    assert k["courier_card"][0].startswith(f"Günaydın {r['courier_name']}") and k["summary"]["record_kinds"] == {"park": 1}


def test_real_day_memory_and_transfer(sv):
    g = RealDay(sv.run, sv.book)
    h = g.memory_summary()
    b = h["expected_fails"]
    assert h["stop"] > 0 and b["memory"] <= b["memoryless"] and 0 <= h["coverage_unfamiliar"]["share"] <= 1
    k = g.cluster(g.G["clusters"][0]["id"])
    assert k["stop"] == len(k["stops"]) and k["path"]["legs"] >= 1 and len(k["path"]["coords"]) >= 2
    a = g.transfer()
    assert a["after"]["courier"] == a["before"]["courier"] - 1 and a["changed"] > 0 and len(a["trace"]) == 5
    assert a["after"]["unfamiliar"] >= a["before"]["unfamiliar"] and "yaklaşık" in a["approximate"].lower()

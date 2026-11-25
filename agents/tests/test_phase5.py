"""Faz 5: şubede sabah. Ajan planı şubeden çıkış saatinden başlar (simülatörle aynı), Orkestratör ayrıştırma planını çıkarır
(indirme okutmasında raf; yükleme sırası rota tersi), öneride sabah özeti ve gerekçe satırı."""
import pytest

from agents import Services
from agents.orchestrator import DayTools
from agents.route import RoutePlanner, plan_departure, morning_info
from agents.rundata import RunData
from agents.delivery_time import time_source
from agents.tests.test_orchestrator import seq
from agents.tr import hhmm


@pytest.fixture
def sv(tmp_path):
    s = Services.create(mode="mock", memory_file=tmp_path / "mem.json")
    time_source(s.run).reset()
    yield s
    time_source(s.run).reset()


def _morning(run: RunData) -> dict:
    from agents.route import EtaModel
    return morning_info(EtaModel.load_cfg(run))


def test_plan_departure_matches_published_config():
    run = RunData()
    sb = _morning(run)
    assert sb["enabled"], "yayımlanan çalıştırmada sabah modeli açık olmalı (Faz 5)"
    p = RoutePlanner(run)
    assert p.rc["start"] == plan_departure(sb, "D") == sb["shift_start"] + sb["presorted_min"]
    assert RoutePlanner(run, arm="C").rc["start"] == sb["shift_start"] + sb["current_min"]
    assert p.shift_end() == sb["shift_end"]                    # vardiya bitişi saat olarak sabit (17:48)
    day = run.meta["critical"]["day"]
    r = next(x for x in run.snapshot("D", day)["routes"] if x.get("plan"))
    out = p.plan(day, int(r["route"]), r["courier"])
    assert out["start"] == hhmm(p.rc["start"])


def test_sorting_plan_shelf_and_load_order():
    run = RunData()
    day = run.meta["critical"]["day"]
    ar = DayTools(run, None, day)
    p = ar.sorting_plan({})
    snap = run.snapshot("D", day)
    F = {k: i for i, k in enumerate(snap["stop_fields"])}
    assert p["shelf_count"] == len(snap["routes"])
    assert p["shipment"] == sum(int(s[F["n"]]) for r in snap["routes"] for s in r["stops"])
    sb = _morning(run)
    assert p["departure"]["today"] == hhmm(sb["shift_start"] + sb["current_min"]) and p["departure"]["presorted"] == hhmm(sb["shift_start"] + sb["presorted_min"])
    r0 = sorted(snap["routes"], key=lambda q: int(q["route"]))[0]
    assert p["shelves"][0]["first_loaded"] == run.addr_label[int(r0["stops"][-1][F["address"]])]     # son durak önce yüklenir


def test_rule_flow_sorting_is_part_of_proposal(sv):
    day = sv.run.meta["critical"]["day"]
    sv.book.reset(day)
    o = sv.orchestrator.plan(day)
    t = seq(o["trace"])
    assert "tool:sorting_plan" in t and t.index("tool:sorting_plan") < t.index("tool:present_proposal")
    s = o["proposal"]["morning"]
    assert s and s["shelf_count"] > 0 and s["departure"]["presorted"] < s["departure"]["today"]
    assert any("Ayrıştırma indirme okutmasında" in g for g in o["proposal"]["rationale"])

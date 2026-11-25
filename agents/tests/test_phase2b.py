"""Faz 2b: teslim zamanı analizi ajan yolu (kayıtlardan, notsuz) → Orkestratör kararı → rota; hasat teyidi; sıra numarası düzeltmesi."""
import numpy as np
import pytest

from agents import Services
from agents.delivery_time import parse_confirmation, time_source
from agents.tests.test_orchestrator import seq


@pytest.fixture
def sv(tmp_path):
    s = Services.create(mode="mock", memory_file=tmp_path / "mem.json")
    time_source(s.run).reset()
    yield s
    time_source(s.run).reset()


@pytest.fixture
def ex(sv):
    e = sv.run.meta.get("time_example")
    assert e, "yayımlanmış çalıştırmada zaman örneği yok"
    return e


def _rows(sv, day):
    sv.book.reset(day)
    ar = sv.orchestrator.tools(day)
    chosen = sv.run.assign_input("D", day)["chosen"]
    return ar, [ar.compute_route({"cluster_id": k, "courier_id": chosen[str(k)]}) for k in ar.kid]


def test_agent_route_with_time_repair_matches_simulator(sv, ex):
    """Örnek gününde tüm rotalar: ajanın rota aracı (teslim kaydından aynı bulgular) = kol D'nin yürüttüğü sıra."""
    _, rows = _rows(sv, ex["day"])
    assert all(r["same_as_sim"] for r in rows)
    assert sum(r["comparison"]["diff"]["time_carried"] for r in rows) > 0
    z = [c for r in rows for c in r["changes"] if c["type"] == "time"]
    assert any(c["address"] == ex["address"] for c in z)
    assert all(c["new_p"] < c["old_p"] and "teslim kayıtları" in c["text"] for c in z)


@pytest.mark.slow
def test_all_days_408_routes_identical(sv):
    n = ok = zt = 0
    for day in sv.run.eval_days:
        _, rows = _rows(sv, day)
        n += len(rows)
        ok += sum(r["same_as_sim"] for r in rows)
        zt += sum(r["comparison"]["diff"]["time_carried"] for r in rows)
    assert ok == n and zt > 0


def test_change_order_numbers_correct(sv, ex):
    """Bilinen hata: metin '37. sıradan 35. sıraya' diyordu, gerçek 36→34. Artık sıralar 1 tabanlı ve doğru."""
    checked = 0
    for day in (ex["day"], sv.run.meta["critical"]["day"]):
        _, rows = _rows(sv, day)
        for r in rows:
            moves = [c for c in r["changes"] if c["type"] in ("window", "time")]
            for c in moves:
                assert f"({c['old_order']}. sıradan {c['new_order']}. sıraya" in c["text"]
            if len(moves) == 1 and not any(c["type"] == "deferred" for c in r["changes"]):
                c = moves[0]
                k = r["comparison"]
                assert k["memory"]["order"][c["new_order"] - 1] == c["address"]
                before = k["no_time"]["order"] if c["type"] == "time" else k["memoryless"]["order"]
                assert before[c["old_order"] - 1] == c["address"]
                checked += 1
    assert checked > 0


def test_no_future_leak_and_log_consistent_with_snapshot(sv, ex):
    zv = time_source(sv.run).data
    day = ex["day"]
    att, ab = zv.counts(day)
    assert int(att.sum()) == int((zv.day < day).sum())
    # Değerlendirme günü kaydı = o günün D anlık görüntüsündeki bulunabilirlik denemeleri
    d0 = sv.run.eval_days[3]
    snap = sv.run.snapshot("D", d0)
    F = {k: i for i, k in enumerate(snap["stop_fields"])}
    obs = sorted((int(s[F["address"]]), int(s[F["eta"]]), int(s[F["ok"]] == 0)) for r in snap["routes"] for s in r["stops"]
                 if s[F["deferred"]] == 0 and (s[F["ok"]] > 0 or s[F["reason"]] == "recipient_absent"))
    m = zv.day == d0
    assert obs == sorted(zip(zv.addr[m].tolist(), zv.minute[m].tolist(), zv.absent[m].tolist()))


def test_orchestrator_time_tools_in_trace_and_decision_changes_route(sv, ex):
    day = ex["day"]
    sv.book.reset(day)
    o = sv.orchestrator.plan(day)
    t = seq(o["trace"])
    i_a, i_u = t.index("tool:delivery_time_analysis"), t.index("tool:apply_time_constraint")
    assert i_a < i_u and t[-3:] == ["tool:present_proposal", "proposal", "awaiting_approval"]
    assert "tool:compute_route" not in t or i_u < t.index("tool:compute_route")      # riskli rota yoksa compute_route çağrılmaz
    zk = o["proposal"]["time_constraints"]
    assert zk["min_confidence"] == "mid" and zk["applied"] > 0
    # LLM bir bulguyu hariç tutarsa o durak taşınmaz ve rota simülasyondan ayrılır
    ar = sv.orchestrator.tools(day)
    before = ar.compute_route({"cluster_id": ex["cluster"], "courier_id": ex["courier"]})
    assert any(c["type"] == "time" and c["address"] == ex["address"] for c in before["changes"]) and before["same_as_sim"]
    r = ar.apply_time_constraint({"min_confidence": "mid", "exclude": [ex["address"]], "rationale": "attempt"})
    assert r["excluded"] == [ex["address"]]
    after = ar.compute_route({"cluster_id": ex["cluster"], "courier_id": ex["courier"]})
    assert not any(c["type"] == "time" and c["address"] == ex["address"] for c in after["changes"])
    assert all(z["address"] != ex["address"] for z in after["time_findings"])
    # Faz 2c: zaman hamlesi rotayı uzatamadığı için çoğu km'yi de kısaltan ters çevirmedir; aynı parça başka bir bulgu durağı için
    # yine seçilebilir. Sıra simülasyondan ayrılırsa ya da aynı kalırsa, ayrım bulgu listesinde ve değişiklik sahibindedir.


def test_harvest_hour_confirmation_question_answer_and_route(sv, ex):
    day = ex["day"]
    sv.book.reset(day)
    h = sv.harvest.plan(day)
    assert "tool:time_confirmations" in seq(h["trace"])
    zq = [q for q in h["questions"] if q["reason"] == "time"]
    assert zq and all("kimse bulunmuyor" in q["question"] and q["hypothesis_type"] is None for q in zq)
    profiles = sv.run.file("truth.json")["presence"]
    q = zq[0]
    res = sv.harvest.simulate_answer(q["id"])
    truth = profiles["profiles"][profiles["profile"][q["address"]]]
    assert res["memory"] is None and res["time"]["status"] == ("ret" if truth in ("home", "reception") else "confirmation")
    zk = time_source(sv.run)
    if res["time"]["status"] == "confirmation":
        assert q["address"] in zk.route(day, [q["address"]]) and zk.route(day, [q["address"]])[q["address"]]["confirmed"]
    else:
        assert q["address"] not in zk.route(day, [q["address"]])
    with pytest.raises(ValueError):
        sv.harvest.reply(q["id"], "yes")


def test_parse_confirmation():
    assert parse_confirmation("Evet, gündüz çalışıyorlar; akşam 5'ten sonra evdeler.") == (True, 17 * 60)
    assert parse_confirmation("Evet, öğlen dükkânı kapatıp çıkıyor; 2'den sonra uğra.") == (True, 14 * 60)
    assert parse_confirmation("Hayır, genelde evde biri oluyor.") == (False, None)
    assert parse_confirmation("bilmiyorum")[0] is None


def test_example_consistent(sv, ex):
    """Demo örneği: ≥ 6 geçmiş deneme, kötü dilimde kendi 'alıcı yok' kaydı, zamansızda alıcı yok, zaman-farkındada teslim."""
    assert len(ex["history"]) >= 6
    b = ex["finding"]
    assert b["not_found"][b["bad"]] >= 2 and b["level"] in ("mid", "high")
    assert ex["result"]["no_time"]["result"] == "recipient_absent" and ex["result"]["memory"]["result"] == "delivery"
    assert all(g["day"] < ex["day"] for g in ex["history"])
    za = sv.run.file("summary.json")["time_analysis"]
    tv = za["carried_stops"]
    assert tv["fails_memory"] < tv["fails_no_time"] and 0 < za["accuracy"] <= 1
    assert np.isfinite(za["diff_daily"]["recipient_absent"])

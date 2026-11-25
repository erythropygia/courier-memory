"""Teslim zamanı analizi (kayıtlardan, notsuz) ve zaman onarımı; saf fonksiyonlar + dünya profili."""
import numpy as np

from cm_sim.config import load_config
from cm_sim.routing_memory import StopRule, arrivals, plan_route
from cm_sim.delivery_time import (Params, address_finding, counts_from_log, slot, slots, proposal_text, fits_route,
                                  time_findings)
from cm_sim.world import build_world, p_absent


def _log(rows):
    """rows: (gün, adres, dakika, bulunamadı) → sütunlar."""
    d, a, m, x = zip(*rows)
    return list(d), list(a), list(m), list(x)


def _background(n_addr=40, days=30):
    """Aynı türde, çoğunlukla teslim edilen arka plan adresleri (tür önceli için)."""
    rows = []
    for a in range(1, n_addr):
        for d in range(0, days, 3):
            rows.append((d, a, 560 + (a * 37 + d * 53) % 600, int((a + d) % 41 == 0)))
    return rows


def test_slot_borders():
    assert [slot(m) for m in (540, 719, 720, 839, 840, 959, 960, 1079, 1080, 1300)] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert list(slots([600, 780, 1100])) == [0, 1, 4]


def test_owner_example_10_days_1300_never_delivered():
    """Sahibin örneği: 10 farklı gün hep 13:00'te kimse yok, 4 kez 16:30'da teslim → '16–18 öner', yüksek güven."""
    rows = _background() + [(2 * d, 0, 780, 1) for d in range(10)] + [(d, 0, 990, 0) for d in (21, 22, 24, 25)]
    att, ab = counts_from_log(40, *_log(rows), before_day=40)
    f = time_findings(att, ab, np.zeros(40, dtype=np.int64), 1, [0], 2, Params())
    b = f[0]
    assert b["type"] == "window" and b["bad"] == 1 and b["good"] == 3 and b["level"] == "high" and b["confidence"] > 0.99
    assert proposal_text(b) == "12–14: 0/10 teslim · 16–18: 4/4 teslim → 16–18 öner"
    assert fits_route(b, "mid") and fits_route(b, "high")


def test_no_future_leak():
    """Hedef gün ve sonrasının kaydı sayılmaz: gün 30 sonrası eklenen 'alıcı yok'lar gün 30 bulgusunu değiştirmez."""
    base = _background() + [(2 * d, 0, 780, 1) for d in range(3)] + [(10, 0, 990, 0), (12, 0, 1000, 0)]
    future = [(30 + d, 0, 990, 1) for d in range(6)]
    a1, b1 = counts_from_log(40, *_log(base), before_day=30)
    a2, b2 = counts_from_log(40, *_log(base + future), before_day=30)
    assert (a1 == a2).all() and (b1 == b2).all()
    a3, _ = counts_from_log(40, *_log(base + future), before_day=36)
    assert a3[0].sum() == a1[0].sum() + 6


def test_little_data_shrinks_and_prior_alone_is_not_enough():
    q, qbar = np.full(5, 0.02), 0.02
    P = Params()
    # tek deneme: bulgu yok
    assert address_finding([0, 1, 0, 0, 0], [0, 1, 0, 0, 0], q, qbar, P) is None
    # kötü dilimde 3 deneme ama yalnız 1 "alıcı yok" (kendi kanıtı < 2): bulgu yok
    assert address_finding([0, 3, 0, 2, 0], [0, 1, 0, 0, 0], q, qbar, P) is None
    # kötü saat belli, başka saatte kayıt yok: rotaya girmeyen 'teyit' bulgusu (hasat sorusu)
    b = address_finding([0, 3, 0, 0, 0], [0, 3, 0, 0, 0], q, qbar, P)
    assert b["type"] == "confirmation" and b["good"] is None and not fits_route(b, "low")


def _ring(n=40, r=0.6):
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.stack([r * np.cos(ang), r * np.sin(ang) + 1.0], axis=1)


def test_time_repair_shifts_stop_off_bad_hour_and_order_is_1_based():
    xy = _ring()
    n = len(xy)
    addrs = np.arange(100, 100 + n)
    svc = np.full(n, 11.0)
    kw = dict(road_factor=1.3, mpk=3.0, start=540.0, scale=1.0, margin=10.0)
    plain = plan_route(xy, np.zeros(2), addrs, svc, {}, **kw)
    t = arrivals(np.concatenate([[0], np.arange(1, n + 1), [0]]),
                 np.sqrt(((np.vstack([[0, 0], xy])[:, None] - np.vstack([[0, 0], xy])[None]) ** 2).sum(-1)) * 1.3,
                 np.concatenate([[0.0], svc]), 540.0, 3.0, 1.0)
    target = next(i for i in range(n) if 720 <= t[i + 1] < 840)          # 12–14'e düşen durak
    a = int(addrs[target])
    rules = {a: StopRule(presence=(0.9, 0.9, 0.9, 0.05, 0.05))}
    res = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=True, **kw)
    ch = [c for c in res["changes"] if c["type"] == "time"]
    assert ch and ch[0]["address"] == a and ch[0]["old_order"] == target + 1
    assert ch[-1]["new_p"] < ch[0]["old_p"]
    assert int(res["order"][ch[-1]["new_order"] - 1]) == a               # new_order 1 tabanlı durak sırası
    assert res["time_fail"]["after"] < res["time_fail"]["before"]
    assert list(plain["order"]) == list(addrs)                           # bulgu yoksa sıra değişmez
    off = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=False, **kw)
    assert list(off["order"]) == list(addrs)


def test_time_repair_does_not_violate_known_window():
    xy = _ring()
    n = len(xy)
    addrs = np.arange(n)
    svc = np.full(n, 11.0)
    kw = dict(road_factor=1.3, mpk=3.0, start=540.0, scale=1.0, margin=10.0)
    rules = {5: StopRule(presence=(0.9, 0.9, 0.9, 0.05, 0.05))}
    for a in range(n):
        if a != 5:
            rules.setdefault(a, StopRule()).windows.append((960.0, 1440.0))      # öğleden sonra hepsi kapalı
    res = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=True, **kw)
    pos = {int(v): i for i, v in enumerate(res["order"])}
    pts = np.vstack([[0, 0], xy[res["order"]]])
    D = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1)) * 1.3
    arr = arrivals(np.concatenate([[0], np.arange(1, n + 1), [0]]), D, np.concatenate([[0.0], svc[res["order"]]]), 540.0, 3.0, 1.0)
    base = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=False, **kw)
    pts0 = np.vstack([[0, 0], xy[base["order"]]])
    D0 = np.sqrt(((pts0[:, None] - pts0[None]) ** 2).sum(-1)) * 1.3
    arr0 = arrivals(np.concatenate([[0], np.arange(1, n + 1), [0]]), D0, np.concatenate([[0.0], svc[base["order"]]]), 540.0, 3.0, 1.0)
    bad = sum(1 for a in range(n) if a != 5 and arr[pos[a] + 1] >= 950)
    bad0 = sum(1 for i, a in enumerate(base["order"]) if a != 5 and arr0[i + 1] >= 950)
    assert bad <= bad0


def test_world_presence_profile_depends_on_hour():
    cfg = load_config()
    w = build_world(cfg)
    prof = np.array(w.addr_presence)
    cal = np.flatnonzero(prof == "worker")[:50]
    home = np.flatnonzero(prof == "home")[:50]
    shop = np.flatnonzero(prof == "shop")[:50]
    assert len(cal) and len(home) and len(shop)
    assert np.mean([p_absent(cfg, w, int(a), 2, 780) for a in cal]) > 0.5 > np.mean([p_absent(cfg, w, int(a), 2, 1050) for a in cal])
    assert np.mean([p_absent(cfg, w, int(a), 5, 780) for a in cal]) < 0.15            # Cumartesi evde
    assert max(p_absent(cfg, w, int(a), 2, m) for a in home for m in (600, 780, 1050)) < 0.02
    assert np.mean([p_absent(cfg, w, int(a), 2, 780) for a in shop]) > 10 * np.mean([p_absent(cfg, w, int(a), 2, 900) for a in shop])
    # Ayrı RNG akışı: profiller dünyanın geri kalanını değiştirmez
    off = build_world(cfg.model_copy(update={"presence": cfg.presence.model_copy(update={"enabled": False})}))
    assert (off.addr_xy == w.addr_xy).all() and [len(q) for q in off.quirks_by_addr] == [len(q) for q in w.quirks_by_addr]

"""Faz 2c: hafıza onarımlarının sert kısıtı (rota uzamaz, bant aşılmaz, vardiya sonrasına kaydırma yok; zaman hamlesi km de artırmaz) ve kaydırılamayan
bulgunun alternatifi (başka kuryeye aktarma → ertesi gün / akşam-teslim noktası + SMS). Saf fonksiyonlar."""
import numpy as np

from cm_sim.routing_memory import RepairLimits, StopRule, arrivals, plan_route, route_duration, time_alternatives
from cm_sim.delivery_time import alternative_text, slot, sms_text

KW = dict(road_factor=1.3, mpk=3.0, start=540.0, scale=1.0, margin=10.0)
LIM = RepairLimits(max_extra_min=0.0, max_extra_km=0.5, band_max=528.0, wait_max=15.0, blocked_diff=0.3)


def _rand_route(seed, n=40):
    rng = np.random.default_rng(seed)
    xy = rng.uniform(-3, 3, size=(n, 2)) + np.array([4.0, 0.0])
    # mesafe sırası (açgözlü en yakın komşu) = düz sıra
    left, cur, order = list(range(n)), np.zeros(2), []
    while left:
        j = min(left, key=lambda k: float(((xy[k] - cur) ** 2).sum()))
        order.append(j)
        left.remove(j)
        cur = xy[j]
    return xy[order], np.full(n, 9.0)


def _dur(res, xy, svc, rules=None, limits=LIM):
    addrs = list(range(len(xy)))
    pos = {a: i for i, a in enumerate(addrs)}
    o = [pos[int(a)] for a in res["order"]]
    pts = np.vstack([[0.0, 0.0], xy[o]])
    D = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1)) * KW["road_factor"]
    s = np.concatenate([[0.0], svc[o]])
    idx = np.concatenate([[0], np.arange(1, len(o) + 1), [0]])
    win = {}
    for i, a in enumerate(o, start=1):
        r = (rules or {}).get(a)
        if r is not None and r.windows:
            win[i] = [(lo - KW["margin"], hi + KW["margin"]) for lo, hi in r.windows]
    return route_duration(idx, D, s, win, KW["start"], KW["mpk"], KW["scale"], limits.wait_max)


def _presence_case(seed):
    """Rastgele rota + 12–14'e düşen bir durağa güçlü 'öğlen yok, 14–18 var' bulgusu."""
    xy, svc = _rand_route(seed)
    n = len(xy)
    pts = np.vstack([[0.0, 0.0], xy])
    D = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(-1)) * 1.3
    t = arrivals(np.concatenate([[0], np.arange(1, n + 1), [0]]), D, np.concatenate([[0.0], svc]), 540.0, 3.0, 1.0)
    i = next((k for k in range(n) if 720 <= t[k + 1] < 840), None)
    if i is None:
        return None
    return xy, svc, {i: StopRule(presence=(0.9, 0.9, 0.05, 0.05, 0.05))}


def test_repair_does_not_extend_route_unconstrained_would():
    """Kısıtsız (Faz 2b) zaman onarımı rotayı uzatabiliyordu; kısıtla beklenen süre onarım öncesini aşmaz, km +0,5'i aşmaz."""
    longer = 0
    for seed in range(40):
        c = _presence_case(seed)
        if c is None:
            continue
        xy, svc, rules = c
        addrs = np.arange(len(xy))
        free = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=True, **KW)
        lim = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=True, limits=LIM, **KW)
        base = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=False, **KW)
        d0, k0 = _dur(base, xy, svc)
        d1, k1 = _dur(lim, xy, svc)
        assert d1 <= d0 + 1e-6 and k1 <= k0 + 1e-6                          # zaman hamlesi km de artırmaz
        L = lim["limits"]
        assert L["after_min"] <= L["border_min"] + 0.01 and abs(L["before_min"] - d0) < 0.01
        assert sum(ch["extra_min"] for ch in lim["changes"]) <= 0.05            # tek hamle önceki kazancı kullanabilir; toplam artmaz
        longer += int(_dur(free, xy, svc)[0] > d0 + 1e-6)
    assert longer > 0, "test anlamlı olmalı: kısıtsız onarım en az bir rotayı uzatmalı"


def test_band_not_exceeded_and_no_worse_if_already_over():
    for seed in range(20):
        c = _presence_case(seed)
        if c is None:
            continue
        xy, svc, rules = c
        addrs = np.arange(len(xy))
        base = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=False, limits=LIM, **KW)
        d0 = base["limits"]["before_min"]
        # bant onarım öncesinin altında: süre hiç artamaz (tolerans 5 dk olsa bile)
        tight = RepairLimits(max_extra_min=5.0, max_extra_km=0.5, band_max=d0 - 30.0)
        r = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=True, limits=tight, **KW)
        assert r["limits"]["after_min"] <= d0 + 0.01 and r["limits"]["border_min"] == round(d0, 2)
        # bant onarım öncesinin hemen üstünde: tolerans 5 dk ama bant 1 dk → en çok bant
        near = RepairLimits(max_extra_min=5.0, max_extra_km=0.5, band_max=d0 + 1.0)
        r2 = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=True, limits=near, **KW)
        assert r2["limits"]["after_min"] <= d0 + 1.0 + 0.01


def test_shifted_stop_not_placed_after_shift_end():
    """Bulgu yalnız '18 sonrası' iyi derse ve rota oraya uzansa bile durak 17:48'den (09:00 + 528) sonraya taşınmaz."""
    xy, _ = _rand_route(3, n=60)
    svc = np.full(len(xy), 9.5)
    addrs = np.arange(len(xy))
    rules = {2: StopRule(presence=(0.9, 0.9, 0.9, 0.9, 0.02))}
    free = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=True, **KW)
    res = plan_route(xy, np.zeros(2), addrs, svc, rules, time_repair=True, limits=LIM, **KW)
    se = LIM.shift_end(540.0)
    assert all(c["new_arrival"] <= max(se, c["old_arrival"]) + 1 for c in res["changes"] if c["type"] == "time")
    assert any(c["new_arrival"] > se for c in free["changes"] if c["type"] == "time"), "kısıtsız onarım mesai sonrasına taşırdı"
    b = [x for x in res["time_blocked"] if x["address"] == 2]
    assert b and b[0]["reason"] in ("after_shift", "route_duration", "band", "no_good_hour")


def test_window_repair_also_constrained():
    """Faz 1–2 öğle penceresi onarımı da aynı kısıtla: taşıma eklediği sürüşü kaçırdığı beklemeden fazla yapamaz."""
    checked = 0
    for seed in range(30):
        xy, svc = _rand_route(seed)
        n = len(xy)
        rules = {a: StopRule(windows=[(720.0, 810.0)], kinds=["lunch_break"], sources=[f"M{a}"]) for a in range(0, n, 4)}
        addrs = np.arange(n)
        res = plan_route(xy, np.zeros(2), addrs, svc, rules, limits=LIM, **KW)
        L = res["limits"]
        d1, k1 = _dur(res, xy, svc, rules)
        assert abs(L["after_min"] - d1) < 0.01 and d1 <= L["before_min"] + 0.01 and k1 <= L["before_km"] + 0.5 + 0.001
        checked += int(any(c["type"] == "window" for c in res["changes"]))
    assert checked > 0


def test_service_correction_keeps_order():
    xy, svc = _rand_route(1)
    rules = {a: StopRule(extra=2.0, kinds=["safety"], sources=[f"M{a}"]) for a in range(0, len(xy), 3)}
    res = plan_route(xy, np.zeros(2), np.arange(len(xy)), svc, rules, limits=LIM, **KW)
    assert list(res["order"]) == list(range(len(xy))) and res["limits"]["after_min"] == res["limits"]["before_min"]


def _two_routes():
    """A: kısa sabah rotası, bulgu durağı (1, −1) ilk sırada (09:0x, öğlen yok). B: uzak kümeden dönerken 15:00 civarı (1, −1)'in
    yanından geçer."""
    xa = np.array([[1.0, -1.0], [2.0, 0.0], [3.0, 0.0]])
    sa = np.full(3, 10.0)
    ra = {0: StopRule(presence=(0.9, 0.9, 0.05, 0.05, 0.05))}
    A = plan_route(xa, np.zeros(2), np.array([10, 11, 12]), sa, {10: ra[0]}, time_repair=True, limits=LIM, **KW)
    xb = np.array([[5.0, 5.0], [5.3, 5.2], [5.6, 5.0], [5.2, 4.7], [4.8, 5.3], [5.5, 5.5], [5.1, 5.6], [4.9, 4.8],
                   [0.9, -1.0], [1.1, -1.0]])
    sb = np.full(len(xb), 40.0)
    sb[-2:] = 5.0
    Bres = plan_route(xb, np.zeros(2), np.arange(20, 20 + len(xb)), sb, {}, time_repair=True, limits=LIM, **KW)
    return A, Bres


def test_unshiftable_finding_yields_alternative_in_trace_transfer():
    A, Bres = _two_routes()
    assert A["time_blocked"] and A["time_blocked"][0]["address"] == 10 and A["time_blocked"][0]["reason"] == "no_good_hour"
    alts = time_alternatives({0: A, 1: Bres}, limits=LIM, **KW)
    assert len(alts) == 1
    x = alts[0]
    assert x["option"] == "transfer" and x["target"] == 1 and x["sms"] and x["decision"] == "manager"
    assert x["extra_min_total"] <= 1e-6 and x["extra_km_total"] <= 0.5 and x["target_duration_after"] <= 528
    assert 2 <= slot(x["target_arrival"]) <= 3 and x["target_p"] <= x["p_now"] - 0.3
    t = alternative_text(x, "Blok X", "Ali", "Elif", 1068)
    assert "aktar" in t and "Müdür" in t and "SMS" in t
    assert "09:00" <= sms_text(500)[24:29]


def test_no_transfer_if_target_route_over_band_next_day():
    A, Bres = _two_routes()
    assert 380 < Bres["limits"]["before_min"] < 420
    lim = RepairLimits(max_extra_min=0.0, max_extra_km=0.5, band_max=380.0)
    x = time_alternatives({0: A, 1: Bres}, limits=lim, **KW)[0]
    assert x["option"] == "next_day" and x["target"] is None             # B bandı aşıyor; 14–16 vardiya içinde (09:00 + 380 = 15:20)
    lim2 = RepairLimits(max_extra_min=0.0, max_extra_km=0.5, band_max=200.0)
    x2 = time_alternatives({0: A, 1: Bres}, limits=lim2, **KW)[0]
    assert x2["option"] == "evening_delivery_point"                       # uygun saat vardiya bitişinden (12:20) sonra

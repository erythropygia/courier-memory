import numpy as np

from cm_sim.engine import Simulation


def test_core_territory_keeps_couriers_in_their_area(small_cfg):
    """Çekirdek bölgeli plan: kurye çoğunlukla kendi bölgesinde (B'nin yabancı payının çok altında), aynı kurye sayısıyla."""
    res = Simulation(small_cfg(["days.eval=5"])).run()
    unf = {a: sum(d["unfamiliar_share"] for d in res.arms[a].daily) / len(res.arms[a].daily) for a in "BCD"}
    setup = {a: sum(d["couriers"] for d in res.arms[a].daily) for a in "BCD"}
    assert unf["C"] < unf["B"] / 3 and unf["D"] < unf["B"] / 3
    assert abs(setup["C"] - setup["B"]) <= len(res.eval_days)


def test_memory_changes_plan_not_copy_of_c(small_cfg):
    """D, C'nin rotasını kopyalamaz; hafıza planı ve sırayı değiştirir. Hafıza kapalıyken D'nin planı C'ninkiyle aynı."""
    res = Simulation(small_cfg(["days.eval=5"])).run()
    seq = lambda a, d: [tuple(r.stops.tolist()) for r in res.arms[a].routes[d]]  # noqa: E731
    assert any(seq("C", d) != seq("D", d) for d in res.eval_days)
    # pencere taşıması yalnız rotayı uzatmıyorsa yapılır; küçük dünyada hafıza planı erteleme/servis düzeltmesiyle de değişir
    changed = sum(len(r.extra.get("changes", [])) + len(r.extra.get("deferred", [])) + len(r.extra.get("extra_service", {}))
                  for d in res.eval_days for r in res.arms["D"].routes[d])
    assert changed > 0
    for d in res.eval_days:                                               # hafızalı sıra = düz sıranın permütasyonu (− ertelenen)
        for r in res.arms["D"].routes[d]:
            plain = set(r.extra["plain"].tolist())
            assert set(r.stops.tolist()) | set(r.extra["deferred_addrs"]) == plain

    off = Simulation(small_cfg(["days.eval=3", "routing.enabled=false", "memory.harvest_per_day=0",
                                "quirks.effects.safety.known_minutes=0"])).run()
    for d in off.eval_days[:1]:            # ilk değerlendirme günü: geçmişler henüz ayrışmadı → plan aynı
        assert [sorted(r.stops.tolist()) for r in off.arms["C"].routes[d]] == [sorted(r.stops.tolist()) for r in off.arms["D"].routes[d]]


def test_lunch_shortcut_fixed(small_cfg):
    """Bilinen öğle arası, pencere içinde gelinirse bedava değildir: bekleme/geri dönüş dakikası doğar."""
    res = Simulation(small_cfg(["days.eval=4"])).run()
    waits = sum(x["window_wait_minutes"] for a in "ACD" for x in res.arms[a].daily)
    hits = sum(x["window_hits"] for a in "ACD" for x in res.arms[a].daily)
    assert hits > 0 and waits > 0
    assert np.isfinite(waits)

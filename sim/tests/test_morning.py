"""Faz 5: şubede sabah akışı. Çıkış = mesai başı + sabah süresi (+ kurye sapması, kollar arası ortak); fazla mesai vardiya
bitişinden (saat) sayılır; kol D'nin aynı rotası bugünkü sabahla karşı-olgu olarak yürütülür. Sabah kapalıyken Faz 0–4 modeli."""
import numpy as np
import pytest

from cm_sim.config import load_config
from cm_sim.engine import Simulation, shift_end_at
from cm_sim.export import summarize
from cm_sim.routing_memory import RepairLimits

SMALL = ["world.addresses=1500", "couriers.senior=8", "couriers.reserve=1", "demand.shipments_per_day=600",
         "days.warmup=6", "days.eval=4"]


@pytest.fixture(scope="module")
def enabled():
    return Simulation(load_config(overrides=SMALL)).run()


@pytest.fixture(scope="module")
def closed():
    return Simulation(load_config(overrides=SMALL + ["morning.enabled=false"])).run()


def test_when_off_departure_is_shift_start_and_overtime_old_definition(closed):
    cfg = closed.cfg
    for a, st in closed.arms.items():
        for day, rr in st.results.items():
            assert all(r.start_minute == cfg.planning.start_minute for r in rr)
            row = next(x for x in st.daily if x["day"] == day)
            legacy = float(np.clip(np.array([r.minutes for r in rr]) - cfg.planning.band[1], 0, None).sum())
            assert row["overtime_minutes"] == pytest.approx(round(legacy, 1), abs=0.11)


def test_departure_by_arm_and_courier_deviation_shared_across_arms(enabled):
    cfg = enabled.cfg
    sb, m = cfg.morning, cfg.planning.start_minute
    for day in enabled.eval_days:
        A = {r.courier: r.start_minute for r in enabled.arms["A"].results[day]}
        D = {r.courier: r.start_minute for r in enabled.arms["D"].results[day]}
        common = set(A) & set(D)
        assert common
        for c in common:   # aynı gün aynı kurye: fark tam olarak sabah süreleri farkı (CRN sapması ortak)
            assert A[c] - D[c] == pytest.approx(sb.current_min - sb.presorted_min)
        assert all(abs(t - (m + sb.current_min)) <= 2 * sb.deviation_min + 1e-9 for t in A.values())
        assert all(abs(t - (m + sb.presorted_min)) <= 2 * sb.deviation_min + 1e-9 for t in D.values())


def test_overtime_from_shift_end(enabled):
    se = shift_end_at(enabled.cfg)
    for a in ("A", "D"):
        st = enabled.arms[a]
        for day, rr in st.results.items():
            row = next(x for x in st.daily if x["day"] == day)
            assert row["overtime_minutes"] == pytest.approx(round(sum(max(0.0, r.end_minute - se) for r in rr), 1), abs=0.11)


def test_counterfactual_same_route_only_departure_differs(enabled):
    sb = enabled.cfg.morning
    n = 0
    for day, rows in enabled.arms["D"].counterfactuals.items():
        for r in rows.values():
            h, b = r["memory"], r["current_morning"]
            assert b["stops"] == h["stops"] and b["km"] == pytest.approx(h["km"])
            assert b["start"] - h["start"] == pytest.approx(sb.current_min - sb.presorted_min, abs=0.11)
            n += 1
    assert n > 0
    s = summarize(enabled)["morning"]
    assert s["enabled"] and s["counterfactual"]["diff_daily"]["departure_mean"] == pytest.approx(-(sb.current_min - sb.presorted_min), abs=0.2)


def test_shift_end_fixed_as_clock_time():
    L = RepairLimits(band_max=528.0, shift_end_at=1068.0)
    assert L.shift_end(570.0) == 1068.0 and L.shift_end(630.0) == 1068.0
    assert RepairLimits(band_max=528.0).shift_end(570.0) == 1098.0           # Faz 2c davranışı (shift_end_at yok)

"""Uygulama verisinin kalibrasyon hedeflerine uyumu: python -m cm_sim.calibration [--set a.b=c]

Hedefler sim/config/calibration.yaml içindedir (saha verisinden türetilmiş toplu değerler).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

from .config import PKG_ROOT, load_config
from .demand import base_rates, demand_for_day
from .engine import Simulation
from .world import build_world

TARGETS = PKG_ROOT / "config" / "calibration.yaml"


def measure(cfg, days: int = 13) -> dict:
    w = build_world(cfg)
    rates = base_rates(cfg, w)
    seen: dict[int, set[int]] = defaultdict(set)
    stops_days = []
    ship = []
    for d in range(days):
        c = demand_for_day(cfg, w, d, rates)
        s = np.flatnonzero(c)
        stops_days.append(s)
        ship.append(int(c.sum()))
        for a in s:
            seen[int(a)].add(d)
    rep = {}
    for k in (1, 5, 12):
        n = r = 0
        for d in range(12, days):
            for a in stops_days[d]:
                n += 1
                r += any((d - j) in seen[int(a)] for j in range(1, k + 1))
        rep[k] = r / max(1, n)
    once = sum(1 for v in seen.values() if len(v) == 1) / max(1, len(seen))
    # Mevcut yapı (ısınma) ve dinamik plan (D) ölçüleri için kısa bir simülasyon
    sim_cfg = cfg.model_copy(deep=True)
    sim_cfg.days.eval = 5
    res = Simulation(sim_cfg).run()
    wd = res.arms["A"].daily
    dd = res.arms["D"].daily
    bd = res.arms["B"].daily
    att = sum(x["attempted"] for x in wd)
    return {
        "shipment_day": float(np.mean(ship)), "stop_day": float(np.mean([len(s) for s in stops_days])),
        "shipment_stop": float(np.mean(ship) / np.mean([len(s) for s in stops_days])),
        "courier_day": float(np.mean([x["couriers"] for x in wd])),
        "failure_rate": float(1 - sum(x["ok"] for x in wd) / max(1, att)),
        "repeat_1_g": rep[1], "repeat_5_g": rep[5], "repeat_12_g": rep[12], "one_time_address": once,
        "workload_deviation_fixed": float(np.mean([x["workload_cv"] for x in wd])),
        "workload_deviation_dynamic": float(np.mean([x["workload_cv"] for x in dd])),
        "dynamic_courier_diff": float(np.mean([x["couriers"] for x in bd]) / np.mean([x["couriers"] for x in wd]) - 1),
        "band_planned_fixed": float(np.mean([x["in_band_planned_share"] for x in wd])),
        "band_planned_dynamic": float(np.mean([x["in_band_planned_share"] for x in bd])),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cm_sim.calibration")
    ap.add_argument("--set", action="append", default=[], dest="overrides")
    ap.add_argument("--out", default=None, help="JSON çıktı yolu (ör. data/demo_run/calibration.json)")
    a = ap.parse_args(argv)
    cfg = load_config(overrides=a.overrides)
    tg = yaml.safe_load(TARGETS.read_text(encoding="utf-8"))
    m = measure(cfg)
    rows = []
    print(f"{'ölçü':26s} {'target':>8s} {'value':>9s}  durum")
    for k, t in tg["targets"].items():
        v = m[k]
        ok = abs(v - t["target"]) <= t["tolerance"] * abs(t["target"])
        rows.append({"measure": k, "explanation": t["explanation"], "target": t["target"], "value": round(v, 4), "compatible": ok})
        print(f"{k:26s} {t['target']:>8} {v:>9.3f}  {'✓' if ok else '✗'}")
    print(f"\nUyumlu: {sum(r['compatible'] for r in rows)}/{len(rows)}")
    if a.out:
        Path(a.out).write_text(json.dumps({"app_data": True, "source": tg["source"], "rows": rows}, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

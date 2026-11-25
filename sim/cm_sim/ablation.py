"""Hafızanın katkısını parçalarına ayırır (dürüstlük): demo senaryoları × seed, kol D'nin bileşenleri açılıp kapatılarak.

python -m cm_sim.ablation [--seeds 3] [--out runs/ablation]   → runs/ablation/ablation.json

Varyantlar (kol A, B, C her varyantta aynıdır; yalnız D değişir):
- `hint_only`: Faz 1'deki D (kapı ipucu; rota ve hasat yok) + düzeltilmiş öğle arası modeli
- `hint_harvest`: + proaktif hasat
- `hint_route`: + hafıza-farkında rota (planda erteleme, servis düzeltmesi, pencere onarımı)
- `full`: ipucu + hasat + rota (yayımlanan D)
- `no_time`: tam − teslim zamanı analizi (Faz 2b; rota zaman onarımı yok)
- `full_g60`, `no_time_g60`: aynı ikili, 60 günlük ısınma (teslim kaydı geçmişi daha derin; duyarlılık)
- Faz 2c: `full_tol5`, `no_time_tol5`: onarım süre toleransı +5 dk (duyarlılık; yayımlanan 0 dk);
  `unconstrained`, `no_time_unconstrained`: sert kısıt kapalı (Faz 2b davranışı; eski → yeni karşılaştırması)

`time_contribution`: aynı seed'de tam − zamansiz (kol D), 20 ve 60 günlük geçmişle (+ tol5, unconstrained_2_b). İki ayrı dünya
olduğu için fazla mesai/rota dakikası farkı gürültü içerir; sıkı ölçü `ayni_rota_*` sütunlarıdır (aynı rota karşı-olgusu, aynı
rastgele sayılar: zaman onarımı var ↔ yok) ve `kisit_*` (onarım öncesine göre en çok süre/km farkı, ihlal sayısı).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .config import load_config
from .engine import Simulation
from .export import summarize
from .run import DEMO_SCENARIOS

VARIANTS = {
    "hint_only": ["routing.enabled=false", "memory.harvest_per_day=0"],
    "hint_harvest": ["routing.enabled=false"],
    "hint_route": ["memory.harvest_per_day=0"],
    "full": [],
    "no_time": ["routing.time_aware=false"],
    "full_g60": ["days.warmup=60"],
    "no_time_g60": ["days.warmup=60", "routing.time_aware=false"],
    "full_tol5": ["routing.repair_max_extra_min=5"],
    "no_time_tol5": ["routing.repair_max_extra_min=5", "routing.time_aware=false"],
    "unconstrained": ["routing.repair_limits=false"],
    "no_time_unconstrained": ["routing.repair_limits=false", "routing.time_aware=false"],
    "full_morning": [],                                     # Faz 5: tam + kol D'de ayrıştırma okutmaya gömülü (sabah ~30 dk)
}
# Faz 5: hafıza varyantları sabahı tüm kollarda eşit tutar (bugünkü süreç); yalnız full_morning D'ye ayrıştırmasız sabahı verir.
EQUAL_MORNING = "morning.presorted_arms=[]"
SEPARATE_MORNING = {"full_morning"}
PAIRS = {"g20": ("full", "no_time"), "g60": ("full_g60", "no_time_g60"), "tol5": ("full_tol5", "no_time_tol5"),
         "unconstrained_2_b": ("unconstrained", "no_time_unconstrained"), "morning": ("full_morning", "full")}
PAIR_KEYS = ("D_far_pct", "recipient_absent_D", "revisit_D", "fail_D", "km_D", "overtime_D", "route_min_D", "same_route_recipient_absent",
             "same_route_revisit", "same_route_km", "same_route_min", "same_route_planned_min", "same_route_expected_min",
             "same_route_overtime_min", "departure_D", "return_D")


def _one(args: tuple[str, int]) -> dict:
    name, seed = args
    base = [] if name in SEPARATE_MORNING else [EQUAL_MORNING]
    cfg = load_config(scenarios=DEMO_SCENARIOS, overrides=base + VARIANTS[name] + [f"seed={seed}", "export.snapshots=false"])
    s = summarize(Simulation(cfg).run())
    A = s["arms"]
    far = {a: A[a]["first_attempt_rate"] for a in "ACD"}
    za = s.get("time_analysis") or {}
    zf, zk = za.get("diff_daily") or {}, za.get("constraint") or {}
    return {"variant": name, "seed": seed,
            "D_vs_C_pp": 100 * (far["D"] - far["C"]), "D_vs_A_pp": 100 * (far["D"] - far["A"]),
            "D_vs_C_preventable_pct": 100 * (A["D"]["preventable_fail"] / max(1, A["C"]["preventable_fail"]) - 1),
            "overtime_D_minus_C": A["D"]["overtime_minutes_per_day"] - A["C"]["overtime_minutes_per_day"],
            "km_D_minus_C": A["D"]["km_per_day"] - A["C"]["km_per_day"],
            "couriers_D_minus_C": A["D"]["couriers_per_day"] - A["C"]["couriers_per_day"],
            "window_hits_D": A["D"]["window_hits_per_day"], "wasted_D": A["D"]["wasted_trips_per_day"],
            "memory_coverage_D": A["D"]["memory_coverage"],
            "D_far_pct": 100 * far["D"], "recipient_absent_D": A["D"]["recipient_absent_per_day"], "revisit_D": A["D"]["revisit_stops_per_day"],
            "fail_D": A["D"]["fail"] / cfg.days.eval, "km_D": A["D"]["km_per_day"],
            "overtime_D": A["D"]["overtime_minutes_per_day"],
            "recipient_absent_D_minus_C": A["D"]["recipient_absent_per_day"] - A["C"]["recipient_absent_per_day"],
            "revisit_D_minus_C": A["D"]["revisit_stops_per_day"] - A["C"]["revisit_stops_per_day"],
            "route_min_D": A["D"]["route_minutes_per_day"],
            "departure_D": A["D"]["departure_mean"], "return_D": A["D"]["end_mean"],
            # aynı rota karşı-olgusu (zaman onarımı var − yok; kol D, gün başına); zamansız varyantta 0
            "same_route_recipient_absent": zf.get("recipient_absent", 0.0), "same_route_revisit": zf.get("revisit", 0.0), "same_route_km": zf.get("km", 0.0),
            "same_route_min": zf.get("minutes", 0.0), "same_route_planned_min": zf.get("planned_min", 0.0),
            "same_route_expected_min": zf.get("expected_duration_min", 0.0),
            "same_route_overtime_min": zf.get("overtime_min", 0.0),
            "constraint_violation": zk.get("violation", 0) or 0, "constraint_max_min": zk.get("max_duration_diff_min") or 0.0,
            "constraint_max_km": zk.get("max_km_diff") or 0.0,
            "unshiftable_day": (za.get("daily") or {}).get("unshiftable", 0.0),
            "transfer_day": (za.get("daily") or {}).get("transfer", 0.0)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cm_sim.ablation")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default="runs/ablation")
    a = ap.parse_args(argv)
    jobs = [(v, s) for v in VARIANTS for s in range(1, a.seeds + 1)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(_one, jobs))
    out = {"app_data": True, "scenarios": DEMO_SCENARIOS, "seeds": a.seeds, "variants": {}}
    for v in VARIANTS:
        rs = [r for r in rows if r["variant"] == v]
        out["variants"][v] = {k: {"mean": round(statistics.mean(r[k] for r in rs), 3), "min": round(min(r[k] for r in rs), 3),
                                    "max": round(max(r[k] for r in rs), 3)}
                                for k in rs[0] if k not in ("variant", "seed")}
        out["variants"][v]["setting"] = ([] if v in SEPARATE_MORNING else [EQUAL_MORNING]) + VARIANTS[v]
    out["time_contribution"] = {}
    for g, (on, off) in PAIRS.items():
        d = {k: [next(r[k] for r in rows if r["variant"] == on and r["seed"] == sd) -
                 next(r[k] for r in rows if r["variant"] == off and r["seed"] == sd) for sd in range(1, a.seeds + 1)]
             for k in PAIR_KEYS}
        out["time_contribution"][g] = {k: {"mean": round(statistics.mean(v), 3), "min": round(min(v), 3), "max": round(max(v), 3)}
                                   for k, v in d.items()}
        out["time_contribution"][g]["note"] = f"{on} − {off}, aynı seed (kol D, gün başına; D_far_pct puan)"
    p = Path(a.out)
    p.mkdir(parents=True, exist_ok=True)
    (p / "ablation.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    for v, x in out["variants"].items():
        print(f"{v:13s} D−C {x['D_vs_C_pp']['mean']:+.2f} puan [{x['D_vs_C_pp']['min']:+.2f}, {x['D_vs_C_pp']['max']:+.2f}] · "
              f"önlenebilir {x['D_vs_C_preventable_pct']['mean']:+.1f}% · fazla mesai {x['overtime_D_minus_C']['mean']:+.0f} dk/gün · "
              f"km {x['km_D_minus_C']['mean']:+.1f}")
    for g, x in out["time_contribution"].items():
        print(f"zaman katkısı {g}: alıcı yok {x['recipient_absent_D']['mean']:+.2f}/gün, tekrar ziyaret {x['revisit_D']['mean']:+.2f}, "
              f"km {x['km_D']['mean']:+.2f}, fazla mesai {x['overtime_D']['mean']:+.1f} dk, ilk denemede {x['D_far_pct']['mean']:+.3f} puan · "
              f"aynı rota: alıcı yok {x['same_route_recipient_absent']['mean']:+.2f}, fazla mesai {x['same_route_overtime_min']['mean']:+.1f} "
              f"[{x['same_route_overtime_min']['min']:+.1f}, {x['same_route_overtime_min']['max']:+.1f}] dk, planlanan "
              f"{x['same_route_planned_min']['mean']:+.1f} [max {x['same_route_planned_min']['max']:+.1f}] dk, beklenen süre "
              f"{x['same_route_expected_min']['mean']:+.1f} [max {x['same_route_expected_min']['max']:+.1f}] dk")
    print(f"{time.time() - t0:.0f} sn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Sağlamlık taraması: ana varsayımlar ızgarası × seed.

Manşet (Faz 2): anlamlı karşılaştırmalar. D − A (yeni yapı + hafıza ↔ bugün) ilk denemede teslim farkının aralığı ve
seed'ler arası yayılımı, kurye-gün farkı; D − C (hafızanın katkısı) aralığı. "D ≥ C ≥ B" sıralaması (B rastgele atama;
kendiliğinden doğru) yalnız geriye uyumluluk için tutulur, manşet değildir.

python -m cm_sim.sweep --grid sim/config/sweep.yaml --seeds 2 --workers 8 --out runs/
Arayüzdeki kaydırıcılar bu ızgaranın sonuçlarından okunur (canlı yeniden koşma yok).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

from .config import PKG_ROOT, load_config
from .engine import ARMS, Simulation
from .export import summarize
from .run import DEMO_SCENARIOS

DEFAULT_GRID = PKG_ROOT / "config" / "sweep.yaml"


def _one(args: tuple[list[str], list[str]]) -> dict:
    scenarios, overrides = args
    cfg = load_config(scenarios=scenarios, overrides=overrides)
    res = Simulation(cfg).run()
    s = summarize(res)
    return {"overrides": overrides, "arms": {a: {k: s["arms"][a][k] for k in (
        "first_attempt_rate", "preventable_fail", "couriers_per_day", "km_per_day", "in_band_share",
        "unfamiliar_share", "memory_coverage", "overtime_minutes_per_day")} for a in ARMS}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cm_sim.sweep")
    ap.add_argument("--grid", default=str(DEFAULT_GRID))
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default="runs")
    ap.add_argument("--normal", action="store_true", help="Demo senaryoları yerine normal senaryo")
    args = ap.parse_args(argv)
    grid = yaml.safe_load(Path(args.grid).read_text(encoding="utf-8"))
    params: dict[str, list] = grid["params"]
    fixed: list[str] = grid.get("fixed", [])
    scenarios = [] if args.normal else DEMO_SCENARIOS
    keys = list(params)
    combos = list(itertools.product(*[params[k] for k in keys]))
    jobs = []
    for combo in combos:
        for seed in range(1, args.seeds + 1):
            ov = fixed + [f"{k}={v}" for k, v in zip(keys, combo)] + [f"seed={seed}"]
            jobs.append((scenarios, ov))
    t0 = time.time()
    print(f"{len(combos)} kombinasyon × {args.seeds} seed = {len(jobs)} çalıştırma, {args.workers} işçi", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(_one, jobs, chunksize=1))
    rows = []
    ok_order = 0
    for ci, combo in enumerate(combos):
        rs = results[ci * args.seeds:(ci + 1) * args.seeds]
        mean = {a: {k: sum(r["arms"][a][k] for r in rs) / len(rs) for k in rs[0]["arms"][a]} for a in ARMS}
        far = {a: mean[a]["first_attempt_rate"] for a in ARMS}
        order_ok = far["D"] >= far["C"] >= far["B"]
        ok_order += order_ok
        per_seed = [100 * (r["arms"]["D"]["first_attempt_rate"] - r["arms"]["A"]["first_attempt_rate"]) for r in rs]
        rows.append({"params": dict(zip(keys, combo)), "arms": mean, "order_D_ge_C_ge_B": order_ok,
                     "pp": {"C_vs_B": round(100 * (far["C"] - far["B"]), 3), "D_vs_C": round(100 * (far["D"] - far["C"]), 3),
                            "D_vs_A": round(100 * (far["D"] - far["A"]), 3)},
                     "D_vs_A_seed_min": round(min(per_seed), 3), "D_vs_A_seed_max": round(max(per_seed), 3),
                     "courier_pct_D_vs_A": round(100 * (mean["D"]["couriers_per_day"] / mean["A"]["couriers_per_day"] - 1), 2),
                     "overtime_D_vs_A": round(mean["D"]["overtime_minutes_per_day"] - mean["A"]["overtime_minutes_per_day"], 1)})
    share = ok_order / len(combos)
    import statistics
    da = [r["pp"]["D_vs_A"] for r in rows]
    dc = [r["pp"]["D_vs_C"] for r in rows]
    kp = [r["courier_pct_D_vs_A"] for r in rows]
    headline = {
        "D_vs_A_pp": {"min": min(da), "max": max(da), "median": round(statistics.median(da), 3),
                      "share_ge_0": round(sum(x >= 0 for x in da) / len(da), 4),
                      "share_abs_le_0_15": round(sum(abs(x) <= 0.15 for x in da) / len(da), 4),
                      "seed_spread_mean": round(statistics.mean(r["D_vs_A_seed_max"] - r["D_vs_A_seed_min"] for r in rows), 3)},
        "D_vs_C_pp": {"min": min(dc), "max": max(dc), "median": round(statistics.median(dc), 3),
                      "share_gt_0": round(sum(x > 0 for x in dc) / len(dc), 4)},
        "courier_day_D_vs_A_pct": {"min": min(kp), "max": max(kp), "median": round(statistics.median(kp), 2)},
    }
    out = Path(args.out) / f"sweep_{'normal' if args.normal else 'demo'}_s{args.seeds}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "grid.json").write_text(json.dumps({"app_data": True, "keys": keys, "values": params, "seeds": args.seeds,
                                               "scenarios": scenarios, "rows": rows, "order_share": round(share, 4),
                                               "headline": headline}, ensure_ascii=False), encoding="utf-8")
    h = headline
    md = [f"# Sağlamlık taraması ({len(combos)} kombinasyon × {args.seeds} seed)", "",
          "> Uygulama verisi · 1 aylık geçmiş. Varsayımlar geniş aralıkta değiştirildi.", "",
          f"**Yeni yapı + hafıza (D), bugüne (A) göre ilk denemede teslim: {h['D_vs_A_pp']['min']:+.2f} … {h['D_vs_A_pp']['max']:+.2f} puan "
          f"(medyan {h['D_vs_A_pp']['median']:+.2f}; kombinasyonların %{100 * h['D_vs_A_pp']['share_abs_le_0_15']:.0f}'inde ±0,15 içinde, "
          f"%{100 * h['D_vs_A_pp']['share_ge_0']:.0f}'inde ≥ 0); kurye-gün {h['courier_day_D_vs_A_pct']['min']:+.1f} … "
          f"{h['courier_day_D_vs_A_pct']['max']:+.1f}%.**", "",
          f"**Hafızanın katkısı (D − C): {h['D_vs_C_pp']['min']:+.2f} … {h['D_vs_C_pp']['max']:+.2f} puan; kombinasyonların "
          f"%{100 * h['D_vs_C_pp']['share_gt_0']:.0f}'inde pozitif.** Seed'ler arası D − A yayılımı ortalama "
          f"{h['D_vs_A_pp']['seed_spread_mean']:.2f} puan.", "",
          f"(Önemsiz sıralama \"D ≥ C ≥ B\" %{100 * share:.0f}; B rastgele atama olduğu için manşet değil.)", "",
          "| " + " | ".join(keys) + " | C−B (puan) | D−C (puan) | D−A (puan) | sıra |", "|" + "---|" * (len(keys) + 4)]
    for r in rows:
        md.append("| " + " | ".join(str(r["params"][k]) for k in keys) +
                  f" | {r['pp']['C_vs_B']:+.2f} | {r['pp']['D_vs_C']:+.2f} | {r['pp']['D_vs_A']:+.2f} | {'✓' if r['order_D_ge_C_ge_B'] else '✗'} |")
    (out / "robustness.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Bitti: {out} ({time.time() - t0:.0f} sn) · D−A {h['D_vs_A_pp']['min']:+.2f}…{h['D_vs_A_pp']['max']:+.2f} puan · "
          f"D−C {h['D_vs_C_pp']['min']:+.2f}…{h['D_vs_C_pp']['max']:+.2f} puan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

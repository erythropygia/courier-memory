"""Hedef 1 ölçümü: yeni kuryenin öğrenme eğrisi, hafızalı (D) ↔ hafızasız (C), çok seed'li işe alım deneyi.

python -m cm_sim.learning [--seeds 8] [--workers 8] [--out runs/learning]   → runs/learning/learning.json

Senaryo `hiring`: değerlendirme günü 2'de dört kıdemli ayrılır, yerlerine dört yeni kurye başlar. Her seed'de aynı
dört kimlik (N01–N04) iki kolda da çalışır; kollar aynı rastgele sayıları kullanır. Ölçüler (yüzde değil adet ve dakika):

- **önlenebilir başarısız / 100 durak** (bilgiyle önlenebilir nedenler) ve **kapıda dk / durak**, kuryenin kaçıncı iş
  günü olduğuna göre (Cumartesi ya da yedekte kaldığı günler sayılmaz)
- iki karşılaştırma: (1) kol C ↔ kol D (iki ayrı dünya: hafıza yoksa kurye takıldıkça kendisi öğrenir),
  (2) aynı rota karşı-olgusu (kol D'nin rotası hafızasız yürütülseydi; kuryenin o günkü bilgisiyle)
- **ustalaşma günü:** 3 günlük hareketli ortalama, aynı koldaki kıdemli ortalamasının 1,1 katına indiği ilk gün
- **ilk hafta (6 iş günü):** kurye başına önlenebilir başarısız ve rota dakikası; ortalama ve %95 aralık (seed×kurye)
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from .config import load_config
from .engine import Simulation

SCENARIO = ["hiring"]
MASTERY_FACTOR = 1.1
FIRST_WEEK = 6


def _one(seed: int) -> dict:
    # Hedef 1 hafızayı ölçer; sabah tüm kollarda eşit (bugünkü süreç).
    cfg = load_config(scenarios=SCENARIO, overrides=[f"seed={seed}", "export.snapshots=false", "morning.presorted_arms=[]"])
    res = Simulation(cfg).run()
    start = {c.id: c.start_day for c in res.couriers if c.kind == "new"}
    out = {"seed": seed, "new": {}, "senior": {}}
    worked: dict[str, dict[str, dict[int, int]]] = {}       # kol → kurye → gün → kaçıncı iş günü
    for arm in ("C", "D"):
        wd = defaultdict(list)
        for r in res.arms[arm].courier_daily:
            if r["kind"] == "new":
                wd[r["courier"]].append(r["day"])
        worked[arm] = {c: {d: i + 1 for i, d in enumerate(sorted(ds))} for c, ds in wd.items()}
    for arm in ("C", "D"):
        per = defaultdict(dict)
        sen = defaultdict(lambda: [0.0, 0.0, 0.0])
        for r in res.arms[arm].courier_daily:
            if r["kind"] == "new":
                k = worked[arm][r["courier"]][r["day"]]
                per[r["courier"]][k] = {"p100": 100 * r["preventable_fail"] / max(1, r["stops"]),
                                        "door": r["door_minutes"] / max(1, r["stops"]), "min": r["minutes"],
                                        "prev": r["preventable_fail"], "stops": r["stops"]}
            elif r["kind"] == "senior":
                s = sen[r["day"]]
                s[0] += r["preventable_fail"]
                s[1] += r["stops"]
                s[2] += r["door_minutes"]
        out["new"][arm] = {c: dict(v) for c, v in per.items()}
        out["senior"][arm] = {"p100": 100 * sum(v[0] for v in sen.values()) / max(1, sum(v[1] for v in sen.values())),
                              "door": sum(v[2] for v in sen.values()) / max(1, sum(v[1] for v in sen.values()))}
    cf = defaultdict(dict)
    for day, routes in res.arms["D"].counterfactuals.items():
        for x in routes.values():
            if x["courier"] in start and "memory" in x:
                k = worked["D"][x["courier"]][day]
                h = x["memoryless"]
                cf[x["courier"]][k] = {"p100": 100 * h["preventable_fail"] / max(1, h["stops"]), "min": h["minutes"],
                                       "prev": h["preventable_fail"]}
    out["new"]["D_memoryless"] = {c: dict(v) for c, v in cf.items()}
    return out


def _ci(v: list[float]) -> tuple[float, float, float]:
    a = np.asarray(v, dtype=float)
    if len(a) == 0:
        return 0.0, 0.0, 0.0
    m = float(a.mean())
    h = 1.96 * float(a.std(ddof=1)) / np.sqrt(len(a)) if len(a) > 1 else 0.0
    return round(m, 2), round(float(m - h), 2), round(float(m + h), 2)


def aggregate(runs: list[dict]) -> dict:
    series = {}
    max_k = max(int(k) for r in runs for arm in r["new"].values() for v in arm.values() for k in v)
    for arm in ("C", "D", "D_memoryless"):
        pts = []
        for k in range(1, max_k + 1):
            vals = [r["new"][arm][c][k] for r in runs for c in r["new"][arm] if k in r["new"][arm][c]]
            if not vals:
                continue
            m, lo, hi = _ci([v["p100"] for v in vals])
            pts.append({"day": k, "preventable_100": m, "alt": lo, "top": hi, "n": len(vals),
                        "route_min": _ci([v["min"] for v in vals])[0],
                        "door_min_per_stop": _ci([v["door"] for v in vals])[0] if "door" in vals[0] else None})
        series[arm] = pts
    senior = {arm: round(float(np.mean([r["senior"][arm]["p100"] for r in runs])), 2) for arm in ("C", "D")}

    def mastery(pts: list[dict], ref: float) -> int | None:
        """Ortak eşik (bugünkü kıdemli düzeyi = kol C kıdemli ortalaması); örneklemin yarısından azına düşen günler sayılmaz."""
        n0 = max((p["n"] for p in pts), default=0)
        pts = [p for p in pts if p["n"] >= n0 / 2]
        y = [p["preventable_100"] for p in pts]
        for i in range(2, len(y)):
            if np.mean(y[i - 2:i + 1]) <= MASTERY_FACTOR * ref:
                return pts[i]["day"]
        return None

    week = {}
    for arm in ("C", "D", "D_memoryless"):
        prev, mins = [], []
        for r in runs:
            for c, v in r["new"][arm].items():
                ks = [k for k in v if k <= FIRST_WEEK]
                if len(ks) == FIRST_WEEK:
                    prev.append(sum(v[k]["prev"] for k in ks))
                    mins.append(sum(v[k]["min"] for k in ks))
        week[arm] = {"preventable_fails": _ci(prev), "route_min": _ci(mins), "n_courier": len(prev)}
    pair_prev, pair_min = [], []
    for r in runs:                                  # aynı kurye, aynı seed: C − D farkı (eşli)
        for c in r["new"]["C"]:
            vc, vd = r["new"]["C"][c], r["new"]["D"].get(c, {})
            ks = [k for k in range(1, FIRST_WEEK + 1) if k in vc and k in vd]
            if len(ks) == FIRST_WEEK:
                pair_prev.append(sum(vc[k]["prev"] - vd[k]["prev"] for k in ks))
                pair_min.append(sum(vc[k]["min"] - vd[k]["min"] for k in ks))
    return {"app_data": True, "scenario": SCENARIO, "seeds": [r["seed"] for r in runs],
            "measure": "Bilgiyle önlenebilir başarısız teslim / 100 durak; işteki güne göre; ortalama ve %95 aralık (kurye×seed).",
            "series": series, "senior_mean": senior,
            "mastery_day": {"C": mastery(series["C"], senior["C"]), "D": mastery(series["D"], senior["C"]),
                               "threshold": f"3 günlük ortalama ≤ {MASTERY_FACTOR} × bugünkü kıdemli düzeyi (kol C kıdemli ortalaması)"},
            "first_week": week,
            "first_week_paired_diff_C_minus_D": {"preventable_fails": _ci(pair_prev), "route_min": _ci(pair_min), "n": len(pair_prev)},
            "note": ("C ↔ D iki ayrı dünyadır: hafıza yoksa kurye takıldığı püf noktasını kendisi öğrenir. D_memoryless, D'nin rotası "
                    "hafızasız yürütülseydi (kuryenin o günkü bilgisiyle) sonucudur; hafızanın o günkü etkisini gösterir.")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cm_sim.learning")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default="runs/learning")
    ap.add_argument("--reaggregate", action="store_true", help="Koşmadan, kayıtlı ham sonuçlardan yeniden topla")
    a = ap.parse_args(argv)
    t0 = time.time()
    raw = Path(a.out) / "ham.json"
    if a.reaggregate and raw.exists():
        runs = [{**r, "new": {arm: {c: {int(k): v for k, v in d.items()} for c, d in cs.items()} for arm, cs in r["new"].items()}}
                for r in json.loads(raw.read_text(encoding="utf-8"))]
    else:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            runs = list(ex.map(_one, range(1, a.seeds + 1)))
    agg = aggregate(runs)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ham.json").write_text(json.dumps(runs), encoding="utf-8")       # yeniden toplamak için (--yeniden)
    (out / "learning.json").write_text(json.dumps(agg, ensure_ascii=False), encoding="utf-8")
    w, u = agg["first_week"], agg["mastery_day"]
    print(f"{len(runs)} seed, {time.time() - t0:.0f} sn · ustalaşma günü C {u['C']} / D {u['D']} · ilk hafta önlenebilir "
          f"C {w['C']['preventable_fails'][0]} / D {w['D']['preventable_fails'][0]} (eşli fark "
          f"{agg['first_week_paired_diff_C_minus_D']['preventable_fails']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

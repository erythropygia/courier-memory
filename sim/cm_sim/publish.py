"""Son demo çalıştırmasını data/demo_run/ olarak yayımlar (2. ve 3. parçanın hazır verisi). Uzun dönem
çalıştırması (long_term/), sağlamlık taraması (sweep.json), öğrenme deneyi (learning.json), ablasyon (ablation.json)
ve kalibrasyon raporu (calibration.json) eklenir.

python -m cm_sim.publish [--src runs/<id>] [--dst data/demo_run]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .run import DEMO_SCENARIOS

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cm_sim.publish")
    ap.add_argument("--src", default=None)
    ap.add_argument("--dst", default=str(ROOT / "data" / "demo_run"))
    ap.add_argument("--runs", default=str(ROOT / "runs"))
    ap.add_argument("--no-calibration", action="store_true")
    a = ap.parse_args(argv)
    if a.src:
        src = Path(a.src)
    else:
        prefix = "+".join(DEMO_SCENARIOS)
        cands = sorted((p for p in Path(a.runs).glob(f"{prefix}-*") if p.is_dir()), key=lambda p: p.stat().st_mtime)
        if not cands:
            print("Demo çalıştırması bulunamadı. Önce: python -m cm_sim.run --demo")
            return 1
        src = cands[-1]
    dst = Path(a.dst)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    sweeps = sorted(Path(a.runs).glob("sweep_demo_*"), key=lambda p: p.stat().st_mtime)
    if sweeps and (sweeps[-1] / "grid.json").exists():
        shutil.copy(sweeps[-1] / "grid.json", dst / "sweep.json")
    for sub, name in (("learning", "learning.json"), ("ablation", "ablation.json")):
        f = Path(a.runs) / sub / name
        if f.exists():
            shutil.copy(f, dst / name)
        else:
            print(f"Uyarı: {f} yok (python -m cm_sim.{sub})")
    longs = sorted((p for p in Path(a.runs).glob("long_term-*") if p.is_dir()), key=lambda p: p.stat().st_mtime)
    if longs:
        ld = dst / "long_term"
        ld.mkdir(exist_ok=True)
        for f in ("meta.json", "summary.json", "daily.json", "learning_curve.json", "recovery.json", "parse_stats.json",
                  "harvest.json", "report.md"):
            if (longs[-1] / f).exists():
                shutil.copy(longs[-1] / f, ld / f)
        print(f"Uzun dönem: {longs[-1].name}")
    if not a.no_calibration:
        from .calibration import main as calib
        calib(["--out", str(dst / "calibration.json")])
    print(f"Yayımlandı: {src} → {dst}")
    print("Ekonomi için: python -m agents.cost && python -m agents.economics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

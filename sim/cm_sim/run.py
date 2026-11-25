"""Komut satırı: python -m cm_sim.run [--config X] [--scenario a --scenario b] [--set a.b=c] [--out runs/]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .engine import Simulation
from .export import export_run

DEMO_SCENARIOS = ["leave_wave", "turnover", "borrowed_courier", "volume_shock"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cm_sim.run", description="Courier Memory simülatörü")
    ap.add_argument("--config", default=None, help="YAML yapılandırma (varsayılan: sim/config/default.yaml)")
    ap.add_argument("--scenario", action="append", default=[], help="Senaryo katmanı; birden fazla verilebilir")
    ap.add_argument("--demo", action="store_true", help="Demo senaryoları: " + ", ".join(DEMO_SCENARIOS))
    ap.add_argument("--set", action="append", default=[], dest="overrides", help="Ezme: a.b=c")
    ap.add_argument("--out", default="runs", help="Çıktı kök klasörü")
    ap.add_argument("--no-snapshots", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    scenarios = (DEMO_SCENARIOS if args.demo else []) + args.scenario
    try:
        cfg = load_config(args.config, scenarios=scenarios, overrides=args.overrides)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    say = (lambda m: None) if args.quiet else (lambda m: print(m, flush=True))
    res = Simulation(cfg).run(progress=say)
    out = export_run(res, Path(args.out), snapshots=False if args.no_snapshots else None)
    print(f"Çıktı: {out}")
    print((out / "report.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

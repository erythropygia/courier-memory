"""Çalıştırma klasörünü okur (docs/sozlesmeler.md §1). Ajanlar ve API yalnız bunu kullanır."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "data" / "demo_run"
QUIRK_KINDS = ("back_entry", "saturday_closed", "lunch_break", "safety", "bell", "position_wrong", "reception",
               "temporary_closed", "roadwork")
# yalnız bilgi taşıyan türler. Simülatörde karşılığı yok; plana ve rotaya girmez, durak kartında gösterilir.
INFO_KINDS = ("park", "building_access", "directions", "animal", "other_info")
MEMORY_KINDS = QUIRK_KINDS + INFO_KINDS
KIND_TR = {"senior": "kıdemli", "reserve": "yedek", "new": "yeni", "borrowed": "ödünç"}


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def parse_waybill(wb: str) -> tuple[int, int, int] | None:
    """SN + gün(2) + adres(5) + sıra(2). cm_sim.demand.parse_waybill ile aynı."""
    wb = (wb or "").strip().upper()
    if len(wb) != 11 or not wb.startswith("SN") or not wb[2:].isdigit():
        return None
    return int(wb[2:4]), int(wb[4:9]), int(wb[9:11])


class RunData:
    def __init__(self, run_dir: str | Path | None = None):
        self.dir = Path(run_dir or os.environ.get("CM_RUN_DIR") or DEFAULT_RUN)
        if not (self.dir / "meta.json").exists():
            raise FileNotFoundError(f"Çalıştırma klasörü bulunamadı: {self.dir}")
        self.meta = _load(self.dir / "meta.json")
        self.couriers = {c["id"]: c for c in _load(self.dir / "couriers.json")["couriers"]}
        addr = _load(self.dir / "addresses.json")
        rows = addr["addresses"]
        self.addr_ll = np.array([[r[1], r[2]] for r in rows], dtype=float)
        self.addr_kind = [r[3] for r in rows]
        self.addr_block = [r[4] for r in rows]
        self.addr_label = [r[5] for r in rows]
        lat0 = self.meta["center"][0]
        self._kx = 111.320 * np.cos(np.radians(lat0))
        self._ky = 110.574

    @property
    def run_id(self) -> str:
        return self.meta["run_id"]

    @property
    def eval_days(self) -> list[int]:
        return self.meta["eval_days"]

    def weekday_name(self, day: int) -> str:
        return self.meta["weekday_names"][day % 6]

    def file(self, rel: str):
        return _load(self.dir / rel)

    @lru_cache(maxsize=64)
    def snapshot(self, arm: str, day: int) -> dict:
        return _load(self.dir / "snapshots" / arm / f"{day}.json")

    @lru_cache(maxsize=64)
    def assign_input(self, arm: str, day: int) -> dict:
        return _load(self.dir / "assign" / arm / f"{day}.json")

    def memory_snapshot(self, day: int) -> list[dict]:
        p = self.dir / "memory" / f"{day}.json"
        return _load(p)["entries"] if p.exists() else []

    @lru_cache(maxsize=1)
    def notes(self) -> list[dict]:
        return _load(self.dir / "notes.json")["notes"]

    @lru_cache(maxsize=1)
    def notes_truth(self) -> dict[str, dict]:
        return {n["id"]: n for n in _load(self.dir / "notes_truth.json")["notes"]}

    def route_of(self, day: int, courier: str, arm: str = "D") -> dict | None:
        for r in self.snapshot(arm, day)["routes"]:
            if r["courier"] == courier:
                return r
        return None

    def address(self, a: int) -> dict:
        return {"id": int(a), "label": self.addr_label[a], "type": self.addr_kind[a],
                "lat": float(self.addr_ll[a, 0]), "lng": float(self.addr_ll[a, 1]), "block": int(self.addr_block[a])}

    def distances_m(self, lat: float, lng: float) -> np.ndarray:
        dx = (self.addr_ll[:, 1] - lng) * self._kx
        dy = (self.addr_ll[:, 0] - lat) * self._ky
        return np.sqrt(dx * dx + dy * dy) * 1000.0

    def nearest(self, lat: float, lng: float, radius_m: float = 80.0, limit: int = 8) -> list[tuple[int, float]]:
        d = self.distances_m(lat, lng)
        idx = np.argsort(d)[:limit]
        return [(int(i), float(d[i])) for i in idx if d[i] <= radius_m]

    def courier_name(self, cid: str) -> str:
        return self.couriers.get(cid, {}).get("name", cid)

    def courier_kind(self, cid: str) -> str:
        return self.couriers.get(cid, {}).get("kind", "?")

"""Kurye popülasyonu. Beceri, hız ve not bırakma eğilimi GİZLİ; tür, takvim ve ad gözlemlenebilir."""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field

import numpy as np

from .config import Config
from .rng import S_COURIERS, rng

NAMES = [
    "Mehmet", "Ali", "Ayşe", "Mustafa", "Hasan", "Elif", "İbrahim", "Murat", "Emre", "Zeynep",
    "Burak", "Serkan", "Derya", "Kemal", "Yusuf", "Ömer", "Fatih", "Seda", "Cem", "Eren",
    "Tolga", "Volkan", "Kaan", "Barış", "Selin", "Deniz", "Onur", "Gökhan", "Melis", "Arda",
]


@dataclass
class Courier:
    id: str
    name: str
    kind: str                         # senior | reserve | new | borrowed
    skill: float                      # GİZLİ: başarısızlık çarpanı (1 = ortalama, düşük = iyi)
    speed: float                      # GİZLİ: kapıda süre çarpanı
    note_propensity: float            # GİZLİ
    home_zone: int | None
    start_day: int = 0                # global gün (dahil)
    end_day: int | None = None        # global gün (hariç)
    leave_days: set[int] = field(default_factory=set)

    def available(self, day: int) -> bool:
        if day < self.start_day:
            return False
        if self.end_day is not None and day >= self.end_day:
            return False
        return day not in self.leave_days


def _draw(cfg: Config, cid: str) -> tuple[float, float, float]:
    c = cfg.couriers
    g = rng(cfg.seed, S_COURIERS, zlib.crc32(cid.encode()))
    skill = float(np.clip(math.exp(g.normal(-c.skill_sigma ** 2 / 2, c.skill_sigma)), *c.skill_clip))
    speed = float(np.clip(math.exp(g.normal(-c.speed_sigma ** 2 / 2, c.speed_sigma)), *c.speed_clip))
    a, b = c.note_propensity_beta
    prop = float(np.clip(g.beta(a, b) * c.note_propensity_scale, 0.0, 1.0))
    return skill, speed, prop


def build_couriers(cfg: Config) -> list[Courier]:
    warm = cfg.days.warmup
    out: list[Courier] = []
    name_i = 0

    def nm() -> str:
        nonlocal name_i
        n = NAMES[name_i % len(NAMES)] + ("" if name_i < len(NAMES) else f" {name_i // len(NAMES) + 1}")
        name_i += 1
        return n

    for i in range(cfg.couriers.senior):
        cid = f"K{i + 1:02d}"
        s, v, p = _draw(cfg, cid)
        out.append(Courier(cid, nm(), "senior", s, v, p, home_zone=i))
    for i in range(cfg.couriers.reserve):
        cid = f"Y{i + 1:02d}"
        s, v, p = _draw(cfg, cid)
        out.append(Courier(cid, nm(), "reserve", s, v, p, home_zone=None))
    for h in cfg.calendar.hires:
        s, v, p = _draw(cfg, h.id)
        out.append(Courier(h.id, nm(), "new", s, v, p, home_zone=None, start_day=warm + h.day))
    # Ödünç kurye birden çok dönem gelebilir (aynı kimlik birden çok satır): ilk–son dönem arası, aradaki günler müsait değil.
    stints: dict[str, list[tuple[int, int]]] = {}
    for b in cfg.calendar.borrowed:
        stints.setdefault(b.id, []).append((warm + b.from_, warm + b.to))
    for bid, ss in sorted(stints.items()):
        s, v, p = _draw(cfg, bid)
        lo, hi = min(a for a, _ in ss), max(b for _, b in ss)
        gaps = {d for d in range(lo, hi + 1) if not any(a <= d <= b for a, b in ss)}
        out.append(Courier(bid, nm(), "borrowed", s, v, p, home_zone=None, start_day=lo, end_day=hi + 1, leave_days=gaps))
    by_id = {c.id: c for c in out}
    for lv in cfg.calendar.leaves:
        if lv.courier not in by_id:
            raise ValueError(f"calendar.leaves: bilinmeyen kurye {lv.courier}")
        by_id[lv.courier].leave_days.update(range(warm + lv.from_, warm + lv.to + 1))
    for dp in cfg.calendar.departures:
        if dp.courier not in by_id:
            raise ValueError(f"calendar.departures: bilinmeyen kurye {dp.courier}")
        by_id[dp.courier].end_day = warm + dp.day
    return out

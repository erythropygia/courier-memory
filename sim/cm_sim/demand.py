"""Günlük talep: adres başına Poisson gönderi sayısı. Politikadan bağımsızdır; tüm kollar aynı talebi görür."""
from __future__ import annotations

import numpy as np

from .config import Config
from .rng import S_DEMAND, rng
from .world import World

N_WEEKDAYS = 6  # Pzt..Cmt
WEEKDAY_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt"]


def weekday(day: int) -> int:
    return day % N_WEEKDAYS


def base_rates(cfg: Config, world: World) -> np.ndarray:
    """Adres başına günlük beklenen gönderi. Düzenli adresler (1 − sporadic_share), seyrek adresler sporadic_share
    kadar gönderiyi paylaşır."""
    total = cfg.demand.shipments_per_day
    rec = world.addr_recurring
    r = np.array([cfg.demand.rate[k] for k in world.addr_kind], dtype=float) * world.addr_demand_w
    out = np.zeros(len(r))
    if rec.any():
        out[rec] = r[rec] / r[rec].sum() * total * (1 - cfg.demand.sporadic_share)
    if (~rec).any():
        out[~rec] = r[~rec] / r[~rec].sum() * total * cfg.demand.sporadic_share
    return out


def day_factor(cfg: Config, day: int) -> float:
    f = cfg.demand.weekday_factor[weekday(day)]
    for s in cfg.demand.shocks:
        if cfg.days.warmup + s.day == day:
            f *= s.factor
    return f


def demand_for_day(cfg: Config, world: World, day: int, rates: np.ndarray | None = None) -> np.ndarray:
    """(n_addresses,) gönderi sayıları."""
    lam = (rates if rates is not None else base_rates(cfg, world)) * day_factor(cfg, day)
    if weekday(day) == 5:
        workplace = np.array([k == "workplace" for k in world.addr_kind])
        lam = np.where(workplace, lam * cfg.demand.workplace_saturday_factor, lam)
    return rng(cfg.seed, day, S_DEMAND).poisson(lam).astype(np.int64)


def waybill(day: int, address: int, k: int) -> str:
    """Uygulamanın ürettiği barkod. Biçim sözleşmenin parçasıdır: SN + gün(2) + adres(5) + sıra(2)."""
    return f"SN{day:02d}{address:05d}{k:02d}"


def parse_waybill(wb: str) -> tuple[int, int, int] | None:
    if len(wb) != 11 or not wb.startswith("SN") or not wb[2:].isdigit():
        return None
    return int(wb[2:4]), int(wb[4:9]), int(wb[9:11])

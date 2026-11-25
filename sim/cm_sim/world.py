"""Coğrafya, bloklar, adresler ve gizli püf noktaları.

Gizli gerçek: Block.difficulty, Address.quirks ve adres bulunabilirlik profili (addr_presence, addr_presence_m). Bunlar yalnız sonuç modeli ve değerlendirme tarafından okunur.
Gözlemlenebilir: blok konumu/türü, adres konumu/türü/etiketi (şirket adresleri bilir, püf noktalarını bilmez).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .config import BLOCK_KINDS, TEMPORARY_KINDS, Config
from .rng import S_PRESENCE, S_QUIRKS, S_WORLD, rng

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LNG_EQ = 111.320
BLOCK_DIFFICULTY_FACTOR = {"rural": 1.5, "industrial": 1.2, "busy_residential": 1.0, "site": 0.8, "business_center": 0.9}


@dataclass
class Quirk:
    id: int
    address: int
    kind: str
    temporary: bool
    active_from: int                 # global gün (dahil)
    active_to: int | None            # global gün (dahil); None = süresiz
    change_day: int | None = None    # bu günden itibaren sürüm 2

    def active(self, day: int) -> bool:
        return self.active_from <= day and (self.active_to is None or day <= self.active_to)

    def version(self, day: int) -> int:
        return 2 if self.change_day is not None and day >= self.change_day else 1


@dataclass
class World:
    cfg_center: tuple[float, float]
    depot_xy: np.ndarray                     # (2,) km
    depot_latlng: tuple[float, float]
    n_rows: int
    n_cols: int
    block_xy: np.ndarray                     # (B, 2) blok merkezi km
    block_latlng: np.ndarray                 # (B, 2)
    block_kind: list[str]
    block_rc: np.ndarray                     # (B, 2) satır, sütun
    block_difficulty: np.ndarray             # GİZLİ
    addr_block: np.ndarray                   # (A,)
    addr_kind: list[str]
    addr_xy: np.ndarray                      # (A, 2) km
    addr_latlng: np.ndarray                  # (A, 2)
    addr_label: list[str]
    addr_recurring: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))   # düzenli adres mi
    addr_demand_w: np.ndarray = field(default_factory=lambda: np.zeros(0))                # adres talep ağırlığı
    quirks_by_addr: list[list[Quirk]] = field(default_factory=list)   # GİZLİ
    addr_presence: list[str] = field(default_factory=list)            # GİZLİ: bulunabilirlik profili (evde, calisan, ...)
    addr_presence_m: np.ndarray = field(default_factory=lambda: np.zeros(0))   # GİZLİ: adres düzeyi çarpan

    @property
    def n_addresses(self) -> int:
        return len(self.addr_kind)

    @property
    def n_blocks(self) -> int:
        return len(self.block_kind)

    def to_latlng(self, xy: np.ndarray) -> np.ndarray:
        return xy_to_latlng(xy, self.cfg_center)


def xy_to_latlng(xy: np.ndarray, center: tuple[float, float]) -> np.ndarray:
    lat0, lng0 = center
    xy = np.asarray(xy, dtype=float)
    lat = lat0 + xy[..., 1] / KM_PER_DEG_LAT
    lng = lng0 + xy[..., 0] / (KM_PER_DEG_LNG_EQ * math.cos(math.radians(lat0)))
    return np.stack([lat, lng], axis=-1)


def latlng_to_xy(latlng: np.ndarray, center: tuple[float, float]) -> np.ndarray:
    lat0, lng0 = center
    ll = np.asarray(latlng, dtype=float)
    y = (ll[..., 0] - lat0) * KM_PER_DEG_LAT
    x = (ll[..., 1] - lng0) * KM_PER_DEG_LNG_EQ * math.cos(math.radians(lat0))
    return np.stack([x, y], axis=-1)


def _smooth_field(g: np.random.Generator, n_rows: int, n_cols: int, coarse: int = 6) -> np.ndarray:
    """Düşük frekanslı gürültü: kaba ızgarada normal → çift doğrusal büyütme. Ortalama 0, std ≈ 1."""
    c = g.standard_normal((coarse + 1, coarse + 1))
    ys = np.linspace(0, coarse, n_rows)
    xs = np.linspace(0, coarse, n_cols)
    y0 = np.clip(np.floor(ys).astype(int), 0, coarse - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, coarse - 1)
    ty = (ys - y0)[:, None]
    tx = (xs - x0)[None, :]
    a = c[y0][:, x0]
    b = c[y0][:, x0 + 1]
    cc = c[y0 + 1][:, x0]
    d = c[y0 + 1][:, x0 + 1]
    f = a * (1 - ty) * (1 - tx) + b * (1 - ty) * tx + cc * ty * (1 - tx) + d * ty * tx
    return (f - f.mean()) / (f.std() + 1e-9)


def _assign_by_quantile(values: np.ndarray, mix: dict[str, float]) -> list[str]:
    """Pürüzsüz alana göre sıralayıp oranlara göre ardışık dilimler: türler yama halinde kümelenir."""
    kinds = list(mix.keys())
    p = np.array([mix[k] for k in kinds], dtype=float)
    p = p / p.sum()
    order = np.argsort(values, kind="stable")
    out = [""] * len(values)
    bounds = np.round(np.cumsum(p) * len(values)).astype(int)
    start = 0
    for k, end in zip(kinds, bounds):
        for i in order[start:end]:
            out[i] = k
        start = end
    for i in order[start:]:
        out[i] = kinds[-1]
    return out


def build_world(cfg: Config) -> World:
    wc = cfg.world
    g = rng(cfg.seed, S_WORLD)
    bm = wc.block_m / 1000.0
    n_cols = int(math.ceil(wc.width_km / bm))
    n_rows = int(math.ceil(wc.height_km / bm))
    x0, y0 = -n_cols * bm / 2, -n_rows * bm / 2

    rr, cc = np.meshgrid(np.arange(n_rows), np.arange(n_cols), indexing="ij")
    rc = np.stack([rr.ravel(), cc.ravel()], axis=1)
    bxy = np.stack([x0 + (rc[:, 1] + 0.5) * bm, y0 + (rc[:, 0] + 0.5) * bm], axis=1)

    ring_field = _smooth_field(g, n_rows, n_cols).ravel()
    kind_field = _smooth_field(g, n_rows, n_cols, coarse=10).ravel()
    d = np.sqrt((bxy[:, 0] / (wc.width_km / 2)) ** 2 + (bxy[:, 1] / (wc.height_km / 2)) ** 2)
    d = d + wc.ring_noise * ring_field
    ring = np.where(d < wc.ring_core, "core", np.where(d < wc.ring_mid, "mid", "outer"))

    block_kind = [""] * len(bxy)
    for name in ("core", "mid", "outer"):
        idx = np.where(ring == name)[0]
        if len(idx) == 0:
            continue
        kinds = _assign_by_quantile(kind_field[idx], wc.block_kind_mix[name])
        for i, k in zip(idx, kinds):
            block_kind[i] = k

    sig = wc.difficulty_sigma
    mu = math.log(wc.difficulty_mean) - sig * sig / 2
    difficulty = np.exp(g.normal(mu, sig, len(bxy))) * np.array([BLOCK_DIFFICULTY_FACTOR[k] for k in block_kind])

    # Adresler: blok ağırlığı × lognormal gürültü ile multinomial.
    w = np.array([wc.address_weight.get(k, 0.0) for k in block_kind]) * np.exp(g.normal(0, 0.4, len(bxy)))
    counts = g.multinomial(wc.addresses, w / w.sum())
    addr_block = np.repeat(np.arange(len(bxy)), counts)
    margin = 0.06 * bm
    off = g.uniform(-bm / 2 + margin, bm / 2 - margin, (len(addr_block), 2))
    axy = bxy[addr_block] + off
    addr_kind: list[str] = []
    labels: list[str] = []
    per_block_k = np.zeros(len(bxy), dtype=int)
    for a, b in enumerate(addr_block):
        mix = wc.address_kind_mix[block_kind[b]]
        ks = list(mix.keys())
        p = np.array([mix[k] for k in ks])
        addr_kind.append(ks[int(g.choice(len(ks), p=p / p.sum()))])
        per_block_k[b] += 1
        labels.append(f"Blok {rc[b, 0]:02d}-{rc[b, 1]:02d} No {per_block_k[b]}")

    # Düzenli adresler (toplu teslim noktaları ve adreslerin bir kısmı) gönderilerin çoğunu alır; kalanlar
    # seyrek, çoğu tek seferlik e-ticaret alıcısıdır. Tekrar oranları saha verisinden türetilen hedeflere kalibre edilir.
    kinds_arr = np.array(addr_kind)
    recurring = (kinds_arr == "collection_point") | (g.random(len(addr_kind)) < wc.recurring_share)
    rs = wc.recurring_sigma
    demand_w = np.where(recurring, np.exp(g.normal(-rs * rs / 2, rs, len(addr_kind))), 1.0)

    depot_xy = np.array(wc.depot_offset_km, dtype=float)
    world = World(
        cfg_center=tuple(wc.center),
        depot_xy=depot_xy,
        depot_latlng=tuple(xy_to_latlng(depot_xy, tuple(wc.center)).tolist()),
        n_rows=n_rows, n_cols=n_cols,
        block_xy=bxy, block_latlng=xy_to_latlng(bxy, tuple(wc.center)),
        block_kind=block_kind, block_rc=rc, block_difficulty=difficulty,
        addr_block=addr_block, addr_kind=addr_kind, addr_xy=axy,
        addr_latlng=xy_to_latlng(axy, tuple(wc.center)), addr_label=labels,
        addr_recurring=recurring, addr_demand_w=demand_w,
    )
    world.quirks_by_addr = build_quirks(cfg, world)
    world.addr_presence, world.addr_presence_m = build_presence(cfg, world)
    return world


def build_presence(cfg: Config, world: World) -> tuple[list[str], np.ndarray]:
    """Her adrese türüne göre bir bulunabilirlik profili ve lognormal çarpan (ortalama 1). Ayrı RNG akışı (S_PRESENCE)."""
    pc = cfg.presence
    n = world.n_addresses
    if not pc.enabled:
        return [""] * n, np.ones(n)
    g = rng(cfg.seed, S_PRESENCE)
    u = g.random(n)
    sig = pc.intensity_sigma
    m = np.exp(g.normal(-sig * sig / 2, sig, n)) if sig > 0 else np.ones(n)
    out: list[str] = []
    for a, ak in enumerate(world.addr_kind):
        mix = pc.mix[ak]
        ks = list(mix)
        cum = np.cumsum([mix[k] for k in ks]) / sum(mix.values())
        out.append(ks[min(int(np.searchsorted(cum, u[a], side="right")), len(ks) - 1)])
    return out, m


def p_absent(cfg: Config, world: World, a: int, weekday: int, minute: float) -> float:
    """Gizli gerçek: adres a'da bu saatte kapıda kimse olmaması olasılığı (durak düzeyi)."""
    pc = cfg.presence
    prof = pc.profiles[world.addr_presence[a]]
    arr = prof.saturday if weekday == 5 else prof.weekdays
    h = min(max(int(minute // 60) - pc.hours_start, 0), len(arr) - 1)
    return float(min(pc.intensity_max, arr[h] * world.addr_presence_m[a]))


def build_quirks(cfg: Config, world: World) -> list[list[Quirk]]:
    q = cfg.quirks
    g = rng(cfg.seed, S_QUIRKS)
    n_days = cfg.n_days
    warm = cfg.days.warmup
    out: list[list[Quirk]] = [[] for _ in range(world.n_addresses)]
    qid = 0
    for a, ak in enumerate(world.addr_kind):
        p = min(1.0, q.prevalence.get(ak, 0.0) * q.prevalence_scale)
        n_q = int(g.random() < p)
        if n_q and ak != "collection_point" and g.random() < 0.15:
            n_q = 2
        mix = q.kinds_by_address.get(ak)
        if not mix:
            continue
        ks = list(mix.keys())
        pk = np.array([mix[k] for k in ks])
        chosen: list[str] = []
        for _ in range(n_q):
            k = ks[int(g.choice(len(ks), p=pk / pk.sum()))]
            if k in chosen:
                continue
            chosen.append(k)
            change_day = None
            if g.random() < q.change_rate and n_days - warm > 2:
                change_day = int(g.integers(warm + 1, n_days))
            out[a].append(Quirk(id=qid, address=a, kind=k, temporary=False,
                                active_from=0, active_to=None, change_day=change_day))
            qid += 1
    # Süreli püf noktaları: değerlendirme döneminde başlar ve biter.
    n_tmp = int(round(q.temporary_rate * world.n_addresses))
    if n_tmp and cfg.days.eval > 3:
        addrs = g.choice(world.n_addresses, size=n_tmp, replace=False)
        tks = list(q.temporary_kinds.keys())
        tp = np.array([q.temporary_kinds[k] for k in tks])
        lo, hi = q.temporary_days
        for a in sorted(int(x) for x in addrs):
            k = tks[int(g.choice(len(tks), p=tp / tp.sum()))]
            start = int(g.integers(warm, max(warm + 1, n_days - 3)))
            dur = int(g.integers(lo, hi + 1))
            out[a].append(Quirk(id=qid, address=a, kind=k, temporary=True,
                                active_from=start, active_to=start + dur - 1))
            qid += 1
    assert all(k.kind not in TEMPORARY_KINDS or k.temporary for qs in out for k in qs)
    return out


def block_kinds_summary(world: World) -> dict[str, int]:
    return {k: sum(1 for x in world.block_kind if x == k) for k in BLOCK_KINDS}

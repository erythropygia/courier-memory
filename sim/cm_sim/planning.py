"""Planlama: dinamik planlama motoru benzeri (dengeli kümeleme + rota) ve sabit bölgeler.

Planlama kuryeden bağımsızdır: kümeler/bölgeler önce üretilir, kurye ataması ayrı adımdır.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .config import Config
from .couriers import Courier
from .world import World


@dataclass
class Route:
    id: int                               # küme ya da bölge kimliği
    stops: np.ndarray                     # adres kimlikleri, ziyaret sırasında
    km: float
    planned_minutes: float
    zone: int | None = None
    courier: str | None = None
    covered_by: str | None = None         # sabit bölgede bölge sahibi yerine giden kurye türü (ör. "reserve")
    extra: dict = field(default_factory=dict)


def service_minutes(cfg: Config, n: np.ndarray | int) -> np.ndarray | float:
    return cfg.outcome.service_per_stop + cfg.outcome.service_per_shipment * n


def dist_matrix(cfg: Config, pts: np.ndarray) -> np.ndarray:
    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
    return d * cfg.planning.road_factor


def _nearest_neighbor(D: np.ndarray) -> list[int]:
    n = D.shape[0]
    visited = np.zeros(n, dtype=bool)
    visited[0] = True
    order = [0]
    cur = 0
    for _ in range(n - 1):
        row = np.where(visited, np.inf, D[cur])
        nxt = int(np.argmin(row))
        order.append(nxt)
        visited[nxt] = True
        cur = nxt
    return order


def _two_opt(route: np.ndarray, D: np.ndarray, passes: int) -> np.ndarray:
    """route: depo(0) ile başlayıp biten düğüm dizisi. Vektörize 2-opt."""
    r = route.copy()
    for _ in range(passes):
        improved = False
        for i in range(1, len(r) - 2):
            a, b = r[i - 1], r[i]
            js = np.arange(i + 1, len(r) - 1)
            c, d = r[js], r[js + 1]
            delta = D[a, c] + D[b, d] - D[a, b] - D[c, d]
            j = int(np.argmin(delta))
            if delta[j] < -1e-9:
                jj = js[j]
                r[i:jj + 1] = r[i:jj + 1][::-1]
                improved = True
        if not improved:
            break
    return r


def order_route(cfg: Config, world: World, addrs: np.ndarray) -> tuple[np.ndarray, float]:
    """Adresleri depodan başlayıp depoda biten bir tura dizer. (sıralı adresler, km) döner."""
    if len(addrs) == 0:
        return addrs, 0.0
    pts = np.vstack([world.depot_xy[None, :], world.addr_xy[addrs]])
    D = dist_matrix(cfg, pts)
    nn = _nearest_neighbor(D) + [0]
    r = _two_opt(np.array(nn), D, cfg.planning.two_opt_passes)
    km = float(D[r[:-1], r[1:]].sum())
    return addrs[r[1:-1] - 1], km


def make_route(cfg: Config, world: World, rid: int, addrs: np.ndarray, counts: np.ndarray, zone: int | None = None,
               extra: dict[int, float] | None = None) -> Route:
    """extra: adres → ek servis dk (hafıza-farkında planın kaba bant denetimi için; sıra değişmez)."""
    ordered, km = order_route(cfg, world, np.asarray(addrs, dtype=np.int64))
    svc = float(np.sum(service_minutes(cfg, counts[ordered]))) if len(ordered) else 0.0
    if extra:
        svc += float(sum(extra.get(int(a), 0.0) for a in ordered))
    return Route(id=rid, stops=ordered, km=km, planned_minutes=svc + km * cfg.planning.minutes_per_km, zone=zone)


def balanced_kmeans(xy: np.ndarray, w: np.ndarray, k: int, iters: int, g: np.random.Generator, slack: float = 1.04) -> np.ndarray:
    n = len(xy)
    if k <= 1:
        return np.zeros(n, dtype=np.int64)
    if k >= n:
        return np.arange(n, dtype=np.int64) % k
    centers = [xy[int(g.integers(n))]]
    d2 = ((xy - centers[0]) ** 2).sum(1)
    for _ in range(1, k):
        p = d2 / d2.sum() if d2.sum() > 0 else np.full(n, 1 / n)
        c = xy[int(g.choice(n, p=p))]
        centers.append(c)
        d2 = np.minimum(d2, ((xy - c) ** 2).sum(1))
    C = np.array(centers)
    cap = w.sum() / k * slack
    labels = np.zeros(n, dtype=np.int64)
    for _ in range(iters):
        D = np.sqrt(((xy[:, None, :] - C[None, :, :]) ** 2).sum(-1))
        srt = np.sort(D, axis=1)
        regret = srt[:, 1] - srt[:, 0]
        order = np.argsort(-regret, kind="stable")
        pref = np.argsort(D, axis=1, kind="stable")
        load = np.zeros(k)
        for i in order:
            chosen = -1
            for c in pref[i]:
                if load[c] + w[i] <= cap:
                    chosen = int(c)
                    break
            if chosen < 0:
                chosen = int(np.argmin(load))
            labels[i] = chosen
            load[chosen] += w[i]
        for c in range(k):
            m = labels == c
            if m.any():
                C[c] = (xy[m] * w[m, None]).sum(0) / w[m].sum()
    return labels


def _stop_weight(cfg: Config, counts: np.ndarray) -> np.ndarray:
    return service_minutes(cfg, counts).astype(float) + cfg.planning.travel_per_stop_estimate


def n_clusters(cfg: Config, stops: np.ndarray, counts: np.ndarray, n_available: int) -> int:
    w = _stop_weight(cfg, counts[stops])
    k = int(math.ceil(w.sum() / cfg.planning.target_minutes))
    return max(1, min(k, n_available, len(stops)))


def plan_dynamic(cfg: Config, world: World, stops: np.ndarray, counts: np.ndarray, n_available: int,
                 g: np.random.Generator) -> list[Route]:
    """Günün duraklarını dengeli kümelere böler ve rotalar. Küme sayısı ≤ müsait kurye."""
    if len(stops) == 0 or n_available == 0:
        return []
    w = _stop_weight(cfg, counts[stops])
    k = int(math.ceil(w.sum() / cfg.planning.target_minutes))
    k = max(1, min(k, n_available, len(stops)))
    routes: list[Route] = []
    for _attempt in range(3):
        labels = balanced_kmeans(world.addr_xy[stops], w, k, cfg.planning.kmeans_iters, g, slack=cfg.planning.dynamic_slack)
        routes = [make_route(cfg, world, c, stops[labels == c], counts) for c in range(k) if (labels == c).any()]
        if max(r.planned_minutes for r in routes) <= cfg.planning.band[1] or k >= min(n_available, len(stops)):
            break
        k += 1
    for i, r in enumerate(routes):
        r.id = i
    return routes


def fixed_zones(cfg: Config, world: World, rates: np.ndarray, g: np.random.Generator) -> np.ndarray:
    """Beklenen talep ağırlığıyla sabit bölgeler; her adresin bölgesi (n_addresses,)."""
    p_stop = 1 - np.exp(-rates)
    w = p_stop * (cfg.outcome.service_per_stop + cfg.planning.travel_per_stop_estimate) + rates * cfg.outcome.service_per_shipment
    # Sahadaki bölgeler mahalle/alan sınırlarıyla çizilmiştir; güncel talebe tam oturmaz. Üs < 1 → bölgeler talepten çok alana göre.
    w = (w + 1e-6) ** cfg.planning.fixed_zone_weight_exp
    # Bölgeler yıllar önceki talebe göre çizildi; o zamandan beri talep bölgeler arasında kaydı (lognormal kayma, blok düzeyinde).
    drift = cfg.planning.fixed_zone_demand_drift
    if drift > 0:
        bd = np.exp(np.random.default_rng([cfg.seed, 97]).normal(-drift * drift / 2, drift, world.n_blocks))
        w = w * bd[world.addr_block]
    return balanced_kmeans(world.addr_xy, w, cfg.couriers.senior, cfg.planning.kmeans_iters + 4, g,
                           slack=cfg.planning.fixed_zone_slack)


def zone_centroids(world: World, zone_of: np.ndarray, n_zones: int) -> np.ndarray:
    return np.array([world.addr_xy[zone_of == z].mean(0) if (zone_of == z).any() else world.depot_xy for z in range(n_zones)])


def plan_fixed(cfg: Config, world: World, stops: np.ndarray, counts: np.ndarray, zone_of: np.ndarray,
               zone_owner: dict[int, str], couriers: dict[str, Courier], day: int,
               centroids: np.ndarray) -> list[Route]:
    """Sabit bölge planı. Sahibi gelmeyen bölge: yedek/yeni/ödünç kurye ya da komşu bölgelere bölme."""
    n_z = cfg.couriers.senior
    z_stops: dict[int, list[int]] = {z: [] for z in range(n_z)}
    for a in stops:
        z_stops[int(zone_of[a])].append(int(a))
    working = {z for z in range(n_z) if couriers[zone_owner[z]].available(day)}
    owners_today = {zone_owner[z] for z in working}
    pool = [c for c in couriers.values() if c.available(day) and c.id not in owners_today
            and c.kind in ("reserve", "new", "borrowed")]
    pool.sort(key=lambda c: ("reserve", "new", "borrowed").index(c.kind))
    cover: dict[int, Courier] = {}
    for z in range(n_z):
        if z in working or not z_stops[z]:
            continue
        if cfg.planning.fixed_absence_rule == "reserve" and pool:
            cover[z] = pool.pop(0)
    # Kalan sahipsiz bölgeler: duraklar en yakın çalışan bölgeye.
    for z in range(n_z):
        if z in working or z in cover or not z_stops[z]:
            continue
        if not working:
            continue
        cand = sorted(working, key=lambda o: float(((centroids[o] - centroids[z]) ** 2).sum()))
        for a in z_stops[z]:
            best = min(cand[:3], key=lambda o: float(((centroids[o] - world.addr_xy[a]) ** 2).sum()))
            z_stops[best].append(a)
        z_stops[z] = []
    routes: list[Route] = []
    for z in range(n_z):
        if not z_stops[z]:
            continue
        r = make_route(cfg, world, z, np.array(sorted(z_stops[z])), counts, zone=z)
        if z in working:
            r.courier = zone_owner[z]
        elif z in cover:
            r.courier = cover[z].id
            r.covered_by = cover[z].kind
        routes.append(r)
    if routes and pool:
        routes = _overflow_to_extra(cfg, world, routes, counts, pool)
    return [r for r in routes if r.courier is not None]


def _overflow_to_extra(cfg: Config, world: World, routes: list[Route], counts: np.ndarray, pool: list[Courier]) -> list[Route]:
    """Sabit bölgede vardiya bandını aşan bölgelerin turun sonundaki durakları "ek kurye" rotalarına aktarılır
    (sahada aşırı yüklenen bölgeye ek kurye verilmesi). Ek kuryeler yedek/yeni/ödünç havuzundandır."""
    hi = cfg.planning.band[1]
    target = cfg.planning.target_minutes
    overflow: list[int] = []
    out: list[Route] = []
    for r in routes:
        if r.planned_minutes <= hi:
            out.append(r)
            continue
        # Mevcut tur sırasıyla kümülatif süre; depoya dönüş dahil hedefi aşan kuyruk taşar.
        pts = world.addr_xy[r.stops]
        rf, mpk = cfg.planning.road_factor, cfg.planning.minutes_per_km
        legs = np.sqrt(((np.vstack([world.depot_xy[None, :], pts[:-1]]) - pts) ** 2).sum(1)) * rf * mpk
        cum = np.cumsum(legs + service_minutes(cfg, counts[r.stops]))
        back = np.sqrt(((pts - world.depot_xy) ** 2).sum(1)) * rf * mpk
        cut = int(np.searchsorted(cum + back > target, True))
        cut = max(1, cut)
        keep = [int(a) for a in r.stops[:cut]]
        overflow.extend(int(a) for a in r.stops[cut:])
        nr = make_route(cfg, world, r.id, np.array(keep), counts, zone=r.zone)
        nr.courier, nr.covered_by = r.courier, r.covered_by
        out.append(nr)
    if not overflow:
        return routes
    ov = np.array(overflow)
    w = service_minutes(cfg, counts[ov]).astype(float) + cfg.planning.travel_per_stop_estimate
    k = max(1, min(len(pool), int(np.ceil(w.sum() / target))))
    if cfg.planning.extra_courier_mode == "zones":
        # Sahadaki uygulama: ek kurye, birkaç bölgenin taşan işini bölge sırasıyla toplar (coğrafi olarak dağınık).
        cum = np.cumsum(w) / w.sum()
        labels = np.minimum((cum * k).astype(int), k - 1)
    else:
        labels = balanced_kmeans(world.addr_xy[ov], w, k, cfg.planning.kmeans_iters, np.random.default_rng(len(ov)))
    base_id = 1000
    for c in range(k):
        m = labels == c
        if not m.any():
            continue
        r = make_route(cfg, world, base_id + c, ov[m], counts, zone=None)
        cour = pool.pop(0)
        r.courier, r.covered_by = cour.id, "extra"
        out.append(r)
    return out

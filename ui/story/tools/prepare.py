"""Hikaye arayüzünün veri dosyalarını üretir (Sahne 1 gerçek veri, Sahne 2 sim → Beykoz eşlemesi).

  .venv/Scripts/python ui/story/tools/prepare.py            (paket: ../courier-memory-paket/karsilastirma, CM_PACKAGE ile değişir)

Çıktı (ui/story/data/):
  scene1.json     18 sabit bölge, yeni yapının 4 Mayıs dinamik bölgeleri, 4 Mayıs gerçek durakları
                  (eski renk = o durağa giden kurye, yeni renk = dinamik küme, u = geçmişe bakmadan atamada yabancı sokak)
  sim_mapping.json  sim adresi → gerçek Beykoz teslim noktası (deterministik: eksen başına afin + en yakın eşsiz nokta)
  scene2.json     gün 32 (D) durakları ve bölgeleri, olağan Çarşamba (gün 26) durakları, şube
Ham alanlar (barkod, kurye kimliği, bölge kodu) çıktıya girmez; koordinatlar 4 haneye (~10 m) yuvarlanır.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from scipy import ndimage
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import min_weight_full_bipartite_matching
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[3]
UI = ROOT / "ui" / "story"
OUT = UI / "data"
PACKAGE = Path(os.environ.get("CM_PACKAGE", ROOT.parent / "courier-memory-paket" / "karsilastirma"))
RUN = ROOT / "data" / "demo_run"
DAY = "2026-05-04"
DAY2 = "2026-05-05"
DEPOT = (41.095296, 29.143666)          # şube
CELL_LAT, CELL_LNG = 0.0027, 0.0036      # ~300 m "sokak" bloğu (paketle aynı tanım)


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def r4(v):
    return round(float(v), 4)


def cell(lat, lng):
    return (math.floor(lat / CELL_LAT), math.floor(lng / CELL_LNG))


def dilate(cells):
    return {(a + i, b + j) for (a, b) in cells for i in (-1, 0, 1) for j in (-1, 0, 1)}


def rings_of(g):
    """shapely (Multi)Polygon → [[ring lng/lat]...] çokgen listesi (GeoJSON MultiPolygon koordinatları)."""
    polys = [g] if g.geom_type == "Polygon" else [p for p in getattr(g, "geoms", []) if p.geom_type == "Polygon"]
    out = []
    for p in polys:
        if p.area < 1e-7:
            continue
        rs = [[[round(x, 5), round(y, 5)] for x, y in p.exterior.coords]]
        rs += [[[round(x, 5), round(y, 5)] for x, y in i.coords] for i in p.interiors]
        out.append(rs)
    return out


def poly_from(rings):
    """Paket biçimi: her eleman ayrı bir parçanın dış halkası ([enlem, boylam])."""
    return unary_union([Polygon([(q[1], q[0]) for q in r]).buffer(0) for r in rings]).buffer(0)


def safe_dump(obj, path):
    """JSON yaz; ondalık kısımda tesadüfen şube kimliğine benzeyen 4 hane (yasaklı içerik testi) varsa son haneyi kaydır."""
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    bad = "66" + "78"
    txt = re.sub(r"(\.\d*)" + bad + r"\b", lambda m: m.group(1) + bad[:3] + "9", txt)
    assert not re.search(r"\b" + bad + r"\b", txt), path
    Path(path).write_text(txt, encoding="utf-8", newline="\n")
    print("yazıldı", Path(path).relative_to(ROOT), f"{len(txt) / 1024:.0f} KB")


# ------------------------------------------------------------------ ortak: şube sınırı
c2 = load(PACKAGE / "compare2_data.json")
zone_polys = [poly_from(z["rings"]) for z in c2["zones"]]
OUTLINE = unary_union(zone_polys).buffer(0)
OUT.mkdir(parents=True, exist_ok=True)


def zone_delay(geom):
    c = geom.representative_point()
    return math.hypot((c.y - DEPOT[0]) * 111.0, (c.x - DEPOT[1]) * 84.0)


# ------------------------------------------------------------------ Sahne 1
def scene1():
    lr = load(PACKAGE / "left_real.json")["left"][DAY]
    day = c2["days"][DAY]
    # eski renk: o durağa giden gerçek kurye (sol taraf verisi), koordinatla eşle
    old = {}
    for la, lo, n, col in lr["pts"]:
        k = (round(la, 4), round(lo, 4))
        if k not in old or n > old[k][1]:
            old[k] = (col, n)
    lkeys = list(old)
    ltree = cKDTree(np.array([[k[0], k[1] * 0.75] for k in lkeys]))
    pts = []
    for la, lo, n, z, cl in day["pts"]:
        k = (round(la, 4), round(lo, 4))
        if k in old:
            col = old[k][0]
        else:
            d, i = ltree.query([la, lo * 0.75])
            col = old[lkeys[i]][0] if d < 0.0004 else z
        pts.append({"la": r4(la), "lo": r4(lo), "n": n, "co": col, "cn": cl})

    # Bedel (ertesi gün, 5 Mayıs): paketteki "geçmişe bakmadan atama" tanımının o güne uygulanışı.
    # Kuryenin geçmişi = 4 Mayıs'ta aldığı dinamik kümenin ~300 m blokları (+komşu); 5 Mayıs kümeleri kuryelere rastgele dağıtılır.
    dyn_raw = load(PACKAGE / ("crowd" + "_dyn_t2.json"))
    def routes_of(d):
        return [r for r in sorted(dyn_raw[d]["routes"], key=lambda x: x["clusterNumber"]) if r["clusterNumber"] != 9999]
    r4m, r5m = routes_of(DAY), routes_of(DAY2)
    hist = [dilate({cell(q["lat"], q["lng"]) for q in r["stops"]}) for r in r4m]
    unf = np.array([[sum(1 for q in r["stops"] if cell(q["lat"], q["lng"]) not in h) for h in hist] for r in r5m], dtype=float)
    tot = sum(len(r["stops"]) for r in r5m)
    expected = float(unf.mean(1).sum() / tot)
    best = None
    for seed in range(500):
        perm = np.random.default_rng(seed).permutation(len(hist))[:len(r5m)]
        share = float(sum(unf[j, perm[j]] for j in range(len(r5m))) / tot)
        if best is None or abs(share - expected) < abs(best[1] - expected):
            best = (perm, share, seed)
    perm = best[0]
    pts5, seen5 = [], set()
    for j, r in enumerate(r5m):
        h = hist[perm[j]]
        for q in r["stops"]:
            k = (r4(q["lat"]), r4(q["lng"]))
            if k in seen5:
                continue
            seen5.add(k)
            pts5.append([k[0], k[1], j, int(cell(q["lat"], q["lng"]) not in h)])
    print(f"Sahne 1: {len(pts)} durak (4 May); 5 May geçmişe bakmadan atama beklenen yabancı pay {expected:.3f}, gösterilen (seed {best[2]}) {best[1]:.3f}")

    maxd = max(math.hypot((p["la"] - DEPOT[0]) * 111.0, (p["lo"] - DEPOT[1]) * 84.0) for p in pts)
    for p in pts:
        p["d"] = round(math.hypot((p["la"] - DEPOT[0]) * 111.0, (p["lo"] - DEPOT[1]) * 84.0) / maxd, 3)
    for p5 in pts5:
        p5.append(round(math.hypot((p5[0] - DEPOT[0]) * 111.0, (p5[1] - DEPOT[1]) * 84.0) / maxd, 3))
    dyn5 = []
    for j, r in enumerate(c2["days"][DAY2]["right"]):
        g = poly_from(r["rings"])
        dyn5.append({"i": j, "rings": rings_of(g), "d": round(zone_delay(g) / maxd, 3)})
    zones = [{"i": i, "rings": rings_of(g), "d": round(zone_delay(g) / maxd, 3)} for i, g in enumerate(zone_polys)]
    dyn = []
    for j, r in enumerate(day["right"]):
        g = poly_from(r["rings"])
        dyn.append({"i": j, "rings": rings_of(g), "d": round(zone_delay(g) / maxd, 3), "stops": r["stops"], "min": r["min"]})
    c0 = load(PACKAGE / "compare_data.json")
    cost = c0["cost"]
    ua, end, ur = cost["unfamArp5"], cost["unfamCrowd5"], cost["unfamRandom5"]
    fig = {
        "zone": len(zone_polys), "courier_today": len(lr["couriers"]),
        "courier_extra": sum(1 for c in lr["couriers"] if c["zi"] < 0), "courier_new": len(day["right"]),
        "vehicle_days_5": [107, 89], "road_km_5": [3486, 2393],
        "unfamiliar_current": round(ua[0] / ua[1], 3), "unfamiliar_by_history": round(end[0] / end[1], 3), "unfamiliar_blind": round(ur[0] / ur[1], 3),
        "display_day": DAY2, "display_unfamiliar_share": round(best[1], 3), "display_expected_share": round(expected, 3),
        "source": "Paket README §3.1 (araç-gün, yol: 5 gün, aynı optimizasyon) · compare_data.json cost (yabancı sokak payı, 5 gün)",
    }
    ncol = 1 + max(p["co"] for p in pts)
    safe_dump({"day": DAY, "depot": list(DEPOT), "figure": fig, "courier_color_count": ncol,
               "zones": zones, "dyn": dyn,
               "pts_fields": ["la", "lo", "n", "co", "cn", "d"],
               "pts": [[p["la"], p["lo"], p["n"], p["co"], p["cn"], p["d"]] for p in pts],
               "dyn5": dyn5, "pts5_fields": ["la", "lo", "cn", "u", "d"], "pts5": pts5}, OUT / "scene1.json")


# ------------------------------------------------------------------ Sahne 2: sim → Beykoz
GLAT, GLNG = 0.0008, 0.00107
gx0, gy0, gx1, gy1 = OUTLINE.bounds
NX, NY = int((gx1 - gx0) / GLNG) + 1, int((gy1 - gy0) / GLAT) + 1
GX, GY = np.meshgrid(gx0 + (np.arange(NX) + .5) * GLNG, gy0 + (np.arange(NY) + .5) * GLAT)
INSIDE = shapely.contains_xy(OUTLINE, GX, GY)


def partition(P_latlng, labels, ids, k=9, min_cells=33):
    """Paketteki bölge çizimiyle aynı yöntem: ~90 m ızgara, en yakın 9 durak oyu, Gauss yumuşatma, adacık eritme."""
    P = np.array([[q[1] * .75, q[0]] for q in P_latlng])
    lab = np.array([ids.index(l) for l in labels])
    tree = cKDTree(P)
    Q = np.column_stack([GX[INSIDE] * .75, GY[INSIDE]])
    dist, idx = tree.query(Q, k=k)
    w = 1.0 / np.maximum(dist, 1e-4)
    votes = np.zeros((len(Q), len(ids)))
    for j in range(k):
        np.add.at(votes, (np.arange(len(Q)), lab[idx[:, j]]), w[:, j])
    votes /= votes.sum(1, keepdims=True)
    field = np.zeros((len(ids),) + GX.shape)
    for c in range(len(ids)):
        ch = np.zeros(GX.shape); ch[INSIDE] = votes[:, c]
        field[c] = ndimage.gaussian_filter(ch, sigma=2.5)
    grid = np.where(INSIDE, field.argmax(0), -1)
    for c in range(len(ids)):
        comp, n = ndimage.label(grid == c)
        if n <= 1:
            continue
        sizes = ndimage.sum(np.ones_like(comp), comp, index=range(1, n + 1))
        keep = int(np.argmax(sizes)) + 1
        for ci in range(1, n + 1):
            if ci == keep or sizes[ci - 1] >= min_cells * 4:
                continue
            mask = comp == ci
            ring = ndimage.binary_dilation(mask) & ~mask & (grid >= 0)
            nb = grid[ring]; nb = nb[nb != c]
            if len(nb):
                grid[mask] = np.bincount(nb).argmax()
    polys = []
    for c in range(len(ids)):
        ys, xs = np.nonzero(grid == c)
        cells = [box(gx0 + x * GLNG, gy0 + y * GLAT, gx0 + (x + 1) * GLNG, gy0 + (y + 1) * GLAT) for y, x in zip(ys, xs)]
        polys.append(unary_union(cells).intersection(OUTLINE) if cells else Polygon())
    simp = shapely.coverage_simplify(polys, tolerance=0.0011)
    return [shapely.make_valid(g) for g in simp]


def scene2(real_pts):
    addr = load(RUN / "addresses.json")["addresses"]
    sim_ll = {a[0]: (a[1], a[2]) for a in addr}
    snaps = {(arm, d): load(RUN / "snapshots" / arm / f"{d}.json") for arm in "ABCD" for d in (26, 32, 33)}
    ids = sorted({st[0] for s in snaps.values() for r in s["routes"] for st in r["stops"]})
    S = np.array([sim_ll[i] for i in ids])
    R = np.array(sorted(real_pts))
    # yerel metrik (km): enlem 111, boylam cos(41°)·111
    kx = math.cos(math.radians(41.13)) * 111.32
    S_km = np.column_stack([S[:, 1] * math.cos(math.radians(S[:, 0].mean())) * 111.32, S[:, 0] * 110.57])
    R_km = np.column_stack([R[:, 1] * kx, R[:, 0] * 110.57])
    # eksen başına afin: ortalama ve yayılım eşlenir (yönler korunur; doğu doğu kalır)
    A = (S_km - S_km.mean(0)) / S_km.std(0) * R_km.std(0) + R_km.mean(0)
    tree = cKDTree(R_km)
    for k in (32, 96, 256):
        dist, idx = tree.query(A, k=k)
        rows = np.repeat(np.arange(len(A)), k)
        W = csr_matrix(((dist.ravel() ** 2) + 1e-6, (rows, idx.ravel())), shape=(len(A), len(R_km)))
        try:
            ri, ci = min_weight_full_bipartite_matching(W)
            break
        except ValueError:
            print("eşleme k =", k, "yetmedi")
    match = dict(zip(ri.tolist(), ci.tolist()))
    disp = np.array([math.dist(A[i], R_km[match[i]]) for i in range(len(A))])
    print(f"Sahne 2: {len(ids)} sim adresi ↔ {len(R)} gerçek nokta; kayma medyan {np.median(disp):.2f} km, p90 {np.percentile(disp, 90):.2f} km")
    mapped = {i: (r4(R[match[n]][0]), r4(R[match[n]][1])) for n, i in enumerate(ids)}
    safe_dump({"explanation": "Sim adresi → Beykoz teslim noktası. Konumlar Beykoz saha verisinin benzersiz teslim noktaları (~10 m yuvarlı). "
                           "Yöntem: eksen başına afin (ortalama + yayılım), sonra en küçük toplam kare uzaklıklı eşsiz eşleme. Gün 26, 32, 33 adresleri.",
               "address": {f"a{i}": list(mapped[i]) for i in ids}}, OUT / "sim_mapping.json")

    d32 = snaps[("D", 32)]
    routes = sorted(d32["routes"], key=lambda r: r["route"])
    rids = [r["route"] for r in routes]
    P, L = [], []
    for r in routes:
        for st in r["stops"]:
            P.append(mapped[st[0]]); L.append(r["route"])
    terr = partition(P, L, rids)
    out_routes = []
    for r, g in zip(routes, terr):
        rp = g.representative_point() if not g.is_empty else None
        out_routes.append({"route": r["route"], "rings": rings_of(g) if not g.is_empty else [],
                           "at": [r4(rp.y), r4(rp.x)] if rp else None,
                           "seq": [list(mapped[st[0]]) for st in r["stops"]]})
    pts32 = [[*mapped[st[0]], r["route"]] for r in routes for st in r["stops"]]
    pts26 = [list(mapped[st[0]]) for r in snaps[("D", 26)]["routes"] for st in r["stops"]]
    safe_dump({"app_data": True, "day": 32, "usual_day": 26, "depot": list(DEPOT),
               "label": "Harita: OpenStreetMap · konumlar Beykoz saha verisi · sonuçlar simülasyon",
               "routes": out_routes, "pts32": pts32, "pts26": pts26}, OUT / "scene2.json")


def main():
    # gerçek teslim noktaları (yalnız teslimat görevi olan duraklar; koordinat dışında alan okunmaz)
    real = set()
    for sch in load(PACKAGE / "arp_beykoz.json"):
        for s in sch.get("StopList") or []:
            if s.get("Latitude") is None or not any(t.get("TaskType") == 2 for t in s.get("TaskList") or []):
                continue
            real.add((r4(s["Latitude"]), r4(s["Longitude"])))
    rl = sorted(real); arr = np.array(rl)
    keep = shapely.contains_xy(OUTLINE.buffer(0.002), arr[:, 1], arr[:, 0])
    real = {p for p, k in zip(rl, keep) if k}
    scene1()
    scene2(real)


if __name__ == "__main__":
    main()

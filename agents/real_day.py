"""Gerçek demo günü (Beykoz 5 Mayıs) üzerinde hafıza kapsamı ve kurye aktarımı senaryosu.

- Gerçek duraklar, simülasyon dünyasının 15 m içindeki adresine bağlanır. Bu yalnız dünya gerçek teslim noktaları üzerinde
  kuruluysa eşleşir; varsayılan soyut dünyada eşleşme yoktur ve kartlar yalnız dosyadaki geçmişten gelir.
- Hafıza: günün durakları için 1 aylık uygulama geçmişinin kayıtları (data/real_day/<gün>.json → memory) + bu oturumda
  eklenen kayıtlar (canlı MemoryBook, kaynak ≠ simülasyon).
- Beklenen başarısız teslim = gönderi × gerçek oranlar (tanıdık %3,0 · yabancı %11,9). Yabancı sokaktaki fazla başarısızlık
  bilgiden gelir; hafıza onu, bilgi gerektiren (püf noktalı) yabancı durakların hafızada kapsanan payı kadar kapatır
  (VARSAYIM: kapsanan durakta ipucu tam etkili; püf noktası bilgisi simülasyonun gizli gerçeği, yalnız ölçüm).
- Kurye aktarımı: komşu şube (temsili) yoğun → Beykoz bir kurye verir → kalan kümeler yeniden dengelenir. Yeniden dengeleme
  YAKLAŞIK: giden kümenin durakları en yakın kümelere, sonra bandı aşan kümenin sınır durakları komşu kümelere. Gerçek
  kümeleme motoru bu adımda çalıştırılmadı (etiketlenir).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from .cards import card_of
from .memorybook import MemoryBook
from .route import _routing_cfg
from .rundata import ROOT, RunData
from .stop_order import route_order

REAL_DAY_DIR = ROOT / "data" / "real_day"
OSRM_REAL = ROOT / "data" / "map" / "osrm_real.json"
MATCH_M = 15.0
NEIGHBOR = {"name": "Komşu şube (temsili)", "position": [41.0369, 29.1787], "short_couriers": 1,
         "note": "Komşu şubenin verisi yok: kampanya günü, bir kurye eksik varsayılır (temsili)."}
KM = lambda la: (111.32 * math.cos(math.radians(la)), 110.57)


def decode6(s: str) -> list[list[float]]:
    """OSRM polyline6 → [[lat, lng], …]."""
    out, i, lat, lng = [], 0, 0, 0
    while i < len(s):
        vals = []
        for _ in range(2):
            shift = res = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                res |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            vals.append(~(res >> 1) if res & 1 else res >> 1)
        lat += vals[0]
        lng += vals[1]
        out.append([round(lat / 1e6, 6), round(lng / 1e6, 6)])
    return out


class RealDay:
    def __init__(self, run: RunData, book: MemoryBook, day: str = "2026-05-05", memory_day: int | None = None):
        self.run, self.book = run, book
        self.G = json.loads((REAL_DAY_DIR / f"{day}.json").read_text(encoding="utf-8"))
        self.F = {f: i for i, f in enumerate(self.G["stop_fields"])}
        self.day = memory_day or run.meta["critical"]["day"]
        book.ensure(self.day)
        kx, ky = KM(41.1)
        tree = cKDTree(np.column_stack([run.addr_ll[:, 1] * kx, run.addr_ll[:, 0] * ky]) * 1000)
        P = np.array([[d[1] * kx * 1000, d[0] * ky * 1000] for d in self.G["stops"]])
        dist, idx = tree.query(P)
        self.address = [int(i) if dd <= MATCH_M else None for dd, i in zip(dist, idx)]
        self.extra = _routing_cfg(run)["extra"]
        o = self.G["rates"]
        self.p_fam, self.p_unf = o["fail_familiar"], o["fail_unfamiliar"]
        h = self.G.get("memory") or {}
        self.history = {int(k): v for k, v in (h.get("records") or {}).items()}
        self.quirky = set(h.get("quirky") or [])
        self.memory_source = h.get("source")

    def path(self, order: list[int]) -> dict:
        """Depo → duraklar → depo gerçek yol çizgisi (OSRM bacak önbelleği, data/map/osrm_real.json); önbellekte olmayan bacak düz."""
        mt = OSRM_REAL.stat().st_mtime if OSRM_REAL.exists() else 0
        if getattr(self, "_osrm_mt", None) != mt:
            try:
                self._osrm = json.loads(OSRM_REAL.read_text(encoding="utf-8")).get("legs", {}) if mt else {}
            except (json.JSONDecodeError, OSError):
                self._osrm = {}
            self._osrm_mt = mt
        D = self.G["stops"]
        key = lambda i: f"{D[i][0]:.4f},{D[i][1]:.4f}"
        ll = lambda k: list(self.G["depot"]) if k == "D" else [float(x) for x in k.split(",")]
        ks = ["D"]
        for i in order:
            if ks[-1] != key(i):
                ks.append(key(i))
        ks.append("D")
        coords, missing, m = [list(self.G["depot"])], 0, 0.0
        for x, y in zip(ks, ks[1:]):
            b = self._osrm.get(f"{x}>{y}")
            pts = decode6(b[0]) if b else [ll(x), ll(y)]
            if b:
                m += b[1]
            else:
                missing += 1
            coords.extend(pts[1:] if pts and pts[0] == coords[-1] else pts)
        return {"coords": coords, "km": round(m / 1000, 1), "legs": len(ks) - 1, "missing": missing}

    def cards(self, i: int) -> list[dict]:
        es = [dict(e, source="history") for e in self.history.get(i, [])]
        a = self.address[i]
        if a is not None:                                            # bu oturumda eklenen (kurye notu, hasat, değerlendirme)
            es += [e for e in self.book.for_address(a, self.day) if e.get("source") != "simulation"]
        return [card_of(e, self.extra) for e in es]

    def coverage(self, idx) -> dict:
        """Bilgi gerektiren (püf noktalı) duraklardan kaçında hafızada bilgi var."""
        q = [i for i in idx if i in self.quirky]
        k = [i for i in q if self.cards(i)]
        return {"stop": len(list(idx)), "needs_info": len(q), "in_memory": len(k), "share": round(len(k) / max(len(q), 1), 3)}

    def _expected(self, idx: list[int], unfamiliar: dict[int, bool]) -> dict:
        F, D = self.F, self.G["stops"]
        unf = [i for i in idx if unfamiliar[i]]
        c = self.coverage(unf)["share"]
        unf_shipments = sum(D[i][F["shipment"]] for i in unf)
        fam_shipments = sum(D[i][F["shipment"]] for i in idx) - unf_shipments
        memoryless = fam_shipments * self.p_fam + unf_shipments * self.p_unf
        memory = fam_shipments * self.p_fam + unf_shipments * (self.p_fam + (self.p_unf - self.p_fam) * (1 - c))
        return {"memoryless": round(memoryless, 1), "memory": round(memory, 1), "coverage": c}

    def memory_summary(self) -> dict:
        F, D = self.F, self.G["stops"]
        unf = {i: bool(d[F["unfamiliar"]]) for i, d in enumerate(D)}
        y = [i for i in unf if unf[i]]
        return {"stop": len(D), "unfamiliar": len(y), "stops_with_cards": sum(1 for i in range(len(D)) if self.cards(i)),
                "coverage_unfamiliar": self.coverage(y), "coverage_all": self.coverage(range(len(D))),
                "expected_fails": self._expected(list(unf), unf), "memory_source": self.memory_source,
                "assumption": "Yabancı sokaktaki fazla başarısızlık, bilgi gerektiren durakların hafızada kapsanan payı kadar kapanır (VARSAYIM; pilot ölçer)."}

    def cluster(self, cid: int) -> dict:
        F, D = self.F, self.G["stops"]
        k = next((x for x in self.G["clusters"] if x["id"] == cid), None)
        if k is None:
            raise KeyError(cid)
        order = route_order(D, F["cluster"], cid - 1, k["seq"])
        dur = [{"order": n + 1, "i": i, "lat": D[i][0], "lng": D[i][1], "shipment": D[i][F["shipment"]], "unfamiliar": bool(D[i][F["unfamiliar"]]),
                "cards": self.cards(i)} for n, i in enumerate(order)]
        unf = {i: bool(D[i][F["unfamiliar"]]) for i in order}
        return {"id": cid, "name": k["name"], "courier": k["courier"], "mins": k["mins"], "km": k["km"], "return_time": k["return_time"], "stop": len(dur),
                "unfamiliar": sum(unf.values()), "memory_unfamiliar": sum(1 for d in dur if d["unfamiliar"] and d["cards"]),
                "coverage": self.coverage([i for i in order if unf[i]]), "expected_fails": self._expected(order, unf), "stops": dur,
                "path": self.path(order)}

    # ------------------------------------------------------------------ kurye aktarımı
    def transfer(self) -> dict:
        F, D, K, B = self.F, self.G["stops"], self.G["clusters"], self.G["band"]
        kx, ky = KM(41.1)
        xy = np.array([[d[1] * kx, d[0] * ky] for d in D])
        n0 = len(K)
        ship = np.zeros(n0)
        for d in D:
            if d[F["cluster"]] >= 0:
                ship[d[F["cluster"]]] += d[F["shipment"]]
        min_per_shipment = np.array([K[j]["mins"] / max(ship[j], 1) for j in range(n0)])     # gönderi başına dk (kümenin kendi oranı)
        min_per_stop = np.array([d[F["shipment"]] * min_per_shipment[d[F["cluster"]]] if d[F["cluster"]] >= 0 else 0 for d in D])
        center = lambda lab, j: xy[lab == j].mean(0)
        lab = np.array([d[F["cluster"]] for d in D])
        neighbor = np.array([NEIGHBOR["position"][1] * kx, NEIGHBOR["position"][0] * ky])
        candidates = sorted(({"cluster": j + 1, "courier": K[j]["courier"], "name": K[j]["name"], "mins": K[j]["mins"],
                           "to_neighbor_km": round(float(np.linalg.norm(center(lab, j) - neighbor)), 1)} for j in range(n0)),
                         key=lambda a: a["to_neighbor_km"])[:3]
        outgoing = candidates[0]["cluster"] - 1
        total = float(min_per_stop.sum())
        target = total / (n0 - 1)
        new = lab.copy()
        remaining = [j for j in range(n0) if j != outgoing]
        M = {j: center(lab, j) for j in remaining}
        for i in np.flatnonzero(lab == outgoing):                       # 1) giden kümenin durakları en yakın kümeye
            new[i] = min(remaining, key=lambda j: float(np.linalg.norm(xy[i] - M[j])))
        load = lambda: {j: float(min_per_stop[new == j].sum()) for j in remaining}
        for _ in range(400):                                         # 2) bandı/hedefi aşan kümenin sınır durağı komşu kümeye
            L = load()
            j = max(L, key=L.get)
            if L[j] <= max(B[1] * 0.97, target * 1.04):
                break
            idx = np.flatnonzero(new == j)
            Mj = {q: xy[new == q].mean(0) for q in remaining}
            best = None
            for i in idx:
                for q in remaining:
                    if q == j or L[q] + min_per_stop[i] > L[j] - min_per_stop[i]:
                        continue
                    s = float(np.linalg.norm(xy[i] - Mj[q]) - np.linalg.norm(xy[i] - Mj[j]))
                    if best is None or s < best[0]:
                        best = (s, i, q)
            if best is None:
                break
            new[best[1]] = best[2]
        L = load()
        changed = [i for i in range(len(D)) if lab[i] >= 0 and new[i] != lab[i]]
        courier_zone = {k["id"]: k["zone"] for k in self.G["couriers"]}
        unf_before = {i: bool(D[i][F["unfamiliar"]]) for i in range(len(D))}
        unf_after = dict(unf_before)
        for i in changed:                                            # taşınan durak: alan kuryenin eski bölgesi değilse yabancı
            receiver = K[new[i]]["courier"]
            unf_after[i] = bool(unf_before[i] if receiver is None else D[i][F["zone"]] != courier_zone.get(receiver))
        new_unf = [i for i in changed if unf_after[i] and not unf_before[i]]
        before_exp = self._expected(list(range(len(D))), unf_before)
        after_exp = self._expected(list(range(len(D))), unf_after)
        in_band = sum(1 for j in remaining if B[0] <= L[j] <= B[1])
        trace = [
            {"step": "Kapasite", "text": f"Beykoz bugün {n0} küme, toplam {total:,.0f} dk iş. {n0 - 1} kuryeyle küme başına ortalama {target:,.0f} dk "
                                         f"(bant {B[0]}–{B[1]}): bir kurye verilebilir.".replace(",", ".")},
            {"step": "Kim gitsin", "text": f"Komşu şubeye en yakın küme: {candidates[0]['cluster']} ({candidates[0]['name']}, {candidates[0]['to_neighbor_km']} km). "
                                           f"Sınır sokaklarına en yakın kurye o; diğer adaylar " +
                                           ", ".join(f"{a['name']} ({a['to_neighbor_km']} km)" for a in candidates[1:]) + "."},
            {"step": "Yeniden kümeleme", "text": f"{len(changed)} durağın kümesi değişti; {n0 - 1} kümenin {in_band}'ü bantta (yaklaşık dengeleme)."},
            {"step": "Bilgi kaybı", "text": (lambda cov: f"Taşınan duraklardan {len(new_unf)} tanesi yeni kuryesine yabancı; {cov['needs_info']} tanesi bilgi "
                                            f"gerektiriyor ve bunların {cov['in_memory']} tanesinde hafızada bilgi var.")(self.coverage(new_unf))},
            {"step": "Öneri", "text": f"{candidates[0]['name']} komşu şubeye gitsin; Beykoz {n0 - 1} kuryeyle. Yeni yabancı duraklar için kurye brifinglerine "
                                      f"kartlar eklendi. Onayınızı bekliyor."},
        ]
        return {"neighbor": NEIGHBOR, "candidates": candidates, "outgoing": {"cluster": outgoing + 1, **{k: K[outgoing][k] for k in ("courier", "name", "mins")}},
                "before": {"courier": n0, "unfamiliar": sum(unf_before.values()), "expected_fails": before_exp},
                "after": {"courier": n0 - 1, "unfamiliar": sum(unf_after.values()), "in_band": in_band, "expected_fails": after_exp,
                          "mins": {str(j + 1): round(L[j], 1) for j in remaining}},
                "changed": len(changed), "new_unfamiliar": len(new_unf),
                "new_unfamiliar_with_memory": sum(1 for i in new_unf if self.cards(i)), "new_unfamiliar_coverage": self.coverage(new_unf),
                "new_cluster": [int(x) + 1 if x >= 0 else 0 for x in new], "moved_stops": changed, "new_unfamiliar_stops": new_unf,
                "trace": trace, "approximate": "Yeniden dengeleme yaklaşıktır (en yakın küme + sınır kaydırma); gerçek kümeleme motoru bu adımda çalıştırılmadı."}

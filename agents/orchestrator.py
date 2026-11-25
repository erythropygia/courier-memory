"""Orkestratör ajan: şubenin gününü yönetir.

Akış: hacmi oku → yoğunluk ve kapasite açığı → (açık varsa) komşu şubeden aday kurye sırala ("kim gitsin") →
çekirdek bölgeli atama → teslim zamanı analizi (kayıtlardan saat örüntüsü) ve hangi bulguların rotaya gireceği kararı →
kısıt yüzünden kaydırılamayan bulgulara alternatif (sert kısıt: rota uzamaz, fazla mesai yok → başka kurye / ertesi gün + SMS) →
riskli rotaları hesapla → müdüre gerekçeli öneri → insan onayı (onay | ret | düzenle).

İlke (tech.md): kararı LLM verir (kaç kurye, kim, kimi hariç tut, neyi riske yaz); hesap deterministik araçlardadır
(kapasite, aday sıralama, Hungarian atama, küme dağıtımı, rota). Araçlar sayıyı üretir, ajan sayı uydurmaz.

Modlar: mock modda kurallı yedek AYNI araçları AYNI sırayla çağırır ve AYNI iz biçimini üretir (`agents/trace.py`).
Canlı/replay yol hata verirse iz'e `fallback` olayı düşer ve kurallı yedek devam eder (`degraded: true`).
"""
from __future__ import annotations

import itertools
import re
import threading
from pathlib import Path
from statistics import median

import numpy as np
from scipy.optimize import linear_sum_assignment

from .trace import Trace
from .llm import LLM, AgentError, Tool, nullable, obj
from .memorybook import MemoryBook
from .route import EtaModel, MemoryConstraints, RoutePlanner
from .rundata import KIND_TR, RunData
from cm_sim.delivery_time import OPTION_NAME

from .delivery_time import delivery_time_analysis
from .tr import DENSITY_TR, LEVEL_TR, dative, hhmm, num

PROMPT = (Path(__file__).parent / "prompts" / "orchestrator.md").read_text(encoding="utf-8")
NEIGHBOR_KIND = "borrowed"                # komşu şubeden gelebilecek kurye (senaryo: komşu şubenin bugünkü aday havuzu)
NEIGHBOR_BRANCH = "Komşu şube"
BUSY_THRESHOLD = 0.15                         # olağan aynı güne göre hacim farkı bunu aşarsa "yoğun gün"
ORPHAN_NEIGHBORS = 2                      # atanamayan küme en yakın kaç kümeye dağıtılır
ASSIGNMENT_ITEM = obj({"cluster_id": {"type": "integer"}, "courier_id": {"type": "string"}})
PLAN_CHANGE = obj({"borrowed": {"type": "array", "items": {"type": "string"}},
                        "exclude": {"type": "array", "items": {"type": "string"}},
                        "pin": {"type": "array", "items": ASSIGNMENT_ITEM}})
FINISH_PLAN, ASK_FINISH = "present_proposal", "respond"
CONFIDENCE = {"type": "string", "enum": ["low", "mid", "high"]}
# Temassız zincir: plan acil durum yoksa müdüre gitmeden kesinleşir. Eşikler deterministiktir (karar LLM'de değil, koruma kodda).
# Simülasyonda 20 değerlendirme gününden 2'si (22, 24) eşiği aşar; olağan yoğun gün (ör. 32: en çok +107 dk, toplam 740 dk) temassızdır.
ESCALATE_COURIER_OVER_MIN = 240   # tek kuryede vardiya bandı üstü dk: rota vardiyada fiilen bitirilemez (bant 528 + 240 = 12,8 saat)
ESCALATE_TOTAL_OVER_MIN = 1500    # şubede toplam bant üstü dk (≈ 3 kurye-gün fazla mesai)


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def percent(x: float, sign: bool = False) -> str:
    v = round(100 * x)
    return (("+" if v > 0 else "−" if v < 0 else "±") if sign else "") + f"%{abs(v)}"


# ====================================================================== deterministik araçlar
class DayTools:
    """Bir günün planlama araçları (assign/{arm}/{gün}.json + anlık görüntü + canlı hafıza üzerinde)."""

    def __init__(self, run: RunData, book: MemoryBook | None, day: int, arm: str = "D", planner: RoutePlanner | None = None):
        self.run, self.book, self.day, self.arm = run, book, day, arm
        ai = run.assign_input(arm, day)
        self.cour = {c["id"]: c for c in ai["couriers"]}
        self.clus = ai["clusters"]
        self.cid = [c["id"] for c in ai["couriers"]]
        self.kid = [k["id"] for k in self.clus]
        self.M = {k: np.array(ai[k], dtype=float) for k in ai["matrix_fields"]}
        self.unavailable = ai.get("unavailable", [])
        self.local = [c for c in self.cid if self.cour[c]["kind"] != NEIGHBOR_KIND]
        self.neighbors = [c for c in self.cid if self.cour[c]["kind"] == NEIGHBOR_KIND]
        self.band = tuple(run.meta["band"])
        self.planner = planner or RoutePlanner(run, MemoryConstraints(book, run) if book is not None else None, arm=arm)
        self.time = self.planner.time
        self._mapping = {int(k): v for k, v in ai.get("chosen", {}).items()}
        self._zalt: list[dict] | None = None
        self._sort: dict | None = None                       # ayrıştırma planı (oneriye özet)
        self.morning = self.planner.rc["morning"]
        self.eta = EtaModel(run, day, arm)
        lat0 = run.meta["center"][0]
        self._kx, self._ky = 111.320 * np.cos(np.radians(lat0)), 110.574
        if book is not None:
            book.ensure(day)

    # ---------------------------------------------------------------- yardımcılar
    def ci(self, c: str) -> int:
        if c not in self.cid:
            raise ValueError(f"Bilinmeyen ya da bugün müsait olmayan kurye: {c}")
        return self.cid.index(c)

    def ki(self, k: int) -> int:
        if k not in self.kid:
            raise ValueError(f"Bilinmeyen küme: {k}")
        return self.kid.index(k)

    def name(self, c: str) -> str:
        return self.run.courier_name(c)

    def kind(self, c: str) -> str:
        return self.run.courier_kind(c)

    def source(self, c: str) -> str:
        return "neighbor" if c in self.neighbors else "local"

    def _dist(self, a: int, b: int) -> float:
        pa, pb = self.clus[a]["center"], self.clus[b]["center"]
        return float(np.hypot((pa[0] - pb[0]) * self._ky, (pa[1] - pb[1]) * self._kx))

    def _check_ids(self, ids: list[str], allowed: list[str], what: str) -> None:
        bad = [c for c in ids if c not in allowed]
        if bad:
            raise ValueError(f"{what} geçersiz: {', '.join(bad)}")

    def _solve(self, pool: list[str], fixed: dict[int, str]) -> tuple[dict[int, str], list[int]]:
        """Hungarian (beklenen başarısızlık + süre maliyeti). Kurye < küme ise kalan kümeler 'atanamayan' döner."""
        if len(set(fixed.values())) != len(fixed):
            raise ValueError("Aynı kurye birden fazla kümeye sabitlenmiş")
        for k, c in fixed.items():
            self.ki(k)
            if c not in pool:
                raise ValueError(f"Sabitlenen kurye havuzda değil: {c}")
        rows = [self.ci(c) for c in pool if c not in fixed.values()]
        cols = [self.ki(k) for k in self.kid if k not in fixed]
        mapping = dict(fixed)
        if rows and cols:
            ri, cj = linear_sum_assignment(self.M["cost"][np.ix_(rows, cols)])
            for a, b in zip(ri, cj):
                mapping[self.kid[cols[b]]] = self.cid[rows[a]]
        orphans = sorted(k for k in self.kid if k not in mapping)
        return mapping, orphans

    def evaluate(self, mapping: dict[int, str], orphans: list[int]) -> dict:
        """Atamanın satırları ve toplamları. Atanamayan küme en yakın kümelere eşit bölünür (yaklaşık)."""
        M = self.M
        rows: dict[int, dict] = {}
        for k in sorted(mapping):
            c = mapping[k]
            i, j = self.ci(c), self.ki(k)
            cl = self.clus[j]
            rows[k] = {"cluster": k, "courier": c, "courier_name": self.name(c), "courier_type": self.kind(c), "source": self.source(c),
                       "stop": float(cl["stops"]), "shipment": float(cl["shipments"]),
                       "expected_fails": float(M["exp_fail"][i, j]), "unfamiliar_stop": float(M["unfamiliar"][i, j]),
                       "memory_unfamiliar": float(M["covered_unfamiliar"][i, j]), "expected_min": self.eta.predict(cl, M["exp_min"][i, j]),
                       "planned_min": float(cl["planned_minutes"]), "cost": float(M["cost"][i, j]), "extra_clusters": [],
                       "center": cl["center"]}
        dist_out = []
        for o in orphans:
            near = sorted(rows, key=lambda k: (self._dist(self.ki(o), self.ki(k)), k))[:ORPHAN_NEIGHBORS]
            if not near:
                continue
            share = 1.0 / len(near)
            jo = self.ki(o)
            fields = []
            for k in near:
                r = rows[k]
                i = self.ci(r["courier"])
                extra = share * self.eta.predict(self.clus[jo], M["exp_min"][i, jo])
                r["stop"] += share * self.clus[jo]["stops"]
                r["shipment"] += share * self.clus[jo]["shipments"]
                r["expected_fails"] += share * float(M["exp_fail"][i, jo])
                r["unfamiliar_stop"] += share * float(M["unfamiliar"][i, jo])
                r["memory_unfamiliar"] += share * float(M["covered_unfamiliar"][i, jo])
                r["expected_min"] += extra
                r["cost"] += share * float(M["cost"][i, jo])
                r["extra_clusters"].append(o)
                fields.append({"cluster": k, "courier": r["courier"], "name": r["courier_name"], "extra_min": round(extra)})
            dist_out.append({"cluster": o, "stop": self.clus[jo]["stops"], "fields": fields})
        out_rows = []
        for k in sorted(rows):
            r = rows[k]
            r["over_band"] = r["expected_min"] > self.band[1]
            for f in ("stop", "shipment", "unfamiliar_stop", "memory_unfamiliar"):
                r[f] = int(round(r[f]))
            for f in ("expected_fails",):
                r[f] = round(r[f], 2)
            r["expected_min"], r["cost"] = round(r["expected_min"]), round(r["cost"], 2)
            out_rows.append(r)
        tot_stops = sum(k["stops"] for k in self.clus)
        t = {"courier_count": len(out_rows),
             "expected_fails": round(sum(r["expected_fails"] for r in out_rows), 1),
             "unfamiliar_stop": sum(r["unfamiliar_stop"] for r in out_rows),
             "memory_unfamiliar": sum(r["memory_unfamiliar"] for r in out_rows),
             "over_band_courier": sum(1 for r in out_rows if r["over_band"]),
             "over_band_min": int(round(sum(max(0.0, r["expected_min"] - self.band[1]) for r in out_rows))),
             "expected_min_total": int(sum(r["expected_min"] for r in out_rows)),
             "cost": round(sum(r["cost"] for r in out_rows), 1)}
        return {"assignment": out_rows, "total": t, "own_zone_share": round(1 - t["unfamiliar_stop"] / max(1, tot_stops), 3),
                "distributed_clusters": dist_out, "eta_model": self.eta.info(),
                "dispatch_note": ("Atanamayan küme en yakın kümelere eşit bölündü; ek süre, kuryenin o kümedeki beklenen "
                                 "süresinin payıdır (yaklaşık).") if dist_out else None}

    def score(self, total: dict) -> float:
        """Senaryo karşılaştırma skoru: planlayıcının kendi ağırlıklarıyla beklenen başarısız + bant üstü dakika."""
        a = self.eta.cfg.get("assignment", {})
        wf, wt = float(a.get("w_fail", 1.0)), float(a.get("w_time", 0.05))
        return round(wf * total["expected_fails"] + wt * total["over_band_min"], 2)

    def random_expected(self) -> float:
        """Geçmişe bakmadan (rastgele) atamada beklenen başarısız: küme başına kurye ortalaması."""
        return round(float(self.M["exp_fail"].mean(axis=0).sum()), 1)

    # ---------------------------------------------------------------- araçlar
    def read_volume(self, _: dict | None = None) -> dict:
        sh = int(sum(k["shipments"] for k in self.clus))
        same = [d for d in self.run.eval_days if d % 6 == self.day % 6 and d != self.day]
        ref = [int(sum(k["shipments"] for k in self.run.assign_input(self.arm, d)["clusters"])) for d in same]
        usual = int(median(ref)) if ref else sh
        diff = sh / max(1, usual) - 1
        return {"day": self.day, "weekday": self.run.weekday_name(self.day), "shipment": sh,
                "stop": int(sum(k["stops"] for k in self.clus)), "cluster_count": len(self.kid),
                "planned_min_total": int(sum(k["planned_minutes"] for k in self.clus)),
                "usual_shipments": usual, "usual_days": same, "volume_diff": round(diff, 3),
                "density": "busy" if diff >= BUSY_THRESHOLD else "low" if diff <= -BUSY_THRESHOLD else "usual"}

    def capacity_gap(self, _: dict | None = None) -> dict:
        need, have = len(self.kid), len(self.local)
        mapping, orphans = self._solve(self.local, {})
        ev = self.evaluate(mapping, orphans) if orphans else None
        return {"required_courier_day": need, "local_available": have, "shortfall": max(0, need - have), "extra": max(0, have - need),
                "open_clusters": orphans,
                "on_leave_or_absent": [{"id": u["id"], "name": u["name"], "type": KIND_TR.get(u["kind"], u["kind"])} for u in self.unavailable],
                "neighbor_candidate_count": len(self.neighbors),
                "shortfall_unclosed": None if ev is None else {"over_band_courier": ev["total"]["over_band_courier"],
                                                             "over_band_min": ev["total"]["over_band_min"],
                                                             "expected_fails": ev["total"]["expected_fails"]}}

    def worked_days(self, c: str) -> int:
        """Kuryenin bu şubede (D kolu) daha önce rota aldığı değerlendirme günü sayısı (gözlemlenebilir)."""
        return sum(1 for d in self.run.eval_days if d < self.day and self.run.route_of(d, c, self.arm) is not None)

    def neighbor_candidates(self, inp: dict) -> dict:
        """'Kim gitsin': her aday için yerel kadro (+ zaten plandaki ödünçler) + aday ile plan kurulur; adayın aldığı
        kümede bölge tanıklığı ve hafıza kapsamı, planın toplam beklenen maliyeti raporlanır. Seçim açgözlü: en düşük
        maliyetli aday eklenir, kalanlar onunla yeniden değerlendirilir."""
        need = max(0, int(inp.get("need") or 0))
        excl = set(inp.get("exclude") or [])
        have = [c for c in (inp.get("current_borrowed") or []) if c in self.neighbors and c not in excl]
        base = [c for c in self.local if c not in excl] + have
        pool_c = [c for c in self.neighbors if c not in excl and c not in have]

        def trial(extra: list[str], c: str) -> dict:
            mapping, orphans = self._solve(base + extra + [c], {})
            ev = self.evaluate(mapping, orphans)
            row = next((r for r in ev["assignment"] if r["courier"] == c), None)
            return {"ev": ev, "row": row, "key": round(ev["total"]["cost"], 1), "fail": ev["total"]["expected_fails"]}

        first = {c: trial([], c) for c in pool_c}
        cands = []
        # Eşitlikte (maliyet 0,1'e yuvarlanmış aynı) beklenen başarısızlığı düşük olan önde: kalite önce, kimlik sırası en son.
        for c in sorted(pool_c, key=lambda c: (first[c]["key"], first[c]["fail"], c)):
            t, r = first[c], first[c]["row"]
            unf = r["unfamiliar_stop"] if r else 0
            cands.append({"id": c, "name": self.name(c), "source_branch": NEIGHBOR_BRANCH, "days_worked_in_branch": self.worked_days(c),
                          "target_cluster": r["cluster"] if r else None, "stop": r["stop"] if r else 0, "unfamiliar_stop": unf,
                          "familiar_share": round(1 - unf / max(1, r["stop"]), 3) if r else 0.0,
                          "memory_unfamiliar": r["memory_unfamiliar"] if r else 0,
                          "memory_coverage": round(r["memory_unfamiliar"] / unf, 3) if (r and unf) else (1.0 if r else 0.0),
                          "expected_fails": r["expected_fails"] if r else 0.0, "expected_min": r["expected_min"] if r else 0,
                          "within_band": (not r["over_band"]) if r else True, "plan_cost": t["key"],
                          "plan_expected_fails": t["ev"]["total"]["expected_fails"],
                          "plan_over_band_min": t["ev"]["total"]["over_band_min"]})
        for i, x in enumerate(cands, 1):
            x["order"] = i
        picked: list[str] = []
        left = list(pool_c)
        for _ in range(min(need, len(left))):
            sc = {c: trial(picked, c) for c in left}
            best = min(left, key=lambda c: (sc[c]["key"], sc[c]["fail"], c))
            picked.append(best)
            left.remove(best)
        keys = [x["plan_cost"] for x in cands]
        all_equal = len(cands) > 1 and len(set(keys)) == 1
        tie = all_equal or (0 < need < len(cands) and keys[need - 1] == keys[need])
        if not cands:
            why = "Komşu şubeden bugün aday yok."
        elif all_equal:
            why = ("Adaylar eşit: hiçbirinin bu şubede tanıdığı blok yok, aldıkları kümelerde hafıza kapsamı aynı. Eşitlikte "
                   "komşu şubenin verdiği sıra kullanıldı.")
        else:
            why = ("Sıra: adayla kurulan planın toplam beklenen maliyeti (başarısızlık + süre); bölge tanıklığı ve hafıza "
                   "kapsamı bu maliyete girer.")
            if tie:
                a_, b_ = cands[need - 1], cands[need]
                why += (f" Eşitlik: {a_['name']} ile {b_['name']} aynı plan maliyetinde ({num(a_['plan_cost'], 1)}); beklenen "
                        f"başarısızlığı düşük olan ({a_['name']}: {num(a_['plan_expected_fails'], 1)} ↔ "
                        f"{num(b_['plan_expected_fails'], 1)}) önde.")
        return {"need": need, "candidates": cands, "proposed": picked, "missing": max(0, need - len(picked)),
                "tie": bool(tie), "rationale": why}

    def core_assignment(self, inp: dict) -> dict:
        borrowed = list(dict.fromkeys(inp.get("borrowed") or []))
        excl = list(dict.fromkeys(inp.get("exclude") or []))
        self._check_ids(borrowed, self.neighbors, "Ödünç kurye (komşu şube adayı olmalı)")
        self._check_ids(excl, self.cid, "Hariç tutulan kurye")
        pool = [c for c in self.local if c not in excl] + [c for c in borrowed if c not in excl]
        fixed = {int(f["cluster_id"]): f["courier_id"] for f in (inp.get("pin") or [])}
        mapping, orphans = self._solve(pool, fixed)
        ev = self.evaluate(mapping, orphans)
        used = set(mapping.values())
        self._mapping = dict(mapping)
        ev.update(borrowed=[c for c in borrowed if c not in excl], exclude=excl,
                  idle_couriers=[{"id": c, "name": self.name(c), "type": KIND_TR.get(self.kind(c), "?")} for c in pool if c not in used],
                  history_blind_expected_fails=self.random_expected())
        return ev

    def _plan_addrs(self) -> dict[int, list[int]]:
        snap = self.run.snapshot(self.arm, self.day)
        F = {k: i for i, k in enumerate(snap["stop_fields"])}
        return {int(r["route"]): ([int(a) for a in (r.get("plan") or {}).get("plain_order", [])] or
                                  [int(s[F["address"]]) for s in r["stops"]]) for r in snap["routes"]}

    def delivery_time_analysis(self, inp: dict | None = None) -> dict:
        """Teslim kayıtlarından saat örüntüsü (not gerekmez): bugünkü planın duraklarında 'şu saatte kimse yok' bulguları."""
        if self.time is None or not self.time.enabled:
            return {"day": self.day, "stop": 0, "window_finding": 0, "confirmation_pending": 0, "fits_route": 0, "findings": [],
                    "confirmations": [], "rule_policy": None, "method": "Teslim kaydı yok ya da zaman analizi kapalı."}
        lv = (inp or {}).get("min_confidence") or "low"
        return delivery_time_analysis(self.time, self.day, self._plan_addrs(), self._mapping, lv)

    def apply_time_constraint(self, inp: dict) -> dict:
        """Hangi bulgular rotaya girer: min_confidence ve üstü, exclude dışındaki 'pencere' bulguları (+ kurye teyitli olanlar)."""
        if self.time is None or not self.time.enabled:
            return {"min_confidence": None, "exclude": [], "applied": 0, "cluster_count": 0}
        select = self.time.make_selection(self.day, inp.get("min_confidence"), inp.get("exclude") or [])
        pa = self._plan_addrs()
        per = {k: len(self.time.route(self.day, addrs)) for k, addrs in pa.items()}
        return {**select, "applied": sum(per.values()), "cluster_count": sum(1 for v in per.values() if v),
                "rationale": inp.get("rationale") or ""}

    def time_alternatives(self, inp: dict | None = None) -> dict:
        """Kısıt (rota uzamaz, bant aşılmaz, vardiya sonrasına kaydırma yok) yüzünden aynı rotada kaydırılamayan bulgular için
        sırayla alternatif: başka kuryeye aktarma (iki rotada kısıt) → ertesi gün uygun dilim / akşam-teslim noktası; hepsinde
        alıcıya önceden SMS önerisi. Hesap simülatörle aynı (`time_alternatives`); karar müdürde."""
        if self.time is None or not self.time.enabled or self.planner.limits is None:
            self._zalt = []
            return {"day": self.day, "unshiftable": 0, "transfer": 0, "next_day": 0, "evening_delivery_point": 0, "proposals": [],
                    "constraint": None}
        rows = self.planner.day_alternatives(self.day, self._mapping)
        self._zalt = rows
        L = self.planner.limits
        n = {k: sum(1 for r in rows if r["option"] == k) for k in ("transfer", "next_day", "evening_delivery_point")}
        return {"day": self.day, "unshiftable": len(rows), **n, "proposals": rows[:LIST_ALT],
                "constraint": {"tolerance_min": L.max_extra_min, "tolerance_km": L.max_extra_km, "band_min": L.band_max,
                          "shift_end": hhmm(self.planner.shift_end())},
                "rule": ("Onarım rota süresini (sürüş + servis + bilinen öğle beklemesi) artıramaz, bandı aşamaz, durağı vardiya "
                          "bitişinden sonraya koyamaz. Aktarmada kısıt iki rotada birlikte geçerli. Öneriler şube panelinde öneri olarak durur; plan beklemez, kendiliğinden uygulanmaz.")}

    def sorting_plan(self, inp: dict | None = None) -> dict:
        """Ayrıştırma indirme okutmasında. Onaylanacak atama + hafızalı rota sırasından raf planı: her kurye bir raf;
        gönderi okutulunca "kurye · raf · yükleme sırası" (son durak önce yüklenir). Plan araç gelmeden hazır olduğu için kurye
        ayrıştırma yapmaz, rafını zimmetler. Bugün kapalı bilinen (planda ertelenen) duraklar ertesi gün rafına. Çıkış: mesai
        başı + sabah süresi (bugünkü süreç / ayrıştırmasız; şube beyanı). Hesap deterministik, paket başına LLM yok."""
        sb = self.morning
        snap = self.run.snapshot(self.arm, self.day)
        F = {k: i for i, k in enumerate(snap["stop_fields"])}
        lab = self.run.addr_label
        shelves, ertesi = [], 0
        for i, r in enumerate(sorted(snap["routes"], key=lambda q: int(q["route"]))):
            k = int(r["route"])
            c = self._mapping.get(k) or r["courier"]
            st = r["stops"]
            ertesi += sum(int(d.get("n", 0)) for d in ((r.get("plan") or {}).get("deferred") or []))
            shelves.append({"shelf": i + 1, "cluster": k, "courier": c, "name": self.name(c), "stop": len(st),
                           "shipment": int(sum(s[F["n"]] for s in st)),
                           "first_loaded": lab[int(st[-1][F["address"]])] if st else None,
                           "last_loaded": lab[int(st[0][F["address"]])] if st else None})
        m = sb["shift_start"]
        out = {"day": self.day, "enabled": sb["enabled"], "shelf_count": len(shelves), "shipment": sum(x["shipment"] for x in shelves),
               "next_day_shelf": ertesi, "shelves": shelves,
               "departure": {"shift_start": hhmm(m), "today": hhmm(m + sb["current_min"]), "presorted": hhmm(m + sb["presorted_min"]),
                         "gain_min": int(round(sb["current_min"] - sb["presorted_min"]))},
               "rule": ("Gönderi indirme okutmasında kuryesinin rafına, rota sırasının tersiyle (son durak önce) yüklenecek şekilde gider; "
                         "kurye ayrıştırma yapmaz, rafını zimmetleyip yükler. Planda olmayan ya da adresi çözülemeyen gönderi 'esnek' "
                         "rafına gider ve müdür ekranına düşer; bugün kapalı bilinen durakların gönderileri ertesi gün rafına."),
               "source": "Sabah süreleri şube beyanıdır; büyüklüğü pilot ölçer."}
        self._sort = out
        return out

    def morning_summary(self) -> dict | None:
        if self._sort is None:
            return None
        a = self._sort
        return {"shelf_count": a["shelf_count"], "shipment": a["shipment"], "next_day_shelf": a["next_day_shelf"], "departure": a["departure"],
                "shelves": [{k: x[k] for k in ("shelf", "cluster", "courier", "name", "shipment")} for x in a["shelves"]]}

    def time_alt_summary(self) -> list[dict] | None:
        if self._zalt is None:
            return None
        keep = ("address", "label", "courier", "courier_name", "option", "reason", "target_courier", "target_courier_name", "text", "sms_text")
        return [{k: r.get(k) for k in keep} for r in self._zalt[:LIST_ALT]]

    def time_summary(self) -> dict | None:
        if self.time is None or not self.time.enabled:
            return None
        select = self.time._selection(self.day)
        return {**select, "applied": sum(len(self.time.route(self.day, a)) for a in self._plan_addrs().values())}

    def compute_route(self, inp: dict) -> dict:
        k, c = int(inp["cluster_id"]), inp["courier_id"]
        self.ki(k)
        exp = self.eta.predict(self.clus[self.ki(k)], self.M["exp_min"][self.ci(c), self.ki(k)])
        mem = (lambda a: len(self.book.for_address(a, self.day))) if self.book is not None else None
        return self.planner.plan(self.day, k, c, exp, mem)

    def evaluate_plan(self, borrowed: list[str], assignment: list[dict]) -> dict:
        """Elle verilen (müdür düzenlemesi) atamayı doğrular ve aynı ölçülerle değerlendirir."""
        self._check_ids(borrowed, self.neighbors, "Ödünç kurye")
        pool = self.local + [c for c in borrowed if c not in self.local]
        mapping = {}
        for a in assignment:
            k, c = int(a["cluster_id"]), a["courier_id"]
            self.ki(k)
            if c not in pool:
                raise ValueError(f"Kurye havuzda değil: {c}")
            if k in mapping:
                raise ValueError(f"Küme iki kez atanmış: {k}")
            mapping[k] = c
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("Aynı kurye birden fazla kümeye atanmış")
        ev = self.evaluate(mapping, sorted(k for k in self.kid if k not in mapping))
        used = set(mapping.values())
        ev.update(borrowed=[c for c in borrowed if c in used], exclude=[],
                  idle_couriers=[{"id": c, "name": self.name(c), "type": KIND_TR.get(self.kind(c), "?")} for c in pool if c not in used],
                  history_blind_expected_fails=self.random_expected())
        return ev

    def resolve_couriers(self, text: str) -> list[str]:
        t = tr_lower(text)
        found: list[tuple[int, str]] = []
        for c in self.run.couriers.values():
            for token in (tr_lower(c["id"]), tr_lower(c["name"])):
                m = re.search(r"\b" + re.escape(token), t)
                if m:
                    found.append((m.start(), c["id"]))
                    break
        found.sort()
        return list(dict.fromkeys(c for _, c in found))


def diff(a: dict, b: dict) -> dict:
    """b − a (plan karşılaştırması)."""
    ta, tb = a["total"], b["total"]
    ma = {r["cluster"]: r["courier"] for r in a["assignment"]}
    mb = {r["cluster"]: r["courier"] for r in b["assignment"]}
    return {"expected_fails": round(tb["expected_fails"] - ta["expected_fails"], 1),
            "over_band_min": tb["over_band_min"] - ta["over_band_min"],
            "over_band_courier": tb["over_band_courier"] - ta["over_band_courier"],
            "unfamiliar_stop": tb["unfamiliar_stop"] - ta["unfamiliar_stop"],
            "memory_unfamiliar": tb["memory_unfamiliar"] - ta["memory_unfamiliar"],
            "courier_count": tb["courier_count"] - ta["courier_count"],
            "changed_clusters": sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k))}


# ====================================================================== ajan
SUMMARY = {
    "read_volume": lambda i, r: f"{r['shipment']} gönderi, olağan {r['weekday']} {r['usual_shipments']} → {percent(r['volume_diff'], True)} ({DENSITY_TR.get(r['density'], r['density'])})",
    "capacity_gap": lambda i, r: f"{r['required_courier_day']} kurye-gün gerekli, yerelde {r['local_available']} müsait → açık {r['shortfall']}",
    "neighbor_candidates": lambda i, r: f"{len(r['candidates'])} aday; önerilen: {', '.join(r['proposed']) or 'yok'}" + (" (eşitlik)" if r["tie"] else ""),
    "core_assignment": lambda i, r: (f"{r['total']['courier_count']} kurye, beklenen başarısız {num(r['total']['expected_fails'])}, "
                                    f"kendi bölgesinde {percent(r['own_zone_share'])}, bant üstü {r['total']['over_band_min']} dk"),
    "compute_route": lambda i, r: (f"küme {r['cluster']} · {r['name']}: {r['stop']} durak, {r['km']} km, beklenen {int(r['expected_min'])} dk, "
                                  f"dönüş {r['estimated_return']}" + _route_summary(r)),
    "delivery_time_analysis": lambda i, r: (f"{r['stop']} durakta {r['window_finding']} saat örüntüsü (önerilen saati kanıtlı), "
                                           f"{r['confirmation_pending']} teyit bekleyen"),
    "apply_time_constraint": lambda i, r: (f"güven ≥ {LEVEL_TR.get(r['min_confidence'], r['min_confidence'])}: {r['applied']} bulgu {r['cluster_count']} rotaya alındı"
                                         + (f", {len(r['exclude'])} adres hariç" if r.get("exclude") else "")),
    "time_alternatives": lambda i, r: (f"kısıt yüzünden kaydırılamayan {r['unshiftable']} bulgu: {r['transfer']} aktarma, "
                                          f"{r['next_day']} ertesi gün, {r['evening_delivery_point']} akşam/teslim noktası önerisi (+SMS; öneri, uygulanmadı)"),
    "sorting_plan": lambda i, r: (f"{r['shelf_count']} raf, {r['shipment']} gönderi okutmada rafına (yükleme sırası rota tersi); "
                                      f"çıkış {r['departure']['today']} → {r['departure']['presorted']} (−{r['departure']['gain_min']} dk)"),
}
LIST_ALT = 10


def _route_summary(r: dict) -> str:
    f = (r.get("comparison") or {}).get("diff")
    if not f:
        return ""
    parts = []
    if f["carried"]:
        parts.append(f"{f['carried']} durak öğle arasından kaçırıldı")
    if f.get("time_carried"):
        parts.append(f"{f['time_carried']} durak kimsenin bulunmadığı saatten kaydırıldı")
    if f["deferred"]:
        parts.append(f"{f['deferred']} kapalı durak plandan çıktı")
    return (" · hafıza: " + ", ".join(parts) + f" ({f['km']:+.1f} km)") if parts else " · hafıza rotayı değiştirmedi"


class Orchestrator:
    def __init__(self, run: RunData, book: MemoryBook, llm: LLM, planner: RoutePlanner | None = None):
        self.run, self.book, self.llm = run, book, llm
        self.planner = planner or RoutePlanner(run, MemoryConstraints(book, run))

    def tools(self, day: int) -> DayTools:
        return DayTools(self.run, self.book, day, planner=self.planner)

    # ---------------------------------------------------------------- araç listesi (iz'e yazan sarmalayıcılarla)
    def _tools(self, ar: DayTools, trace: Trace, finish: str) -> tuple[list[Tool], dict]:
        def wrap(name, fn):
            def f(inp):
                inp = dict(inp or {})
                trace.emit("tool", tool=name, input=inp)
                try:
                    res = fn(inp)
                except Exception as e:
                    trace.emit("error", tool=name, text=str(e))
                    raise
                trace.emit("result", tool=name, summary=SUMMARY[name](inp, res), data=res)
                return res
            return f

        specs = [
            ("read_volume", "Günün gönderi/durak/küme hacmi ve olağan aynı haftagününe göre farkı (yoğunluk).", obj({}), ar.read_volume),
            ("capacity_gap", "Gereken kurye-gün (küme sayısı) ile yerel müsait kurye farkı; açık kapanmazsa bant üstü süre.",
             obj({}), ar.capacity_gap),
            ("neighbor_candidates", "Komşu şubeden gelebilecek kuryeleri sıralar ('kim gitsin'): bölge tanıklığı, hafıza kapsamı, "
                               "beklenen başarısızlık ve süre. ihtiyac: kaç kurye; exclude: bugün olmayan kuryeler (aday da sayılmaz); current_borrowed: zaten plandaki ödünç kuryeler.",
             obj({"need": {"type": "integer"}, "exclude": {"type": "array", "items": {"type": "string"}},
                  "current_borrowed": {"type": "array", "items": {"type": "string"}}}), ar.neighbor_candidates),
            ("core_assignment", "Çekirdek bölgeli atamayı çözer (Hungarian). odunc: plana katılacak komşu şube kuryeleri; "
                               "exclude: bugün atanmayacak kuryeler; sabitle: zorunlu küme→kurye. Kurye azsa kalan kümeleri "
                               "en yakın kümelere dağıtır ve bant üstü süreyi raporlar.",
             PLAN_CHANGE, ar.core_assignment),
            ("delivery_time_analysis", "Teslim kayıtlarından (not gerekmez, yalnız geçmiş günler) saat örüntüsü: aynı adreste bir saat "
                                      "diliminde 'alıcı yok' tekrarlıyor ve başka dilimde teslim edilmişse bulgu (güven dusuk|orta|yuksek, "
                                      "önerilen dilim). Başka saatte kaydı olmayanlar 'teyitler' listesinde (hasatta sorulur).",
             obj({"min_confidence": CONFIDENCE}), ar.delivery_time_analysis),
            ("apply_time_constraint", "Hangi teslim zamanı bulgularının rotaya gireceğine karar verir: min_confidence ve üstü bulgular "
                                    "(exclude adresleri dışında) compute_route'da bulunma olasılığı yüksek saate kaydırılır. Kurye "
                                    "teyitli bulgu her zaman, reddedilen hiç girmez. gerekce: bir cümle.",
             obj({"min_confidence": CONFIDENCE, "exclude": {"type": "array", "items": {"type": "integer"}}, "rationale": {"type": "string"}}),
             ar.apply_time_constraint),
            ("time_alternatives", "apply_time_constraint'dan sonra: sert kısıt (rota süresi artmaz, vardiya bandı aşılmaz, durak vardiya "
                                     "bitişinden sonraya kaymaz) yüzünden aynı rotada kaydırılamayan bulgular ve her biri için sırayla "
                                     "alternatif: başka kuryeye aktarma (kısıt iki rotada) → ertesi gün uygun dilim / akşam-teslim noktası; "
                                     "hepsinde alıcıya SMS önerisi. Öneriler şube panelinde öneri olarak durur; plan beklemez, kendiliğinden uygulanmaz.",
             obj({}), ar.time_alternatives),
            ("compute_route", "Bir küme–kurye rotası: durak, km, kuryeye özgü beklenen süre, tahmini dönüş, hafızalı durak, kısıtlar, "
                             "hafıza ve teslim zamanı değişiklikleri.",
             obj({"cluster_id": {"type": "integer"}, "courier_id": {"type": "string"}}), ar.compute_route),
            ("sorting_plan", "Atamadan sonra: indirme okutmasında ayrıştırma planı. Her kurye bir raf; gönderi okutulunca kuryesinin "
                                 "rafına ve yükleme sırasına (rota tersi) gider, kurye ayrıştırma yapmaz. Raf sayısı, gönderi, ertesi gün "
                                 "rafı ve tahmini çıkış (bugünkü süreç ↔ ayrıştırmasız) döner.",
             obj({}), ar.sorting_plan),
        ]
        fns = {n: wrap(n, fn) for n, _, _, fn in specs}
        tools = [Tool(n, d, s, fns[n], lambda i, r, n=n: SUMMARY[n](i, r)) for n, d, s, _ in specs]
        if finish == FINISH_PLAN:
            tools.append(Tool(FINISH_PLAN, "Günün planını sunar (son adım); acil durum yoksa plan temassız kesinleşir, varsa kod müdüre eskale eder. Plan, verilen odunc/exclude/sabitle ile "
                                           "core_assignment'dan yeniden hesaplanır; sayı yazma, gerekçe ve riskleri yaz.",
                              obj({"borrowed": {"type": "array", "items": {"type": "string"}},
                                   "exclude": {"type": "array", "items": {"type": "string"}},
                                   "pin": {"type": "array", "items": ASSIGNMENT_ITEM},
                                   "rationale": {"type": "array", "items": {"type": "string"}},
                                   "risks": {"type": "array", "items": {"type": "string"}},
                                   "questions": {"type": "array", "items": {"type": "string"}}})))
        else:
            tools.append(Tool(ASK_FINISH, "Müdürün senaryo sorusunu cevaplar (son adım). Önerdiğin plan değişikliği varsa "
                                          "plan_change'ni doldur, yoksa null.",
                              obj({"response": {"type": "string"}, "plan_change": nullable(PLAN_CHANGE)})))
        return tools, fns

    # ---------------------------------------------------------------- öneri
    def plan(self, day: int, trace: Trace | None = None, manager_review: bool = False) -> dict:
        """Günü planlar. Acil durum yoksa plan temassız kesinleşir (`auto_decision`); varsa müdüre eskale edilir
        (`escalation` + `awaiting_approval`). manager_review: müdür acil durum bildirdi (sistemin göremediği durum)."""
        trace = Trace() if trace is None else trace
        ar = self.tools(day)
        trace.source = "llm" if self.llm.uses_llm else "rule"
        trace.emit("start", day=day, mod=self.llm.mode, task="plan")
        tools, fns = self._tools(ar, trace, FINISH_PLAN)
        degraded, error = False, None
        if self.llm.uses_llm:
            try:
                run = self.llm.run_agent(agent="orchestrator", system=PROMPT, tools=tools, finish_tool=FINISH_PLAN, effort="medium",
                                         max_turns=14, on_text=lambda t: trace.emit("decision", text=t),
                                         user=f"Gün {day} ({self.run.weekday_name(day)}) için şubenin gününü planla ve müdüre öner.")
                if not run.final_input:
                    raise AgentError("Ajan öneriyi sunmadı")
                fi = run.final_input
                trace.emit("tool", tool=FINISH_PLAN, input=fi)
                proposal = self._proposal(ar, fi)
            except Exception as e:
                degraded, error = True, str(e)
                trace.source = "rule"
                trace.emit("fallback", text=f"Canlı ajan tamamlanamadı ({e}); kurallı yedek aynı araçlarla devam ediyor.")
                proposal = self._plan_rule(ar, trace, fns)
        else:
            proposal = self._plan_rule(ar, trace, fns)
        trace.emit("proposal", proposal=proposal)
        reasons = self.escalation(ar, proposal, manager_review)
        if reasons:
            trace.emit("escalation", source="rule", reasons=reasons)
            trace.emit("awaiting_approval")
            status = "awaiting_approval"
        else:
            trace.emit("auto_decision", source="rule", decision="approval",
                       text="Acil durum yok: kapasite açığı kapandı, fazla mesai eşiğin altında, plan geçmişe bakmayan atamadan iyi. "
                            "Plan müdüre gitmeden kesinleşti.")
            trace.emit("done", source="rule", status="finalized")
            status = "finalized"
        out = {"day": day, "mode": self.llm.mode, "degraded": degraded, "status": status, "proposal": proposal,
               "escalation": reasons, "trace": trace.events}
        if error:
            out["error"] = error
        return out

    def escalation(self, ar: DayTools, proposal: dict, manager_review: bool = False) -> list[dict]:
        """Müdürü yalnız acil durumda çağıran deterministik eşikler. Boş liste → zincir temassız devam eder."""
        reasons = []
        if manager_review:
            reasons.append({"code": "manual", "text": "Müdür acil durum bildirdi; plan onayına sunuluyor."})
        gap = ar.capacity_gap()
        borrowed = len(proposal.get("borrowed") or [])
        unclosed = gap["shortfall"] - borrowed
        dist = proposal.get("distributed_clusters") or []
        if unclosed > 0 or dist:
            reasons.append({"code": "capacity", "text": f"Kapasite açığı kapanmıyor: {gap['shortfall']} kurye-gün açık, komşu şubeden "
                            f"{borrowed} kurye geliyor" + (f"; {len(dist)} küme komşu rotalara dağıtıldı" if dist else "") + "."})
        band = ar.band[1]
        heavy = sorted(((r["expected_min"] - band, r.get("courier_name") or r["courier"]) for r in proposal.get("assignment") or []
                        if r["expected_min"] - band >= ESCALATE_COURIER_OVER_MIN), reverse=True)
        total_over = (proposal.get("total") or {}).get("over_band_min", 0)
        if heavy or total_over >= ESCALATE_TOTAL_OVER_MIN:
            who = ", ".join(f"{n} +{round(m)} dk" for m, n in heavy[:3])
            reasons.append({"code": "overtime", "text": f"Ciddi fazla mesai: toplam bant üstü {total_over} dk (eşik {ESCALATE_TOTAL_OVER_MIN})"
                            + (f"; {len(heavy)} kuryede {ESCALATE_COURIER_OVER_MIN} dk üstü ({who})" if heavy else "") + "."})
        blind = (proposal.get("comparison") or {}).get("history_blind_expected_fails")
        fails = (proposal.get("total") or {}).get("expected_fails")
        if blind is not None and fails is not None and fails > blind:
            reasons.append({"code": "plan_worse", "text": f"Plan geçmişe bakmayan atamadan kötü: beklenen başarısız {num(fails)} > {num(blind)}."})
        return reasons

    def _proposal(self, ar: DayTools, fi: dict) -> dict:
        ev = ar.core_assignment({"borrowed": fi.get("borrowed") or [], "exclude": fi.get("exclude") or [], "pin": fi.get("pin") or []})
        return {"day": ar.day, "weekday": self.run.weekday_name(ar.day),
                "borrowed": [{"id": c, "name": ar.name(c), "source_branch": NEIGHBOR_BRANCH} for c in ev["borrowed"]],
                "exclude": ev["exclude"], "assignment": ev["assignment"], "total": ev["total"],
                "own_zone_share": ev["own_zone_share"], "distributed_clusters": ev["distributed_clusters"],
                "dispatch_note": ev["dispatch_note"], "eta_model": ev["eta_model"], "idle_couriers": ev["idle_couriers"],
                "comparison": {"history_blind_expected_fails": ev["history_blind_expected_fails"]},
                "time_constraints": ar.time_summary(), "time_alternatives": ar.time_alt_summary(), "morning": ar.morning_summary(),
                "rationale": list(fi.get("rationale") or []), "risks": list(fi.get("risks") or []),
                "questions": list(fi.get("questions") or [])}

    def _plan_rule(self, ar: DayTools, trace: Trace, T: dict) -> dict:
        """Kurallı yedek: istemdeki sırayla aynı araçlar, aynı iz biçimi."""
        trace.emit("decision", text="Günün hacmine ve kadroya bakıyorum.")
        h = T["read_volume"]({})
        wd = h["weekday"]
        if h["density"] == "busy":
            trace.emit("decision", text=f"Hacim olağan {wd} gününe göre {percent(h['volume_diff'], True)}: yoğun gün. Kapasiteyi kontrol ediyorum.")
        else:
            trace.emit("decision", text=f"Hacim olağan {wd} gününe yakın ({percent(h['volume_diff'], True)}). Kapasiteyi kontrol ediyorum.")
        k = T["capacity_gap"]({})
        borrowed: list[str] = []
        cand = None
        if k["shortfall"] > 0 and k["neighbor_candidate_count"] > 0:
            trace.emit("decision", text=f"{k['required_courier_day']} kurye-gün gerekiyor, yerelde {k['local_available']} müsait: {k['shortfall']} açık. "
                                   f"Komşu şubeden kimin gelmesi gerektiğini sıralatıyorum.")
            cand = T["neighbor_candidates"]({"need": k["shortfall"], "exclude": [], "current_borrowed": []})
            borrowed = cand["proposed"]
            names = " ve ".join(ar.name(c) for c in borrowed)
            trace.emit("decision", text=f"Açık kadar, {len(borrowed)} kurye istiyorum: {names}. {cand['rationale']} "
                                   f"Şimdi çekirdek bölgeli atamayı çözüyorum.")
        elif k["shortfall"] > 0:
            trace.emit("decision", text=f"{k['shortfall']} kurye-gün açık ama komşu şubeden aday yok; açık kümeler en yakın kümelere "
                                   f"dağıtılacak. Atamayı çözüyorum.")
        else:
            trace.emit("decision", text=f"Açık yok ({k['extra']} yerel kurye yedekte); komşu şubeden destek istemiyorum. "
                                   f"Çekirdek bölgeli atamayı çözüyorum.")
        a = T["core_assignment"]({"borrowed": borrowed, "exclude": [], "pin": []})
        z = None
        if ar.time is not None and ar.time.enabled:
            trace.emit("decision", text="Teslim kayıtlarında saat örüntüsü arıyorum: bir adreste belli saatte hep kimse bulunmuyorsa durağı "
                                   "o saatten kaydırmak tekrar ziyareti önler.")
            z = T["delivery_time_analysis"]({"min_confidence": "low"})
            lv = z["rule_policy"]
            if z["window_finding"]:
                trace.emit("decision", text=f"{z['window_finding']} adreste örüntü var; güveni '{LEVEL_TR.get(lv, lv)}' ve üstü olanları rotaya alıyorum "
                                       f"(önerilen saatte adresin kendi teslim kaydı var). {z['confirmation_pending']} adreste yalnız kötü saat "
                                       f"belli; onları hasatta kuryeye soracağız.")
                T["apply_time_constraint"]({"min_confidence": lv, "exclude": [],
                                          "rationale": f"Kurallı politika: güven ≥ {LEVEL_TR.get(lv, lv)}, önerilen saati kanıtlı bulgular."})
                trace.emit("decision", text="Kural: kaydırma rotayı uzatamaz, vardiya bandını aşamaz, durağı mesai sonrasına koyamaz. Bu "
                                       "yüzden aynı rotada kaydırılamayan bulgular için başka kurye ya da ertesi gün + SMS seçeneğine bakıyorum.")
                za = T["time_alternatives"]({})
                if za["unshiftable"]:
                    trace.emit("decision", text=f"{za['unshiftable']} bulgu kısıt yüzünden aynı rotada kaydırılamadı: {za['transfer']} tanesini "
                                           f"o saatte bölgeden geçen başka kuryeye aktarmayı (iki rota da uzamadan), "
                                           f"{za['next_day'] + za['evening_delivery_point']} tanesi için alıcıya SMS ile ertesi gün / "
                                           f"teslim noktası seçeneğini öneriyorum. Bunlar şube panelinde öneri olarak durur; plan beklemez.")
                else:
                    trace.emit("decision", text="Kısıt yüzünden kaydırılamayan bulgu yok.")
            else:
                trace.emit("decision", text="Bugünkü duraklarda güvenilir saat örüntüsü yok; rotalar saat için değişmeyecek.")
        risky = sorted((r for r in a["assignment"] if r["courier_type"] in ("borrowed", "new")), key=lambda r: (-r["unfamiliar_stop"], r["cluster"]))[:3]
        routes = []
        if risky:
            trace.emit("decision", text="Bölgeye yabancı kuryelerin rotalarını ve beklenen sürelerini kontrol ediyorum.")
            for r in risky:
                routes.append(T["compute_route"]({"cluster_id": r["cluster"], "courier_id": r["courier"]}))
        ay = None
        if ar.morning["enabled"]:
            trace.emit("decision", text="Plan araç gelmeden hazır. İndirme okutmasında her gönderiyi kuryesinin rafına ve yükleme sırasına "
                                   "yönlendiriyorum; kuryeler ayrıştırma yapmayacak, yalnız rafını zimmetleyip yükleyecek.")
            ay = T["sorting_plan"]({})
        rationale, risks, questions = self._template(ar, h, k, cand, a, routes)
        if ay is not None:
            rationale.append(f"Ayrıştırma indirme okutmasında: {ay['shelf_count']} raf, yükleme sırası rotanın tersi. Tahmini çıkış "
                           f"{ay['departure']['presorted']} (bugünkü süreçte {ay['departure']['today']}).")
        zo = ar.time_summary()
        if z is not None and zo and zo["applied"]:
            time_moved = sum((r.get("comparison") or {}).get("diff", {}).get("time_carried", 0) for r in routes)
            rationale.append(f"Teslim kayıtlarına göre {zo['applied']} durakta 'şu saatte kimse yok' örüntüsü rotaya girdi"
                           + (f"; kontrol ettiğim rotalarda {time_moved} durak kaydırıldı." if time_moved else ".")
                           + " Kaydırma rotayı uzatmaz, fazla mesai yaratmaz.")
            alts = ar._zalt or []
            if alts:
                risks.append(f"{len(alts)} durak kısıt yüzünden aynı rotada kaydırılamadı; alternatif öneriler (aktarma / ertesi gün + SMS) "
                               f"şube panelinde öneri olarak duruyor (plan beklemez): " + "; ".join(f"{r['label']} → {OPTION_NAME[r['option']]}" for r in alts[:3])
                               + (" …" if len(alts) > 3 else "") + ".")
        trace.emit("decision", text="Planı gerekçesiyle sunuyorum. Acil durum kapısı denetleyecek: acil durum yoksa plan müdüre gitmeden kesinleşir.")
        fi = {"borrowed": borrowed, "exclude": [], "pin": [], "rationale": rationale, "risks": risks, "questions": questions}
        trace.emit("tool", tool=FINISH_PLAN, input=fi)
        return self._proposal(ar, fi)

    def _template(self, ar: DayTools, h: dict, k: dict, cand: dict | None, a: dict, routes: list[dict]):
        t = a["total"]
        g = [f"Hacim {h['shipment']} gönderi; olağan {h['weekday']} gününe göre {percent(h['volume_diff'], True)}. "
             f"{k['required_courier_day']} kurye-gün gerekiyor, yerelde {k['local_available']} kurye müsait."]
        if cand and cand["proposed"]:
            g.append(f"Komşu şubeden {len(cand['proposed'])} kurye öneriyorum ({', '.join(ar.name(c) for c in cand['proposed'])}); "
                     f"açık kadar, fazlası değil. {cand['rationale']}")
        elif k["shortfall"] > 0:
            g.append(f"{k['shortfall']} kurye-gün açık kapanmıyor; {len(a['distributed_clusters'])} küme komşu kümelere dağıtıldı.")
        g.append(f"Kendi çekirdek bölgesinde kalınan durak payı {percent(a['own_zone_share'])}. Kuryeler kaydırılmıyor; "
                 f"esnek kuşak destek kuryelerine gidiyor.")
        g.append(f"Beklenen başarısız teslim {num(t['expected_fails'])}; kuryeler geçmişe bakmadan atansaydı "
                 f"{num(a['history_blind_expected_fails'])}.")
        if t["unfamiliar_stop"]:
            g.append(f"Bölgeye yabancı {t['unfamiliar_stop']} durağın {t['memory_unfamiliar']} tanesinde hafıza notu var; kapıda ipucu verilecek.")
        risks = []
        over = sorted((r for r in a["assignment"] if r["over_band"]), key=lambda r: (-r["expected_min"], r["cluster"]))
        if over:
            risks.append(f"{len(over)} kuryenin beklenen süresi vardiya bandının ({int(self.run.meta['band'][1])} dk) üstünde, "
                           f"toplam {t['over_band_min']} dk: " + ", ".join(f"{r['courier_name']} {r['expected_min']} dk" for r in over[:3])
                           + (" …" if len(over) > 3 else "") + ".")
        for r in a["assignment"]:
            if r["source"] == "neighbor" and r["over_band"]:
                risks.append(f"Ödünç kurye {r['courier_name']} (küme {r['cluster']}) bandı aşıyor: {r['expected_min']} dk; "
                               f"yükü hafifletmek için müdür düzenlemesi düşünülebilir.")
        for d in a["distributed_clusters"]:
            risks.append(f"Küme {d['cluster']} ({d['stop']} durak) atanamadı; " +
                           ", ".join(f"{x['name']} +{x['extra_min']} dk" for x in d["fields"]) + ".")
        if a["idle_couriers"]:
            risks.append(f"{len(a['idle_couriers'])} kurye yedekte bekliyor: " + ", ".join(x["name"] for x in a["idle_couriers"][:4]) + ".")
        questions = []
        for c in (cand["proposed"] if cand else [])[:2]:
            questions.append(f"{ar.name(c)} gelmezse ne olur?")
        if not questions:
            new = [r for r in a["assignment"] if r["courier_type"] in ("new", "reserve")]
            if new:
                questions.append(f"{new[0]['courier_name']} gelmezse ne olur?")
        return g, risks, questions

    # ---------------------------------------------------------------- senaryo sorusu
    def ask(self, day: int, question: str, proposal: dict, trace: Trace | None = None, history: list[dict] | None = None) -> dict:
        trace = Trace() if trace is None else trace
        start = len(trace)
        ar = self.tools(day)
        base_in = {"borrowed": [x["id"] for x in proposal["borrowed"]], "exclude": list(proposal.get("exclude") or []), "pin": []}
        trace.source = "llm" if self.llm.uses_llm else "rule"
        trace.emit("start", day=day, mod=self.llm.mode, task="ask", question=question)
        tools, fns = self._tools(ar, trace, ASK_FINISH)
        degraded, error = False, None
        if self.llm.uses_llm:
            try:
                hist = [{"role": "user" if h.get("role") == "manager" else "assistant", "content": str(h.get("text", ""))}
                        for h in (history or [])]
                if hist and hist[0]["role"] != "user":
                    hist.insert(0, {"role": "user", "content": "(önceki konuşma)"})
                cur = ", ".join(f"küme {r['cluster']}→{r['courier']}" for r in proposal["assignment"])
                run = self.llm.run_agent(agent="ask_orchestrator", system=PROMPT, tools=tools, finish_tool=ASK_FINISH, history=hist,
                                         effort="medium", max_turns=10, on_text=lambda t: trace.emit("decision", text=t),
                                         user=(f"Gün {day}. Onay bekleyen öneri: ödünç {base_in['borrowed'] or 'yok'}, hariç "
                                               f"{base_in['exclude'] or 'yok'}; atama: {cur}.\nŞube müdürünün sorusu: {question}"))
                fi = run.final_input or {}
                if "response" not in fi:
                    raise AgentError("Ajan yanıtlamadı")
                trace.emit("tool", tool=ASK_FINISH, input=fi)
                pd = fi.get("plan_change")
                revised = self._proposal(ar, {**pd, "rationale": proposal["rationale"], "risks": [], "questions": []}) if pd else None
                res = {"response": fi["response"], "new_proposal": revised, "diff": diff(proposal, revised) if revised else None, "alternatives": []}
            except Exception as e:
                degraded, error = True, str(e)
                trace.source = "rule"
                trace.emit("fallback", text=f"Canlı ajan tamamlanamadı ({e}); kurallı yedek aynı araçlarla cevaplıyor.")
                res = self._ask_rule(ar, trace, fns, question, proposal, base_in)
        else:
            res = self._ask_rule(ar, trace, fns, question, proposal, base_in)
        trace.emit("response", response=res["response"], diff=res["diff"])
        res.update(day=day, mode=self.llm.mode, degraded=degraded, trace=trace.since(start))
        if error:
            res["error"] = error
        return res

    def _ask_rule(self, ar: DayTools, trace: Trace, T: dict, question: str, proposal: dict, base: dict) -> dict:
        q = tr_lower(question)
        names = ar.resolve_couriers(question)
        plan_c = {r["courier"] for r in proposal["assignment"]}
        if not names:
            trace.emit("decision", text="Soruda kurye adı yok; günün kapasitesini özetliyorum.")
            k = T["capacity_gap"]({})
            txt = (f"Bugün {k['required_courier_day']} kurye-gün gerekiyor, yerelde {k['local_available']} kurye var; komşu şubeden "
                   f"{len(base['borrowed'])} kurye öneride. Bir kuryenin adını vererek sorabilirsiniz: \"Onur gelmezse ne olur?\".")
            return self._ask_finish(trace, txt, None, proposal, [])
        if len(names) >= 2 and "yerine" in q:
            a_, b_ = names[0], names[1]
            borrowed = [c for c in base["borrowed"] if c != a_]
            if b_ in ar.neighbors and b_ not in borrowed:
                borrowed.append(b_)
            k_a = next((r["cluster"] for r in proposal["assignment"] if r["courier"] == a_), None)
            trace.emit("decision", text=f"{ar.name(a_)} yerine {ar.name(b_)}: planı bu değişiklikle yeniden çözüyorum.")
            pd = {"borrowed": borrowed, "exclude": sorted(set(base["exclude"]) | {a_}),
                  "pin": [{"cluster_id": k_a, "courier_id": b_}] if k_a is not None else []}
            r = T["core_assignment"](pd)
            revised = self._as_proposal(ar, r, proposal)
            f = diff(proposal, revised)
            txt = (f"{ar.name(a_)} yerine {ar.name(b_)} giderse beklenen başarısız teslim {num(proposal['total']['expected_fails'])} → "
                   f"{num(revised['total']['expected_fails'])} ({num(f['expected_fails'], sign=True)}); bant üstü süre "
                   f"{proposal['total']['over_band_min']} → {revised['total']['over_band_min']} dk. Onaylarsanız planı güncelliyorum.")
            return self._ask_finish(trace, txt, pd, proposal, [], revised=revised)
        out = [c for c in names if c in ar.cid]
        if not out:
            return self._ask_finish(trace, f"{', '.join(ar.name(c) for c in names)} bugün müsait değil; planda yer almıyor.", None, proposal, [])
        gone = [c for c in out if c in plan_c]
        who = " ve ".join(ar.name(c) for c in out)
        if not gone:
            return self._ask_finish(trace, f"{who} bugünkü planda yok (yedekte); plan değişmez.", None, proposal, [])
        borrowed_remaining = [c for c in base["borrowed"] if c not in out]
        excl = sorted(set(base["exclude"]) | set(out))
        alts = []
        trace.emit("decision", text=f"{who} gelmezse iki yol var: komşu şubeden yerine biri, ya da kimse gelmez ve kümeler dağıtılır. "
                               f"İkisini de hesaplıyorum.")
        c = T["neighbor_candidates"]({"need": len(gone), "exclude": excl, "current_borrowed": borrowed_remaining})
        r1 = None
        if c["proposed"]:
            pd1 = {"borrowed": borrowed_remaining + c["proposed"], "exclude": excl, "pin": []}
            r1 = T["core_assignment"](pd1)
        pd2 = {"borrowed": borrowed_remaining, "exclude": excl, "pin": []}
        r2 = T["core_assignment"](pd2)
        b = proposal["total"]
        y2 = self._as_proposal(ar, r2, proposal)
        f2 = diff(proposal, y2)
        alts.append({"name": "Kimse gelmezse", "plan_change": pd2, "total": y2["total"], "diff": f2})
        def effect(y: dict, f: dict) -> str:
            s = (f"bant üstü süre {b['over_band_min']} → {y['total']['over_band_min']} dk ({num(f['over_band_min'], 0, sign=True)}), "
                 f"bandı aşan kurye {b['over_band_courier']} → {y['total']['over_band_courier']}, beklenen başarısız teslim "
                 f"{num(b['expected_fails'])} → {num(y['total']['expected_fails'])} ({num(f['expected_fails'], sign=True)})")
            if y["distributed_clusters"]:
                s = f"{len(y['distributed_clusters'])} küme komşu kümelere dağılır; " + s
            return s

        parts = []
        if r1 is not None:
            y1 = self._as_proposal(ar, r1, proposal)
            f1 = diff(proposal, y1)
            rep = " ve ".join(ar.name(x) for x in c["proposed"])
            alts.insert(0, {"name": f"Komşu şubeden {rep}", "plan_change": pd1, "total": y1["total"], "diff": f1})
            same = abs(f1["expected_fails"]) < 0.05 and f1["over_band_min"] == 0
            parts.append(f"(1) Komşu şubeden yerine {rep} gelirse: " + effect(y1, f1)
                         + ("; adaylar bu şubeye eşit yabancı olduğu için fark yok." if same else "."))
        parts.append(f"({len(parts) + 1}) Kimse gelmezse: " + effect(y2, f2) + ".")
        for x in alts:
            x["score"] = ar.score(x["total"])
        best = min(alts, key=lambda x: (x["score"], x["name"]))
        parts.append(f"Önerim: {best['name']}" + (" gelsin." if best is not alts[-1] else ".") + " Onaylarsanız planı güncelliyorum.")
        return self._ask_finish(trace, f"{who} gelmezse iki yol var. " + " ".join(parts), best["plan_change"], proposal, alts,
                                revised=self._as_proposal(ar, r1 if (r1 is not None and best is alts[0]) else r2, proposal))

    def _as_proposal(self, ar: DayTools, ev: dict, proposal: dict) -> dict:
        return {"day": ar.day, "weekday": self.run.weekday_name(ar.day),
                "borrowed": [{"id": c, "name": ar.name(c), "source_branch": NEIGHBOR_BRANCH} for c in ev["borrowed"]],
                "exclude": ev["exclude"], "assignment": ev["assignment"], "total": ev["total"],
                "own_zone_share": ev["own_zone_share"], "distributed_clusters": ev["distributed_clusters"],
                "dispatch_note": ev["dispatch_note"], "eta_model": ev["eta_model"], "idle_couriers": ev["idle_couriers"],
                "comparison": {"history_blind_expected_fails": ev["history_blind_expected_fails"]},
                "time_constraints": ar.time_summary(), "time_alternatives": ar.time_alt_summary(), "morning": proposal.get("morning"),
                "rationale": proposal.get("rationale", []), "risks": [], "questions": []}

    def _ask_finish(self, trace: Trace, txt: str, pd: dict | None, proposal: dict, alts: list[dict], revised: dict | None = None) -> dict:
        trace.emit("tool", tool=ASK_FINISH, input={"response": txt, "plan_change": pd})
        return {"response": txt, "new_proposal": revised if pd else None, "diff": diff(proposal, revised) if (pd and revised) else None,
                "alternatives": alts}

    # ---------------------------------------------------------------- insan onayı
    def apply_decision(self, day: int, proposal: dict, decision: str, assignment: list[dict] | None = None, note_: str | None = None) -> dict:
        """Müdürün kararı: onay → plan kesinleşir; ret → plan yok; duzenle → verilen atama doğrulanıp kesinleşir."""
        if decision == "approval":
            return {"status": "finalized", "plan": proposal, "changed_clusters": [], "note": note_}
        if decision == "ret":
            return {"status": "rejected", "plan": None, "changed_clusters": [], "note": note_}
        if decision != "edit":
            raise ValueError("karar 'onay', 'ret' ya da 'duzenle' olmalı")
        if not assignment:
            raise ValueError("duzenle için atama listesi gerekli")
        ar = self.tools(day)
        items = [{"cluster_id": int(a.get("cluster", a.get("cluster_id"))), "courier_id": a.get("courier", a.get("courier_id"))} for a in assignment]
        borrowed = sorted({x["courier_id"] for x in items if x["courier_id"] in ar.neighbors})
        ev = ar.evaluate_plan(borrowed, items)
        plan = self._as_proposal(ar, ev, proposal)
        plan["rationale"] = list(proposal.get("rationale", [])) + [f"Müdür düzenledi{': ' + note_ if note_ else ''}."]
        return {"status": "finalized", "plan": plan, "changed_clusters": diff(proposal, plan)["changed_clusters"], "note": note_,
                "diff": diff(proposal, plan)}


# ====================================================================== koşu deposu (API ve betikler)
class Session:
    def __init__(self, kid: str, day: int):
        self.id, self.day = kid, day
        self.trace = Trace()
        self.status = "running"           # calisiyor | awaiting_approval | kesinlesti | reddedildi | hata
        self.result: dict | None = None
        self.decision: dict | None = None
        self.error: str | None = None
        self.done = threading.Event()

    def summary(self, after: int = 0) -> dict:
        return {"session_id": self.id, "day": self.day, "status": self.status, "events": self.trace.since(after), "total_event": len(self.trace),
                "proposal": (self.result or {}).get("proposal"), "mode": (self.result or {}).get("mode"),
                "degraded": (self.result or {}).get("degraded"), "plan": (self.decision or {}).get("plan"), "error": self.error,
                "escalation": (self.result or {}).get("escalation") or []}


class SessionStore:
    """Bellek içi koşu kaydı (demo). Sunucu yeniden başlarsa kaybolur."""

    def __init__(self, orch: Orchestrator):
        self.orch = orch
        self.sessions: dict[str, Session] = {}
        self.plans: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._n = itertools.count(1)

    def start(self, day: int, background: bool = True, manager_review: bool = False) -> Session:
        with self._lock:
            k = Session(f"G{day}-{next(self._n):03d}", day)
            self.sessions[k.id] = k

        def work():
            try:
                k.result = self.orch.plan(day, k.trace, manager_review)
                k.status = k.result["status"]
                if k.status == "finalized":          # temassız: acil durum yok, plan müdüre gitmeden kesinleşti
                    k.decision = {"status": "finalized", "plan": k.result["proposal"], "changed_clusters": [], "note": None, "auto": True}
                    self.plans[day] = k.result["proposal"]
            except Exception as e:     # ajan da kurallı yedek de planı çıkaramadı: acil durum, müdüre eskale
                k.error, k.status = str(e), "error"
                k.trace.emit("escalation", source="rule", reasons=[{"code": "agent_failed", "text": f"Plan çıkarılamadı ({e}); müdür devreye girmeli."}])
                k.trace.emit("done", status="error", text=str(e))
            finally:
                k.done.set()

        if background:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()
        return k

    def get(self, kid: str) -> Session:
        if kid not in self.sessions:
            raise KeyError(kid)
        return self.sessions[kid]

    def decision(self, kid: str, decision: str, assignment: list[dict] | None = None, note_: str | None = None) -> dict:
        k = self.get(kid)
        k.done.wait(timeout=300)
        if k.status != "awaiting_approval" or not k.result:
            raise ValueError(f"Koşu onay beklemiyor (durum: {k.status})")
        proposal = k.result["proposal"]
        res = self.orch.apply_decision(k.day, proposal, decision, assignment, note_)
        k.decision = res
        k.status = res["status"]
        k.trace.emit("human_decision", source="human", decision=decision, changed_clusters=res["changed_clusters"], **{"note": note_})
        k.trace.emit("done", source="human", status=res["status"])
        if res["plan"] is not None:
            self.plans[k.day] = res["plan"]
        return res

    def ask(self, kid: str, question: str, history: list[dict] | None = None) -> dict:
        k = self.get(kid)
        k.done.wait(timeout=300)
        if not k.result:
            raise ValueError(f"Koşunun önerisi yok (durum: {k.status})")
        if k.status != "awaiting_approval":
            raise ValueError(f"Koşu onay beklemiyor (durum: {k.status})")
        return self.orch.ask(k.day, question, k.result["proposal"], k.trace, history)

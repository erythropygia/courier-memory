"""Rota aracı: bir kümenin rotası, kuryeye özgü beklenen süre ve hafıza kısıtları (Hedef 3).

`MemoryConstraints(book, run)` canlı hafızadan yapılı kısıt üretir (kapalı gün, geçici kapanış, kapalı pencere, ek servis).
`RoutePlanner.plan` hafızasız (düz) sıradan başlar ve simülatörün kol D'de kullandığı AYNI fonksiyonla
(`cm_sim.routing_memory.plan_route`) hafızalı rotayı kurar: bugün kapalı bilinen durak plandan çıkar, öğle arası bilinen
durak pencere dışına taşınır, bilinen püf noktasının kalan süresi plana girer. Çıktıda `constraints`, `changes` ve
`comparison` (hafızasız ↔ hafızalı) dolar. Canlı hafıza simülasyonun o günkü hafızasıyla aynıysa hafızalı sıra kol D'nin
yürüttüğü sırayla aynıdır (`same_as_sim`); kurye notu ya da hasat cevabı hafızayı değiştirdiyse rota da değişir.

Faz 2b: `time` (agents.delivery_time.TimeSource) teslim kayıtlarından çıkan saat bulgularını verir ("öğlen kimse yok, 18
sonrası var"); bulgulu durak, simülatörle aynı zaman onarımıyla (`plan_route(time_repair=True)`) bulunma olasılığı yüksek
saate kaydırılır. Değişiklik metinlerindeki sıra numaraları 1 tabanlı durak sırasıdır.

Faz 2c: onarımlar simülatörle aynı sert kısıtla (`RepairLimits`) çalışır: rota süresi (sürüş + servis + bilinen öğle beklemesi)
ve km onarım öncesinden fazla artmaz, bant üstü aşılmaz, kaydırılan durak vardiya bitişinden sonraya konmaz. Kısıt yüzünden
kaydırılamayan bulgu `time_unshiftable`da nedeniyle döner; `day_alternatives` günün tüm rotalarında simülatörle aynı
`time_alternatives` fonksiyonunu çağırır (aktarma → ertesi gün / akşam-teslim noktası + SMS önerisi; müdür kararı).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, Sequence

import numpy as np

from cm_sim.routing_memory import (RepairLimits, StopRule, arrivals, expected_time_fails, plan_route, rule_from_entries,
                                   time_alternatives)
from cm_sim.delivery_time import SLOT_NAMES, REASON_TEXT, BORDERS, alternative_text, proposal_text, sms_text

from .rundata import INFO_KINDS, RunData
from .tr import hhmm

DAY_START_MIN = 540          # 09:00; anlık görüntüdeki eta değerleri gece yarısından dakikadır
KM_PER_DEG_LAT, KM_PER_DEG_LNG_EQ = 110.574, 111.320     # cm_sim.world ile aynı izdüşüm


@dataclass(frozen=True)
class RouteConstraint:
    """Hafızadan türetilen, rotanın okuyabileceği yapılı kısıt."""
    address: int
    kind: str                                   # closed_day | closed_window | extra_service | dogru_nokta | temporary_closed | time_preference
    weekday: int | None = None                  # closed_day: 0=Pzt … 5=Cmt
    window: tuple[int, int] | None = None       # closed_window: [başlangıç, bitiş) gece yarısından dakika; time_preference: önerilen dilim
    extra_service_min: float = 0.0              # extra_service
    point: tuple[float, float] | None = None    # dogru_nokta: (lat, lng)
    until_day: int | None = None                # temporary_closed: bu güne kadar (dahil)
    source: str | None = None                   # hafıza kaydı kimliği
    sources: int = 1                            # kaydın bağımsız kaynak sayısı (erteleme eşiği için)


class ConstraintSource(Protocol):
    name: str

    def constraints(self, day: int, addresses: Sequence[int]) -> list[RouteConstraint]: ...


class NoConstraints:
    """Hafıza rotaya kısıt olarak girmez (karşılaştırma ve testler için)."""
    name = "offline"

    def constraints(self, day: int, addresses: Sequence[int]) -> list[RouteConstraint]:
        return []


def morning_info(cfg: dict) -> dict:
    """Faz 5: çalıştırmanın config.yaml'ından şubeden çıkış bilgisi (simülatör `engine._morning_min` karşılığı).
    Sabah kapalıysa çıkış = mesai başı (Faz 0–4)."""
    pl = cfg.get("planning") or {}
    sb = cfg.get("morning") or {}
    m = float(pl.get("start_minute", DAY_START_MIN))
    band_hi = float((pl.get("band") or [378, 528])[1])
    on = bool(sb.get("enabled", False))
    return {"enabled": on, "shift_start": m, "shift_end": m + band_hi,
            "current_min": float(sb.get("current_min", 90.0)) if on else 0.0,
            "presorted_min": float(sb.get("presorted_min", 30.0)) if on else 0.0,
            "deviation_min": float(sb.get("deviation_min", 10.0)) if on else 0.0,
            "arms": list(sb.get("presorted_arms", ["D"])) if on else []}


def plan_departure(sb: dict, arm: str) -> float:
    """Planın varsaydığı çıkış (beklenen, sapmasız): mesai başı + kolun sabah süresi."""
    if not sb["enabled"]:
        return sb["shift_start"]
    return sb["shift_start"] + (sb["presorted_min"] if arm in sb["arms"] else sb["current_min"])


def _routing_cfg(run: RunData) -> dict:
    cfg = EtaModel.load_cfg(run)
    r = dict(cfg.get("routing") or {})
    q = cfg.get("quirks") or {}
    pl = cfg.get("planning") or {}
    return {"enabled": bool(r.get("enabled", False)), "defer_closed": bool(r.get("defer_closed", True)),
            "window_repair": bool(r.get("window_repair", True)), "service_correction": bool(r.get("service_correction", True)),
            "extra": dict(r.get("extra_service_min") or {}), "min_src": int(r.get("defer_min_sources", 2)),
            "scale": float(r.get("time_scale", 1.1)), "margin": float(r.get("window_margin_min", 10)),
            "lunch": tuple(q.get("lunch_window", (720, 810))), "rf": float(pl.get("road_factor", 1.3)),
            "mpk": float(pl.get("minutes_per_km", 3.0)), "start": float(pl.get("start_minute", DAY_START_MIN)),
            "sps": float((cfg.get("outcome") or {}).get("service_per_stop", 1.0)),
            "spsh": float((cfg.get("outcome") or {}).get("service_per_shipment", 1.5)),
            "time_aware": bool(r.get("time_aware", False)), "revisit": float(r.get("time_revisit_min", 10.0)),
            "km_cost": float(r.get("time_km_cost_min", 0.8)), "min_gain": float(r.get("time_min_gain_min", 0.5)),
            "limits_on": bool(r.get("repair_limits", False)), "max_extra_min": float(r.get("repair_max_extra_min", 0.0)),
            "max_extra_km": float(r.get("repair_max_extra_km", 0.5)), "band_max": float((pl.get("band") or [378, 528])[1]),
            "wait_max": float(q.get("lunch_wait_max", 15.0)), "blocked_diff": float(r.get("time_blocked_diff", 0.3)),
            "alternatives": bool(r.get("time_alternatives", False)),
            "wait_margin": float(r.get("repair_wait_margin_min", r.get("window_margin_min", 10))),
            "morning": morning_info(cfg),
            "shift_end_at": (float(pl.get("start_minute", DAY_START_MIN)) + float((pl.get("band") or [378, 528])[1]))
            if bool((cfg.get("morning") or {}).get("enabled", False)) else None}


def repair_limits(rc: dict) -> RepairLimits | None:
    """Simülatörün `engine.repair_limits` karşılığı (çalıştırma klasörünün config.yaml'ından)."""
    if not rc.get("limits_on"):
        return None
    return RepairLimits(max_extra_min=rc["max_extra_min"], max_extra_km=rc["max_extra_km"], band_max=rc["band_max"],
                        wait_max=rc["wait_max"], blocked_diff=rc["blocked_diff"], wait_margin=rc["wait_margin"],
                        shift_end_at=rc.get("shift_end_at"))


class MemoryConstraints:
    """Canlı hafızadan (MemoryBook) kısıt üretir. Tür → kısıt eşlemesi simülatörle aynıdır (routing_memory)."""
    name = "memory"

    def __init__(self, book, run: RunData):
        self.book, self.run = book, run
        self.rc = _routing_cfg(run)

    def _entries(self, day: int, a: int) -> list[dict]:
        """Yalnız rotayı etkileyen türler; bilgi türleri (park, bina erişimi…; Faz 2d) plana ve rotaya girmez."""
        if self.book is None:
            return []
        return [e for e in self.book.for_address(int(a), day) if e["kind"] not in INFO_KINDS]

    def constraints(self, day: int, addresses: Sequence[int]) -> list[RouteConstraint]:
        out = []
        rc = self.rc
        for a in addresses:
            for e in self._entries(day, a):
                k, src, n = e["kind"], e["id"], int(e.get("sources", 1))
                if k == "saturday_closed":
                    out.append(RouteConstraint(int(a), "closed_day", weekday=5, source=src, sources=n))
                elif k == "temporary_closed":
                    out.append(RouteConstraint(int(a), "temporary_closed", until_day=e.get("ttl_until"), source=src, sources=n))
                elif k == "lunch_break":
                    w = e.get("window") or rc["lunch"]
                    out.append(RouteConstraint(int(a), "closed_window", window=(int(w[0]), int(w[1])), source=src, sources=n))
                elif rc["extra"].get(k):
                    out.append(RouteConstraint(int(a), "extra_service", extra_service_min=float(rc["extra"][k]), source=src, sources=n))
        return out

    def rules(self, day: int, addresses: Sequence[int]) -> dict[int, StopRule]:
        wd = day % 6
        out = {}
        for a in addresses:
            es = self._entries(day, a)
            if es:
                r = rule_from_entries([(e["kind"], e["id"], int(e.get("sources", 1)), e.get("window")) for e in es], wd,
                                      self.rc["lunch"], self.rc["extra"], self.rc["min_src"])
                if r is not None:
                    out[int(a)] = r
        return out


class EtaModel:
    """Kuryeye özgü beklenen rota süresi: gerçekleşen = a × planlanan + b × (kurye ek süresi).

    kurye ek süresi = atama matrisindeki `exp_min` − kümenin taban servis süresi (yabancılık ve hız etkisi).
    Katsayılar, o günden ÖNCEKİ değerlendirme günlerinin gerçekleşen rota sürelerine (gözlemlenebilir geçmiş) en küçük
    kareler ile oturtulur; gelecek günün verisi kullanılmaz. Yeterli geçmiş yoksa a=1, b=0,5.
    """

    @staticmethod
    def load_cfg(run: RunData) -> dict:
        import yaml
        p = run.dir / "config.yaml"
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
        return cfg if isinstance(cfg, dict) else {}

    def __init__(self, run: RunData, day: int, arm: str = "D"):
        self.cfg = self.load_cfg(run)
        ou = self.cfg.get("outcome", {})
        self.sps = float(ou.get("service_per_stop", 1.0))
        self.spsh = float(ou.get("service_per_shipment", 1.5))
        P, X, A = [], [], []
        for d in run.eval_days:
            if d >= day:
                break
            ai, snap = run.assign_input(arm, d), run.snapshot(arm, d)
            cid = [c["id"] for c in ai["couriers"]]
            for r in snap["routes"]:
                if r["courier"] not in cid or r["route"] >= len(ai["clusters"]):
                    continue
                cl = ai["clusters"][r["route"]]
                P.append(cl["planned_minutes"])
                X.append(ai["exp_min"][cid.index(r["courier"])][r["route"]] - self.base(cl))
                A.append(r["minutes"])
        self.n = len(A)
        if self.n >= 30:
            co, *_ = np.linalg.lstsq(np.c_[P, X], np.array(A), rcond=None)
            self.a, self.b = float(co[0]), float(co[1])
            pred = np.c_[P, X] @ co
            self.mae = float(np.abs(np.array(A) - pred).mean())
            self.mae_planned = float(np.abs(np.array(A) - np.array(P)).mean())
        else:
            self.a, self.b, self.mae, self.mae_planned = 1.0, 0.5, None, None

    def base(self, cluster: dict) -> float:
        return self.sps * cluster["stops"] + self.spsh * cluster["shipments"]

    def predict(self, cluster: dict, exp_min: float) -> float:
        return self.a * float(cluster["planned_minutes"]) + self.b * (float(exp_min) - self.base(cluster))

    def info(self) -> dict:
        return {"a": round(self.a, 3), "b": round(self.b, 3), "history_route": self.n,
                "mean_absolute_error_min": None if self.mae is None else round(self.mae, 1),
                "planned_only_error_min": None if self.mae_planned is None else round(self.mae_planned, 1)}


def _slot_range(d: int) -> tuple[int, int]:
    b = (540,) + BORDERS + (1440,)
    return int(b[d]), int(b[d + 1])


class RoutePlanner:
    def __init__(self, run: RunData, source: ConstraintSource | None = None, arm: str = "D", time="auto"):
        """zaman: "auto" → çalıştırma klasörünün paylaşılan teslim zamanı kaynağı (kol D); None → zaman analizi yok."""
        self.run, self.arm = run, arm
        self.source: ConstraintSource = source or NoConstraints()
        self.rc = _routing_cfg(run)
        self.rc["start"] = plan_departure(self.rc["morning"], arm)     # Faz 5: plan şubeden çıkış saatinden başlar
        if time == "auto":
            from .delivery_time import time_source
            time = time_source(run) if arm == "D" else None
        self.time = time
        self.limits = repair_limits(self.rc)
        lat0, lng0 = run.meta["center"]
        self._c = (float(lat0), float(lng0), KM_PER_DEG_LNG_EQ * np.cos(np.radians(float(lat0))))

    def _xy(self, latlng: np.ndarray) -> np.ndarray:
        lat0, lng0, kx = self._c
        ll = np.asarray(latlng, dtype=float).reshape(-1, 2)
        return np.stack([(ll[:, 1] - lng0) * kx, (ll[:, 0] - lat0) * KM_PER_DEG_LAT], axis=-1)

    def _rules(self, day: int, addrs: list[int], cons: list[RouteConstraint]) -> dict[int, StopRule]:
        if hasattr(self.source, "rules"):
            return self.source.rules(day, addrs)
        ents: dict[int, list] = {}                      # yalnız kısıt listesi veren kaynak (testler, dış kaynak)
        kmap = {"closed_day": "saturday_closed", "temporary_closed": "temporary_closed", "closed_window": "lunch_break"}
        for c in cons:
            k = kmap.get(c.kind)
            if k:
                ents.setdefault(c.address, []).append((k, c.source, c.sources, c.window))
            elif c.kind == "extra_service":
                ents.setdefault(c.address, []).append(("_extra", c.source, c.sources, None))
        out = {}
        for a, es in ents.items():
            r = rule_from_entries(es, day % 6, self.rc["lunch"], {"_extra": 0.0}, self.rc["min_src"])
            if r is not None:
                r.extra = sum(c.extra_service_min for c in cons if c.address == a and c.kind == "extra_service")
                out[a] = r
        return out

    def apply(self, day: int, route: dict, cons: list[RouteConstraint]) -> dict:
        """Hafızasız sıradan hafızalı rotayı kurar (cm_sim.routing_memory.plan_route). Dönüş: plan_route çıktısı + düz sıra."""
        F = {k: i for i, k in enumerate(self.run.snapshot(self.arm, day)["stop_fields"])}
        visited = {int(s[F["address"]]): s for s in route["stops"]}
        plan = route.get("plan") or {}
        plain = [int(a) for a in plan.get("plain_order", [])] or list(visited)
        n_of = {int(s[F["address"]]): int(s[F["n"]]) for s in route["stops"]}
        for d in plan.get("deferred", []):
            n_of[int(d["address"])] = int(d["n"])
        ll = np.array([self.run.addr_ll[a] for a in plain])
        base = np.array([self.rc["sps"] + self.rc["spsh"] * n_of.get(a, 1) for a in plain])
        rules = self._rules(day, plain, cons)
        rc = self.rc
        zb = self.time.route(day, plain) if (self.time is not None and rc["time_aware"]) else {}
        for a, b in zb.items():
            rules.setdefault(int(a), StopRule()).presence = tuple(float(x) for x in b["estimate"])
        dep = self._xy(np.array(self.run.meta["depot"]))[0]
        kw = dict(road_factor=rc["rf"], mpk=rc["mpk"], start=rc["start"], scale=rc["scale"], margin=rc["margin"],
                  defer_closed=rc["defer_closed"], window_repair=rc["window_repair"], service_correction=rc["service_correction"],
                  revisit_min=rc["revisit"], km_cost_min=rc["km_cost"], min_gain_min=rc["min_gain"], limits=self.limits)
        res = plan_route(self._xy(ll), dep, np.array(plain), base, rules, time_repair=bool(zb), **kw)
        if any(c["type"] == "time" for c in res["changes"]):
            nt = plan_route(self._xy(ll), dep, np.array(plain), base, rules, time_repair=False, **kw)
            res["no_time"] = {"order": [int(a) for a in nt["order"]], "km": nt["km"], "planned": nt["planned"]}
        res["time_findings"] = zb
        res["plain"] = plain
        res["rules"] = rules
        res["n_of"] = n_of
        res["base"] = dict(zip(plain, base.tolist()))
        res["xy"] = dict(zip(plain, self._xy(ll)))
        res["depot_xy"] = dep
        return res

    def _time_fails(self, order: list[int], res: dict) -> float:
        """Bulgulu duraklarda beklenen bulunamama (durak) toplamı, bu sırayla (planlanan beklenen varışlarla)."""
        zb = res.get("time_findings") or {}
        if not order or not zb:
            return 0.0
        rules = res["rules"]
        pts = np.vstack([res["depot_xy"][None, :], np.array([res["xy"][a] for a in order])])
        D = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)) * self.rc["rf"]
        svc = np.concatenate([[0.0], [res["base"][a] + (rules[a].extra if a in rules and self.rc["service_correction"] else 0.0)
                                      for a in order]])
        idx = np.concatenate([[0], np.arange(1, len(order) + 1), [0]])
        pos = {a: i for i, a in enumerate(order, start=1)}
        pres = {pos[a]: np.array(b["estimate"], dtype=float) for a, b in zb.items() if a in pos}
        return expected_time_fails(idx, D, svc, pres, self.rc["start"], self.rc["mpk"], self.rc["scale"])

    def _window_hits(self, order: list[int], res: dict) -> tuple[int, int, list[int]]:
        """Beklenen varışı kendi kapalı penceresine düşen durak sayısı, kapalı (bugün) kapıya gidiş sayısı ve her durağın
        beklenen varışı (dk; başlangıç + time_scale × planlanan geçen süre). Sabah brifingi bu varışları kullanır."""
        rules = res["rules"]
        if not order:
            return 0, 0, []
        pts = np.vstack([res["depot_xy"][None, :], np.array([res["xy"][a] for a in order])])
        D = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)) * self.rc["rf"]
        svc = np.concatenate([[0.0], [res["base"][a] + (rules[a].extra if a in rules and self.rc["service_correction"] else 0.0)
                                      for a in order]])
        idx = np.concatenate([[0], np.arange(1, len(order) + 1), [0]])
        arr = arrivals(idx, D, svc, self.rc["start"], self.rc["mpk"], self.rc["scale"])
        hits = closed = 0
        for i, a in enumerate(order, start=1):
            r = rules.get(a)
            if r is None:
                continue
            if any(lo <= arr[i] < hi for lo, hi in r.windows):
                hits += 1
            if r.closed:
                closed += 1
        return hits, closed, [int(round(x)) for x in arr[1:-1]]

    def _constraints(self, day: int, route: dict, F: dict) -> list[RouteConstraint]:
        plan = route.get("plan") or {}
        addrs = [int(a) for a in plan.get("plain_order", [])] or [int(s[F["address"]]) for s in route["stops"]]
        cons = self.source.constraints(day, addrs)
        if self.time is not None and self.rc["time_aware"] and self.rc["enabled"]:
            for a, b in self.time.route(day, addrs).items():
                cons.append(RouteConstraint(int(a), "time_preference", window=_slot_range(b["good"]) if b.get("good") is not None else None,
                                            source=f"Z{int(a)}", sources=1))
        return cons

    def shift_end(self) -> float | None:
        return None if self.limits is None else self.limits.shift_end(self.rc["start"])

    def unshiftable_rows(self, res: dict, courier_name: str | None = None) -> list[dict]:
        """Aynı rotada kısıt yüzünden kaydırılamayan bulgular (neden + okunur metin). Rota dışı alternatif yok (bkz. day_alternatives)."""
        lab = self.run.addr_label
        out = []
        for b in res.get("time_blocked") or []:
            reason = REASON_TEXT.get(b["reason"], b["reason"])
            extra = f"; en az {b['min_extra_min']:+.1f} dk" if b.get("min_extra_min") is not None and b["reason"] in ("route_duration", "band", "km") else ""
            out.append({**b, "label": lab[b["address"]], "good_slot": SLOT_NAMES[b["good"]],
                        "text": f"{lab[b['address']]}: {hhmm(b['arrival'])} (tahmini bulunamama %{round(100 * b['p_now'])}); en iyi saat "
                                 f"{SLOT_NAMES[b['good']]} ama aynı rotada kaydırılamadı: {reason}{extra}. Alternatif için "
                                 f"time_alternatives (başka kurye / ertesi gün + SMS; müdür kararı)."})
        return out

    def day_alternatives(self, day: int, mapping: dict[int, str] | None = None) -> list[dict]:
        """Günün tüm rotalarında kaydırılamayan bulgular için alternatifler (simülatörle aynı `time_alternatives`)."""
        if self.limits is None or not self.rc["enabled"] or self.time is None or not self.rc["time_aware"]:
            return []
        snap = self.run.snapshot(self.arm, day)
        F = {k: i for i, k in enumerate(snap["stop_fields"])}
        by_route, cour = {}, {}
        for route in snap["routes"]:
            if not route.get("plan"):
                continue
            k = int(route["route"])
            by_route[k] = self.apply(day, route, self._constraints(day, route, F))
            cour[k] = (mapping or {}).get(k) or route["courier"]
        if not by_route:
            return []
        rc = self.rc
        alts = time_alternatives(by_route, road_factor=rc["rf"], mpk=rc["mpk"], start=rc["start"], scale=rc["scale"],
                                    margin=rc["margin"], limits=self.limits, min_gain=rc["min_gain"] / max(1e-9, rc["revisit"]))
        lab, se = self.run.addr_label, self.shift_end()
        out = []
        for x in alts:
            y = {**x, "label": lab[x["address"]], "courier": cour.get(x["source"]), "courier_name": self.run.courier_name(cour.get(x["source"], "")),
                 "target_courier": cour.get(x["target"]) if x.get("target") is not None else None}
            y["target_courier_name"] = self.run.courier_name(y["target_courier"]) if y["target_courier"] else None
            y["text"] = alternative_text(y, y["label"], y["courier_name"], y["target_courier_name"], se)
            y["sms_text"] = sms_text(y["target_arrival"] if y["option"] == "transfer" else y["arrival"])
            out.append(y)
        return out

    def plan(self, day: int, cluster: int, courier: str, expected_min: float | None = None, memory_count=None) -> dict:
        snap = self.run.snapshot(self.arm, day)
        route = next((r for r in snap["routes"] if r["route"] == cluster), None)
        if route is None:
            raise ValueError(f"Gün {day}: küme {cluster} için rota yok")
        F = {k: i for i, k in enumerate(snap["stop_fields"])}
        plan = route.get("plan") or {}
        cons = self._constraints(day, route, F)
        planned = float(route.get("planned_minutes", route["minutes"]))
        exp_min = float(expected_min) if expected_min is not None else planned
        out = {"cluster": cluster, "courier": courier, "name": self.run.courier_name(courier), "km": round(float(route["km"]), 1),
               "planned_min": round(planned, 0), "expected_min": round(exp_min, 0), "start": hhmm(self.rc["start"]),
               "start_min": self.rc["start"], "estimated_return": hhmm(self.rc["start"] + exp_min), "constraint_source": self.source.name,
               "constraints": [asdict(c) for c in cons], "changes": [], "comparison": None}
        if isinstance(self.source, NoConstraints) or not plan or not self.rc["enabled"]:
            stops = route["stops"]
            out.update(stop=len(stops), shipment=int(sum(s[F["n"]] for s in stops)),
                       memory_stop=sum(1 for s in stops if memory_count and memory_count(int(s[F["address"]])) > 0))
            return out
        res = self.apply(day, route, cons)
        order = [int(a) for a in res["order"]]
        n_of = res["n_of"]
        lab = self.run.addr_label
        changes = []
        for a, kind, src in res["deferred"]:
            changes.append({"type": "deferred", "address": a, "label": lab[a], "reason": kind, "record": src, "shipment": n_of.get(a, 0),
                            "text": f"{lab[a]}: bugün kapalı ({'Cumartesi kapalı' if kind == 'saturday_closed' else 'geçici kapanış'}); "
                                     f"plandan çıkarıldı, boşuna gidilmeyecek."})
        zb = res.get("time_findings") or {}
        for c in res["changes"]:
            if c["type"] == "time":
                b = zb.get(c["address"], {})
                extra = " (kurye teyit etti)" if b.get("confirmed") else ""
                changes.append({**c, "label": lab[c["address"]], "finding": proposal_text(b) if b else None, "confirmed": bool(b.get("confirmed")),
                                "old_slot": SLOT_NAMES[_slot_of(c["old_arrival"])], "new_slot": SLOT_NAMES[_slot_of(c["new_arrival"])],
                                "text": f"{lab[c['address']]}: teslim kayıtları {proposal_text(b) if b else '?'}{extra} "
                                         f"→ {hhmm(c['old_arrival'])} yerine {hhmm(c['new_arrival'])} ({c['old_order']}. sıradan "
                                         f"{c['new_order']}. sıraya, {c['extra_km']:+.1f} km, rota süresi {c.get('extra_min', 0):+.0f} dk); "
                                         f"tahmini bulunamama %{round(100 * c['old_p'])} → %{round(100 * c['new_p'])}."})
                continue
            w = c["window"]
            # old_order / new_order zaten 1 tabanlı durak sırası (düğüm 0 = depo); Faz 2'de +1 eklenip bir fazla yazılıyordu.
            changes.append({**c, "label": lab[c["address"]],
                            "text": f"{lab[c['address']]}: {hhmm(c['old_arrival'])} varış {hhmm(w[0])}–{hhmm(w[1])} kapalı penceresine "
                                     f"denk geliyordu → {hhmm(c['new_arrival'])} ({c['old_order']}. sıradan {c['new_order']}. sıraya, "
                                     f"{c['extra_km']:+.1f} km, rota süresi {c.get('extra_min', 0):+.0f} dk)."})
        extra = res["extra"]
        if extra:
            changes.append({"type": "extra_service", "stop": len(extra), "mins": round(sum(extra.values()), 1),
                            "text": f"{len(extra)} durakta bilinen püf noktası için +{sum(extra.values()):.0f} dk servis süresi plana eklendi."})
        h0, c0, _ = self._window_hits(res["plain"], res)
        h1, c1, arrival = self._window_hits(order, res)
        z0, z1 = self._time_fails(res["plain"], res), self._time_fails(order, res)
        zs = res.get("no_time")
        no_time_route = None
        if zs is not None:
            no_time_route = {"km": round(zs["km"], 1), "planned_min": round(zs["planned"]), "order": zs["order"],
                    "expected_absence": round(self._time_fails(zs["order"], res), 2)}
        mem = memory_count or (lambda a: 0)
        visited_plain = res["plain"]
        out.update(stop=len(order), shipment=int(sum(n_of.get(a, 0) for a in order)),
                   memory_stop=sum(1 for a in order if mem(a) > 0),
                   changes=changes, same_as_sim=order == [int(s[F["address"]]) for s in route["stops"]],
                   comparison={
                       "memoryless": {"stop": len(visited_plain), "km": round(res["plain_km"], 1),
                                     "planned_min": round(res["plain_planned"]), "window_matching": h0, "closed_door_visit": c0,
                                     "expected_absence": round(z0, 2), "order": visited_plain},
                       "no_time": no_time_route,
                       "memory": {"stop": len(order), "km": round(res["km"], 1), "planned_min": round(res["planned"]),
                                    "window_matching": h1, "closed_door_visit": c1, "expected_absence": round(z1, 2),
                                    "order": order, "expected_arrival": arrival},
                       "diff": {"km": round(res["km"] - res["plain_km"], 2), "deferred": len(res["deferred"]),
                                "carried": sum(1 for c in res["changes"] if c["type"] == "window"),
                                "time_carried": sum(1 for c in res["changes"] if c["type"] == "time"),
                                "window_matching": h1 - h0, "closed_door_visit": c1 - c0,
                                "expected_absence": round(z1 - z0, 2),
                                "time_unshiftable": len(res.get("time_blocked") or [])},
                       "route_constraint": res.get("limits"),
                       "simulation": route.get("counterfactual"),
                       "note": ("Hafızasız = aynı duraklar, mesafeye göre sıra, hafıza yok. Zamansız = hafızalı rota, teslim zamanı "
                               "onarımı yok (yalnız zaman onarımı rotayı değiştirdiyse). 'simulasyon': bu rota kol D'de hafızasız / "
                               "yalnız ipucu / zamansız / hafızalı yürütüldüğünde gerçekleşen (aynı rastgele sayılar).")},
                   time_findings=[self.time.row(a, b, day) for a, b in zb.items()] if (self.time is not None and zb) else [],
                   time_unshiftable=self.unshiftable_rows(res, self.run.courier_name(courier)))
        return out


def _slot_of(minute: float) -> int:
    from cm_sim.delivery_time import slot
    return slot(minute)

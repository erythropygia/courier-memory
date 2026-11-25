"""Simülasyon motoru: ısınma (sabit bölge) → çatallama → dört kol.

A: Mevcut yapı (sabit bölge)
B: Yeni yapı · geçmişe bakmadan atama
C: Yeni yapı · kurye–bölge uyumuna göre atama
D: Yeni yapı · uyum + hafıza

B aynı gün dinamik kümeleri kullanır. C ve D çekirdek bölgeli planı kurar; D'de hafıza planı da değiştirir
(`routing_memory`): bugün kapalı bilinen durak kümelemeden önce çıkar, bilinen püf noktasının kalan süresi durak
ağırlığına girer, öğle arası bilinen durak pencere dışına taşınır. Plan kesinleşince D'de proaktif hasat yapılır
(yabancı kurye için hafızası boş durakları → o bloğu tanıyan kıdemliye hedefli soru).

Her D rotası için iki karşı-olgu da aynı rastgele sayılarla yürütülür (aynı kurye, aynı duraklar, aynı gün):
"hafızasız" (düz sıra, ipucu yok) ve "yalnız ipucu" (düz sıra + kapı ipucu). Hafızanın rotaya katkısı buradan ölçülür.
Faz 2b: teslim zamanı analizi (kayıtlardan, `cm_sim.delivery_time`) bulgusu olan durakları bulunma olasılığı yüksek saate
kaydırır; zaman onarımı rotayı değiştirdiyse üçüncü karşı-olgu "zamansız" (aynı hafızalı rota, zaman onarımı yok) yürütülür.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .config import Config
from .couriers import Courier, build_couriers
from .demand import base_rates, demand_for_day, weekday
from .history import Familiarity, History, HistoryReader
from .notes import Note, make_quirk_note, maybe_noise_note
from .outcome import PREVENTABLE, REASONS, RouteResult, execute_route
from .estimation import assignment_totals, expected_cost
from .planning import (Route, fixed_zones, make_route, n_clusters, order_route, plan_dynamic, plan_fixed, service_minutes,
                       zone_centroids)
from .config import ADDRESS_KINDS
from .routing_memory import RepairLimits, StopRule, plan_route, time_alternatives
from .delivery_time import SLOT_MID, Params as TimeParams, TimeRecord, fits_route, time_findings
from .policies.base import (AssignmentDecision, ClusterView, CourierView, DayContext, StopView,
                            validate_mapping)
from .policies.memory_oracle import MemoryOraclePolicy
from .policies.simple import AnchoredPlanPolicy, BlindPolicy
from .rng import S_MORNING, day_streams, rng
from .world import World, build_world, p_absent

ARMS = ("A", "B", "C", "D")
ARM_LABELS = {
    "A": "Mevcut yapı · sabit bölge",
    "B": "Yeni yapı · geçmişe bakmadan atama",
    "C": "Yeni yapı · çekirdek bölgeli dinamik plan",
    "D": "Yeni yapı · çekirdek bölge + hafıza",
}


@dataclass
class ArmState:
    arm: str
    fam: Familiarity
    history: History
    known: dict[str, dict[tuple[int, int], int]]
    zone_owner: dict[int, str]
    memory: MemoryOraclePolicy | None = None
    daily: list[dict] = field(default_factory=list)
    courier_daily: list[dict] = field(default_factory=list)
    results: dict[int, list[RouteResult]] = field(default_factory=dict)
    routes: dict[int, list[Route]] = field(default_factory=dict)
    decisions: dict[int, AssignmentDecision] = field(default_factory=dict)
    notes: list[Note] = field(default_factory=list)
    memory_snapshots: dict[int, list[dict]] = field(default_factory=dict)
    parse_stats: list[dict] = field(default_factory=list)
    counterfactuals: dict[int, dict[int, dict]] = field(default_factory=dict)   # gün → rota → {hafizasiz, hint_only, hafizali}
    harvest_stats: list[dict] = field(default_factory=list)
    time_stats: list[dict] = field(default_factory=list)                        # Faz 2b: günlük teslim zamanı bulgusu istatistiği
    time_alts: dict[int, list[dict]] = field(default_factory=dict)              # Faz 2c: gün → kaydırılamayan bulgu alternatifleri


def shift_end_at(cfg: Config) -> float:
    """Vardiya bitişi saat olarak: mesai başı + bant üstü (09:00 + 528 = 17:48). Fazla mesai bu saatten sayılır."""
    return float(cfg.planning.start_minute) + float(cfg.planning.band[1])


def repair_limits(cfg: Config) -> RepairLimits | None:
    """Faz 2c sert kısıtı (routing.repair_*; bant üstü planning.band[1]; bekleme üst sınırı quirks.lunch_wait_max)."""
    rc = cfg.routing
    if not rc.repair_limits:
        return None
    return RepairLimits(max_extra_min=rc.repair_max_extra_min, max_extra_km=rc.repair_max_extra_km,
                        band_max=float(cfg.planning.band[1]), wait_max=float(cfg.quirks.lunch_wait_max),
                        blocked_diff=rc.time_blocked_diff, wait_margin=rc.repair_wait_margin_min,
                        shift_end_at=shift_end_at(cfg) if cfg.morning.enabled else None)


@dataclass
class SimResult:
    cfg: Config
    world: World
    couriers: list[Courier]
    zone_of: np.ndarray
    arms: dict[str, ArmState]
    warm: ArmState
    eval_days: list[int]
    counts: dict[int, np.ndarray]
    elapsed: float


class Simulation:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.world = build_world(cfg)
        self.couriers = build_couriers(cfg)
        self.by_id = {c.id: c for c in self.couriers}
        self.cidx = {c.id: i for i, c in enumerate(self.couriers)}
        self._morning_cache: dict[int, np.ndarray] = {}
        self.rates = base_rates(cfg, self.world)
        self.zone_of = fixed_zones(cfg, self.world, self.rates, rng(cfg.seed, 98))
        self.centroids = zone_centroids(self.world, self.zone_of, cfg.couriers.senior)
        pl = cfg.planning
        self.kind_idx = np.array([ADDRESS_KINDS.index(k) for k in self.world.addr_kind], dtype=np.int64)
        self.zparams = TimeParams.from_dict(cfg.time_analysis.model_dump())
        self.policies = {
            "B": BlindPolicy(cfg.seed),
            "C": AnchoredPlanPolicy("anchored", pl.anchor_bonus_km, pl.anchor_alpha, pl.anchor_slack, pl.anchor_min_f, pl.kmeans_iters),
            "D": AnchoredPlanPolicy("anchored_memory", pl.anchor_bonus_km, pl.anchor_alpha, pl.anchor_slack, pl.anchor_min_f,
                                    pl.kmeans_iters, use_memory=True),
        }

    # ------------------------------------------------------------------ Faz 5: sabah (şubeden çıkış)
    def _morning_min(self, arm: str) -> float:
        """Mesai başından çıkışa beklenen dakika. Isınma ("W") bugünkü süreçtir."""
        sb = self.cfg.morning
        if not sb.enabled:
            return 0.0
        return float(sb.presorted_min if arm in sb.presorted_arms else sb.current_min)

    def _plan_start(self, arm: str) -> float:
        """Planın varsaydığı çıkış (beklenen, sapmasız); ajan aynı değeri kullanır (agents/route.py)."""
        return float(self.cfg.planning.start_minute) + self._morning_min(arm)

    def _deviation(self, day: int) -> np.ndarray:
        """Kurye başına çıkış sapması (dk); gün başına ayrı akış, kollar arası aynı (CRN)."""
        if day not in self._morning_cache:
            z = np.clip(rng(self.cfg.seed, day, S_MORNING).standard_normal(len(self.couriers)), -2.0, 2.0)
            self._morning_cache[day] = z * float(self.cfg.morning.deviation_min)
        return self._morning_cache[day]

    def _departure(self, arm: str, day: int, cid: str, mins: float | None = None) -> float:
        """Gerçekleşen çıkış = mesai başı + sabah süresi + kurye sapması. Sabah kapalıysa mesai başı (Faz 0–4)."""
        start = float(self.cfg.planning.start_minute)
        if not self.cfg.morning.enabled:
            return start
        base = self._morning_min(arm) if mins is None else float(mins)
        return start + max(0.0, base + float(self._deviation(day)[self.cidx[cid]]))

    # ------------------------------------------------------------------ yardımcılar
    def _ctx(self, st: ArmState, day: int, use_memory: bool) -> DayContext:
        return DayContext(
            day=day, weekday=weekday(day),
            history=HistoryReader(st.history, st.fam, self.cfg.familiarity.unfamiliar_below, self.world.block_kind),
            memory=st.memory.reader() if (use_memory and st.memory) else None,
            assignment_cfg=self.cfg.assignment,
            service_per_stop=self.cfg.outcome.service_per_stop,
            service_per_shipment=self.cfg.outcome.service_per_shipment,
            unfamiliar_below=self.cfg.familiarity.unfamiliar_below,
            block_xy=self.world.block_xy,
        )

    def stop_views(self, day: int, stops: np.ndarray, counts: np.ndarray) -> tuple[StopView, ...]:
        w = self.world
        return tuple(StopView(id=f"{day}-{int(a)}", address=int(a), block=int(w.addr_block[a]),
                              lat=float(w.addr_latlng[a, 0]), lng=float(w.addr_latlng[a, 1]),
                              n_shipments=int(counts[a]), x=float(w.addr_xy[a, 0]), y=float(w.addr_xy[a, 1])) for a in stops)

    def cluster_views(self, day: int, routes: list[Route], counts: np.ndarray) -> list[ClusterView]:
        return [ClusterView(id=r.id, stops=self.stop_views(day, r.stops, counts), planned_minutes=r.planned_minutes, km=r.km)
                for r in routes]

    def courier_views(self, st: ArmState, day: int) -> list[CourierView]:
        return [CourierView(id=c.id, name=c.name, kind=c.kind, available=c.available(day),
                            days_in_branch=st.history.c_days.get(c.id, 0)) for c in self.couriers]

    def _new_state(self, arm: str) -> ArmState:
        h = History(self.world.n_blocks)
        h.time = TimeRecord(self.world.n_addresses)
        return ArmState(arm=arm, fam=Familiarity(self.cfg.familiarity.alpha, self.cfg.familiarity.half_life),
                        history=h, known={c.id: {} for c in self.couriers},
                        zone_owner={z: f"K{z + 1:02d}" for z in range(self.cfg.couriers.senior)})

    def _update_zone_owners(self, st: ArmState, day: int) -> None:
        owners = set(st.zone_owner.values())
        for z, cid in list(st.zone_owner.items()):
            c = self.by_id[cid]
            if c.end_day is not None and day >= c.end_day:
                cand = [x for x in self.couriers if x.kind == "new" and x.available(day) and x.id not in owners]
                if cand:
                    st.zone_owner[z] = cand[0].id
                    owners.add(cand[0].id)

    def _seed_border_familiarity(self, st: ArmState) -> None:
        """Komşu şube kuryesi sınır sokaklarını kendi şubesinden düzenli dağıtır: o blokların teslim geçmişi şirket içinde
        ortaktır (gözlemlenebilir), tanıdıklık olarak görünür. calendar.borrowed[].border_side ile."""
        w = self.world
        bx, by = w.block_xy[:, 0], w.block_xy[:, 1]
        for b in self.cfg.calendar.borrowed:
            if not b.border_side:
                continue
            dep = b.border_depth_km
            side = {"east": bx >= bx.max() - dep, "west": bx <= bx.min() + dep,
                    "north": by >= by.max() - dep, "south": by <= by.min() + dep}[b.border_side]
            for blk in np.flatnonzero(side):
                st.fam.state[b.id][int(blk)] = (b.border_familiarity, self.cfg.days.warmup - 1)

    # ------------------------------------------------------------------ gün yürütme
    def _execute(self, st: ArmState, day: int, routes: list[Route], counts: np.ndarray, streams,
                 use_hints: bool, ingest: MemoryOraclePolicy | None, record: bool) -> None:
        cfg, w = self.cfg, self.world
        wd = weekday(day)
        ctx = self._ctx(st, day, use_memory=use_hints)
        results: list[RouteResult] = []
        for r in routes:
            c = self.by_id[r.courier]
            hints = None
            if use_hints and st.memory is not None:
                hints = st.memory.hints_for(ctx, c.id, self.stop_views(day, r.stops, counts))
            results.append(execute_route(cfg, w, r, c, day, wd, counts, streams, st.fam, st.known[c.id], hints,
                                         start=self._departure(st.arm, day, c.id)))

        notes: list[Note] = []
        h = st.history
        thr = cfg.familiarity.unfamiliar_below
        for rr in results:
            c = self.by_id[rr.courier]
            blocks = set()
            last_xy = w.depot_xy
            for s in rr.stops:
                blocks.add(s.block)
                last_xy = w.addr_xy[s.address]
                h.addr_days[s.address] += 1
                # Teslim zamanı kaydı (gözlemlenebilir): bulunabilirliği sınayan denemeler (teslim ya da alıcı yok).
                if h.time is not None and s.deferred == 0 and (s.ok > 0 or s.reasons.get("recipient_absent", 0) > 0):
                    h.time.add(day, s.address, wd, int(round(s.arrival)), s.ok == 0)
                att = s.ok + s.fail
                if att:
                    rel = s.fail - s.reasons.get("recipient_absent", 0)
                    h.block_att[s.block] += att
                    h.block_fail[s.block] += s.fail
                    h.block_rel[s.block] += rel
                    if s.familiarity < thr:
                        h.unf_att[s.block] += att
                        h.unf_fail[s.block] += s.fail
                        h.unf_rel[s.block] += rel
                        h.cb_unf_att[(c.id, s.block)] += att
                    else:
                        h.fam_att[s.block] += att
                        h.fam_fail[s.block] += s.fail
                        h.fam_rel[s.block] += rel
                    h.cb_att[(c.id, s.block)] += att
                    h.c_att[c.id] += att
                    h.c_fail[c.id] += s.fail
                    h.c_rel[c.id] += rel
                    base = cfg.outcome.service_per_stop + cfg.outcome.service_per_shipment * s.n
                    if s.familiarity >= thr:
                        # Kapı hızı yalnız tanıdık duraklardan: yabancı durağın yol bulma dakikası kuryeyi "yavaş" göstermesin
                        # (yalnız yabancı sokakta gözlenmiş ödünç/yeni kurye haksız yere cezalanırdı).
                        h.c_svc_actual[c.id] += s.service
                        h.c_svc_base[c.id] += base
                    ex = h.extra_unf if s.familiarity < thr else h.extra_fam
                    ex[0] += s.service - base
                    ex[1] += 1
                for slot, q in s.encountered:
                    if streams.u_learn[s.address, slot] < cfg.learning.p_learn:
                        st.known[c.id][(s.address, q.id)] = q.version(day)
                if s.encountered and streams.u_note[s.address] < c.note_propensity:
                    notes.append(make_quirk_note(cfg, w, day, s.arrival, c.id, s.encountered[0][1], s.n))
                if (cfg.memory.feedback and use_hints and st.memory is not None and s.wrong_hint
                        and streams.u_feedback[s.address] < cfg.memory.p_feedback):
                    st.memory.feedback_invalidate(w, s.address, day)
            nn = maybe_noise_note(cfg, w, day, c.id, rr.end_minute, last_xy)
            if nn:
                notes.append(nn)
            for b in blocks:
                st.fam.visit(c.id, b, day)
            h.c_days[c.id] += 1
        if ingest is not None:
            ps = ingest.ingest_with_truth(w, day, notes)
            ps["events"] = ingest.ingest_events(w, day, wd, [s for rr in results for s in rr.stops], cfg.quirks.lunch_window)
            st.parse_stats.append({"day": day, **ps})
        st.notes.extend(notes)
        self._last_routes = routes
        if record:
            st.results[day] = results
            st.routes[day] = routes
            st.daily.append(self._day_metrics(st.arm, day, results, counts, notes))
            for r, rr in zip(routes, results):
                c = self.by_id[rr.courier]
                allst = rr.stops + rr.plan_deferred
                att = sum(s.ok + s.fail for s in allst)
                vis = [s for s in rr.stops if s.deferred == 0]
                st.courier_daily.append({
                    "day": day, "courier": c.id, "kind": c.kind, "stops": len(rr.stops),
                    "attempted": att, "ok": sum(s.ok for s in allst),
                    "preventable_fail": sum(s.preventable_fail for s in allst),
                    "unfamiliar_share": round(sum(s.unfamiliar for s in rr.stops) / max(1, len(rr.stops)), 4),
                    "hinted": sum(s.hinted for s in rr.stops), "minutes": round(rr.minutes, 1), "km": round(rr.km, 2),
                    "planned_minutes": round(r.planned_minutes, 1),
                    "door_minutes": round(sum(s.service for s in vis), 1),
                    "window_wait": round(sum(s.window_wait for s in rr.stops), 1),
                    "wasted": sum(s.wasted for s in rr.stops),
                })

    def _day_metrics(self, arm: str, day: int, results: list[RouteResult], counts: np.ndarray, notes: list[Note]) -> dict:
        cfg = self.cfg
        visited = [s for rr in results for s in rr.stops]
        pdef = [s for rr in results for s in rr.plan_deferred]
        stops = visited + pdef
        ship = sum(s.n for s in stops)
        deferred = sum(s.deferred for s in stops)
        ok = sum(s.ok for s in stops)
        fail = sum(s.fail for s in stops)
        att = ok + fail
        reasons = {r: 0 for r in REASONS}
        for s in stops:
            for r, n in s.reasons.items():
                reasons[r] += n
        mins = np.array([rr.minutes for rr in results]) if results else np.zeros(1)
        lo, hi = cfg.planning.band
        ends = np.array([rr.end_minute for rr in results]) if results else np.zeros(1) + cfg.planning.start_minute
        deps = np.array([rr.start_minute for rr in results]) if results else np.zeros(1) + cfg.planning.start_minute
        attempted_stops = [s for s in visited if s.deferred == 0]
        stops_v = visited
        planned = np.array([r.planned_minutes for r in self._last_routes]) if getattr(self, "_last_routes", None) else mins
        return {
            "arm": arm, "day": day, "weekday": weekday(day),
            "in_band_planned_share": round(float(((planned >= lo) & (planned <= hi)).mean()), 4),
            "planned_cv": round(float(planned.std() / planned.mean()), 4) if planned.mean() > 0 else 0.0,
            "shipments": ship, "deferred": deferred, "attempted": att, "ok": ok, "fail": fail,
            "first_attempt_rate": round(ok / att, 5) if att else None,
            "preventable_fail": sum(s.preventable_fail for s in stops),
            "fail_by_reason": reasons,
            "couriers": len(results),
            "km": round(sum(rr.km for rr in results), 2),
            "minutes_mean": round(float(mins.mean()), 1),
            "in_band": int(((mins >= lo) & (mins <= hi)).sum()),
            "in_band_share": round(float(((mins >= lo) & (mins <= hi)).mean()), 4),
            # Fazla mesai vardiya bitişinden (saat) sayılır: geç çıkış da fazla mesai yaratır (Faz 5). Sabah kapalıyken = rota − bant üstü.
            "overtime_minutes": round(float(np.clip(ends - shift_end_at(cfg), 0, None).sum()), 1),
            "departure_mean": round(float(deps.mean()), 1),
            "end_mean": round(float(ends.mean()), 1),
            "workload_cv": round(float(mins.std() / mins.mean()), 4) if mins.mean() > 0 else 0.0,
            "door_minutes_per_stop": round(sum(s.service for s in attempted_stops) / max(1, len(attempted_stops)), 3),
            "stops": len(stops),
            "unfamiliar_share": round(sum(s.unfamiliar for s in stops_v) / max(1, len(stops_v)), 4),
            "hinted_stops": sum(s.hinted for s in stops_v),
            "hint_helped": sum(s.hint_helped for s in stops_v),
            "wrong_hint": sum(s.wrong_hint for s in stops_v),
            "memory_coverage": round(sum(s.hinted for s in stops_v) / max(1, len(stops_v)), 4),
            "notes": len(notes),
            "window_hits": sum(s.window_hit for s in stops_v),
            "window_wait_minutes": round(sum(s.window_wait for s in stops_v), 1),
            "wasted_trips": sum(s.wasted for s in stops_v),
            "plan_deferred_stops": len(pdef),
            "revisit_stops": sum(1 for s in stops if s.fail > 0),
            "wrong_deferrals": sum(1 for s in pdef if s.fail),
            "eta_abs_error": round(float(np.abs(mins - planned).mean()), 1) if len(planned) == len(mins) else None,
        }

    def _anchored_day(self, s: ArmState, arm: str, day: int, stops: np.ndarray, counts: np.ndarray, n_av: int,
                      extra: dict[int, float] | None = None):
        """Çekirdek bölgeli plan: kümeler kuryelerin çekirdekleri etrafında; bandı aşan rota varsa bir kurye eklenir.
        extra: adres → ek servis dk (kol D, hafızadan); durak ağırlığına ve planlanan süreye girer."""
        cfg = self.cfg
        pol = self.policies[arm]
        ctx = self._ctx(s, day, use_memory=(arm == "D"))
        cviews = self.courier_views(s, day)
        sv = self.stop_views(day, stops, counts)
        extra = extra or {}
        ew = np.array([extra.get(int(a), 0.0) for a in stops]) if extra else None
        k = n_clusters(cfg, stops, counts, n_av)
        routes: list[Route] = []
        chosen: list[str] = []
        for _ in range(3):
            labels, chosen = pol.plan(ctx, sv, cviews, k, cfg.seed, extra_w=ew)
            routes = [make_route(cfg, self.world, j, stops[labels == j], counts, extra=extra)
                      for j in range(len(chosen)) if (labels == j).any()]
            keep = [j for j in range(len(chosen)) if (labels == j).any()]
            chosen = [chosen[j] for j in keep]
            if max(r.planned_minutes for r in routes) <= cfg.planning.band[1] or k >= n_av:
                break
            k += 1
        for i, (r, cid) in enumerate(zip(routes, chosen)):
            r.id = i
            r.courier = cid
        mapping = {r.id: r.courier for r in routes}
        clusters = self.cluster_views(day, routes, counts)
        validate_mapping(pol.name, mapping, clusters, cviews)
        mat = expected_cost(ctx, clusters, cviews, ctx.memory)
        return routes, AssignmentDecision(mapping=mapping, details={"matrix": mat, "totals": assignment_totals(mat, mapping)})

    def _memory_day(self, s: ArmState, day: int, stops: np.ndarray, counts: np.ndarray, n_av: int):
        """Kol D: hafıza-farkında plan. (rotalar, karar, hasat istatistiği)"""
        cfg, w = self.cfg, self.world
        rc = cfg.routing
        wd = weekday(day)
        mem = s.memory
        on = rc.enabled and mem is not None
        rules0 = mem.rules_for(day, wd, stops) if on else {}
        closed = {a for a, r in rules0.items() if r.closed} if (on and rc.defer_closed) else set()
        kept = np.array([a for a in stops if int(a) not in closed], dtype=np.int64)
        extra = {a: r.extra for a, r in rules0.items() if r.extra > 0} if (on and rc.service_correction) else {}
        routes, dec = self._anchored_day(s, "D", day, kept, counts, n_av, extra)
        time_on = on and rc.time_aware and s.history.time is not None
        finds = self._time_findings(s, day, stops) if time_on else {}
        apply = {a: b for a, b in finds.items() if fits_route(b, rc.time_min_confidence)}
        tstat = {"day": day, "finding": sum(1 for b in finds.values() if b["type"] == "window"),
                 "confirmation": sum(1 for b in finds.values() if b["type"] == "confirmation"), "eligible": len(apply), "route": 0,
                 "carried": 0, "correct": 0, "expected_before": 0.0, "expected_after": 0.0, "unshiftable": 0, "transfer": 0,
                 "next_day": 0, "evening_delivery_point": 0, "transfer_gain": 0.0, "violation": 0}
        lim = repair_limits(cfg)
        by_route: dict[int, dict] = {}
        hv = None
        if mem is not None and cfg.memory.harvest_per_day > 0:
            hv = self._harvest(s, day, routes)
        # Plandan çıkan duraklar en yakın kümeye "bağlanır" (hafızasız planda o rotada olacaklardı).
        attach: dict[int, list[int]] = {r.id: [] for r in routes}
        if closed and routes:
            cen = np.array([w.addr_xy[r.stops].mean(0) for r in routes])
            for a in sorted(closed):
                j = int(np.argmin(((cen - w.addr_xy[a]) ** 2).sum(1)))
                attach[routes[j].id].append(int(a))
        for r in routes:
            allst = np.concatenate([r.stops, np.array(attach[r.id], dtype=np.int64)])
            plain, plain_km = order_route(cfg, w, allst)
            if on:
                rules = mem.rules_for(day, wd, plain)
                for a in plain:
                    b = apply.get(int(a))
                    if b is not None:
                        rules.setdefault(int(a), StopRule()).presence = tuple(b["estimate"])
                        tstat["route"] += 1
                        tstat["correct"] += int(self._finding_true(int(a), wd, b))
                kw = dict(road_factor=cfg.planning.road_factor, mpk=cfg.planning.minutes_per_km,
                          start=self._plan_start("D"), scale=rc.time_scale, margin=rc.window_margin_min,
                          defer_closed=rc.defer_closed, window_repair=rc.window_repair, service_correction=rc.service_correction,
                          revisit_min=rc.time_revisit_min, km_cost_min=rc.time_km_cost_min, min_gain_min=rc.time_min_gain_min,
                          limits=lim)
                xy, svc0 = w.addr_xy[plain], service_minutes(cfg, counts[plain]).astype(float)
                res = plan_route(xy, w.depot_xy, plain, svc0, rules, time_repair=time_on, **kw)
                r.stops, r.km, r.planned_minutes = res["order"], res["km"], res["planned"]
                r.extra.update(plain=plain, plain_km=res["plain_km"], plain_planned=res["plain_planned"],
                               deferred=res["deferred"], deferred_addrs=[d[0] for d in res["deferred"]],
                               changes=res["changes"], extra_service=res["extra"], time_fail=res["time_fail"],
                               limits=res["limits"], time_blocked=res["time_blocked"])
                by_route[r.id] = res
                L = res["limits"]
                if L is not None and L["after_min"] > L["border_min"] + 1e-6:
                    tstat["violation"] += 1
                tm = [c for c in res["changes"] if c["type"] == "time"]
                tstat["carried"] += len(tm)
                tstat["expected_before"] += res["time_fail"]["before"]
                tstat["expected_after"] += res["time_fail"]["after"]
                if tm:
                    nt = plan_route(xy, w.depot_xy, plain, svc0, rules, time_repair=False, **kw)
                    r.extra["notime"] = {"order": nt["order"], "km": nt["km"], "planned": nt["planned"],
                                         "expected_min": (nt["limits"] or {}).get("after_min")}
                    r.extra["time_findings"] = {int(c["address"]): apply[int(c["address"])] for c in tm}
            else:
                r.stops, r.km = plain, plain_km
                r.planned_minutes = plain_km * cfg.planning.minutes_per_km + float(np.sum(service_minutes(cfg, counts[plain])))
                r.extra.update(plain=plain, plain_km=plain_km, plain_planned=r.planned_minutes, deferred=[], deferred_addrs=[],
                               changes=[], extra_service={})
        if time_on and lim is not None and rc.time_alternatives and by_route:
            alts = time_alternatives(by_route, road_factor=cfg.planning.road_factor, mpk=cfg.planning.minutes_per_km,
                                        start=self._plan_start("D"), scale=rc.time_scale, margin=rc.window_margin_min,
                                        limits=lim, min_gain=rc.time_min_gain_min / max(1e-9, rc.time_revisit_min))
            cour = {r.id: r.courier for r in routes}
            for x in alts:
                x["courier"] = cour.get(x["source"])
                x["target_courier"] = cour.get(x["target"]) if x.get("target") is not None else None
                tstat["unshiftable"] += 1
                tstat[x["option"]] += 1
                tstat["transfer_gain"] += float(x.get("gain_stop") or 0.0)
            s.time_alts[day] = alts
        if time_on:
            tstat["transfer_gain"] = round(tstat["transfer_gain"], 3)
            tstat["expected_before"] = round(tstat["expected_before"], 2)
            tstat["expected_after"] = round(tstat["expected_after"], 2)
            s.time_stats.append(tstat)
        return routes, dec, hv

    def _time_findings(self, s: ArmState, day: int, addrs: np.ndarray) -> dict[int, dict]:
        """Teslim zamanı bulguları: yalnız bugünden ÖNCEKİ kayıtlar (History.zaman), adres türü önceliyle büzme."""
        z = s.history.time
        return time_findings(z.att, z.abs, self.kind_idx, len(ADDRESS_KINDS), addrs, weekday(day), self.zparams)

    def _finding_true(self, a: int, wd: int, b: dict) -> bool:
        """Gizli gerçekle doğrulama (yalnız ölçüm): kötü dilimde gerçek bulunamama, önerilen dilimden en az 0,10 yüksek mi?"""
        pk = p_absent(self.cfg, self.world, a, wd, SLOT_MID[b["bad"]])
        pi = p_absent(self.cfg, self.world, a, wd, SLOT_MID[b["good"]])
        return pk - pi >= 0.1

    def _harvest(self, s: ArmState, day: int, routes: list[Route]) -> dict:
        w, thr = self.world, self.cfg.familiarity.unfamiliar_below
        targets = []
        for r in routes:
            for a in r.stops:
                b = int(w.addr_block[a])
                if s.fam.value(r.courier, b, day) < thr and not s.memory.store.has_entry(int(a), day):
                    targets.append((int(a), b, r.courier))
        on_duty = {r.courier for r in routes}
        answerers = {c: self.cfg.memory.harvest_per_senior for c in sorted(on_duty) if self.by_id[c].kind != "borrowed"}
        departing = {}
        for c in self.couriers:
            if c.end_day is not None and day < c.end_day <= day + 3 and c.available(day):
                departing[c.id] = [b for b in sorted(s.fam.blocks_of(c.id)) if s.fam.value(c.id, b, day) >= 0.5]
        hv = s.memory.harvest(w, day, targets, answerers, s.fam, s.known, s.history.addr_days, departing)
        hv["day"] = day
        hv["target_stop"] = len(targets)
        s.harvest_stats.append(hv)
        return hv

    @staticmethod
    def _route_summary(rr: RouteResult) -> dict:
        allst = rr.stops + rr.plan_deferred
        return {"minutes": round(rr.minutes, 1), "km": round(rr.km, 2), "ok": sum(x.ok for x in allst),
                "fail": sum(x.fail for x in allst), "preventable_fail": sum(x.preventable_fail for x in allst),
                "deferred": sum(x.deferred for x in allst), "window_hits": sum(x.window_hit for x in rr.stops),
                "window_wait": round(sum(x.window_wait for x in rr.stops), 1), "wasted": sum(x.wasted for x in rr.stops),
                "stops": len(allst), "recipient_absent": sum(x.reasons.get("recipient_absent", 0) for x in allst),
                "revisit": sum(1 for x in allst if x.fail > 0), "start": round(rr.start_minute, 1), "end": round(rr.end_minute, 1)}

    def _counterfactuals(self, s: ArmState, day: int, routes: list[Route], counts: np.ndarray, streams) -> dict[int, dict]:
        """Aynı kurye, aynı duraklar, aynı rastgele sayılar: hafızasız ve yalnız-ipucu yürütmeleri (durum değişmez)."""
        cfg, w = self.cfg, self.world
        wd = weekday(day)
        ctx = self._ctx(s, day, use_memory=True)
        out = {}
        for r in routes:
            plain = r.extra.get("plain")
            if plain is None:
                continue
            c = self.by_id[r.courier]
            pr = Route(id=r.id, stops=plain, km=r.extra["plain_km"], planned_minutes=r.extra["plain_planned"], courier=r.courier)
            dep = self._departure("D", day, c.id)          # karşı-olgular D'nin gerçek çıkışıyla (yalnız hafıza değişir)
            none = execute_route(cfg, w, pr, c, day, wd, counts, streams, s.fam, s.known[c.id], None, start=dep)
            hints = s.memory.hints_for(ctx, c.id, self.stop_views(day, plain, counts)) if s.memory is not None else None
            only = execute_route(cfg, w, pr, c, day, wd, counts, streams, s.fam, s.known[c.id], hints, start=dep)
            out[r.id] = {"courier": c.id, "kind": c.kind, "planned_plain": round(r.extra["plain_planned"], 1),
                         "planned": round(r.planned_minutes, 1), "memoryless": self._route_summary(none),
                         "hint_only": self._route_summary(only)}
            nt = r.extra.get("notime")
            if nt is not None:
                # Zamansız: aynı hafızalı rota (erteleme, pencere, servis düzeltmesi) ama zaman onarımı yok; aynı ipuçları.
                hv = s.memory.hints_for(ctx, c.id, self.stop_views(day, nt["order"], counts)) if s.memory is not None else None
                ntr = Route(id=r.id, stops=nt["order"], km=nt["km"], planned_minutes=nt["planned"], courier=r.courier,
                            extra={"deferred_addrs": r.extra.get("deferred_addrs", [])})
                rr = execute_route(cfg, w, ntr, c, day, wd, counts, streams, s.fam, s.known[c.id], hv, start=dep)
                out[r.id]["no_time"] = self._route_summary(rr)
                moved = set(r.extra.get("time_findings", {}))
                out[r.id]["time_stops"] = {int(x.address): self._stop_outcome(x) for x in rr.stops if int(x.address) in moved}
            sb = cfg.morning
            if sb.enabled and "D" in sb.presorted_arms and sb.presorted_min != sb.current_min:
                # Faz 5: aynı hafızalı rota ve ipuçları, aynı rastgele sayılar; çıkış bugünkü sabahla (ayrıştırma kuryede).
                hb = s.memory.hints_for(ctx, c.id, self.stop_views(day, r.stops, counts)) if s.memory is not None else None
                rb = execute_route(cfg, w, r, c, day, wd, counts, streams, s.fam, s.known[c.id], hb,
                                   start=self._departure("D", day, c.id, mins=sb.current_min))
                out[r.id]["current_morning"] = self._route_summary(rb)
        return out

    @staticmethod
    def _stop_outcome(x) -> dict:
        reason = max(x.reasons, key=x.reasons.get) if x.reasons else None
        return {"arrival": int(round(x.arrival)), "ok": x.ok, "fail": x.fail, "reason": reason}

    # ------------------------------------------------------------------ ana döngü
    def run(self, progress: Callable[[str], None] | None = None) -> SimResult:
        t0 = time.time()
        cfg = self.cfg
        say = progress or (lambda m: None)
        warm = self._new_state("W")
        memory = MemoryOraclePolicy(cfg)
        warm.memory = memory
        counts_by_day: dict[int, np.ndarray] = {}

        for day in range(cfg.days.warmup):
            counts = demand_for_day(cfg, self.world, day, self.rates)
            stops = np.flatnonzero(counts)
            st = day_streams(cfg.seed, day, counts)
            self._update_zone_owners(warm, day)
            routes = plan_fixed(cfg, self.world, stops, counts, self.zone_of, warm.zone_owner, self.by_id, day, self.centroids)
            self._execute(warm, day, routes, counts, st, use_hints=False,
                          ingest=memory if cfg.memory.seed_from_warmup else None, record=False)
        say(f"ısınma bitti ({cfg.days.warmup} gün, {time.time() - t0:.1f} sn)")
        self._seed_border_familiarity(warm)

        arms: dict[str, ArmState] = {}
        for a in ARMS:
            s = copy.deepcopy(warm)
            s.arm = a
            s.notes = []
            s.parse_stats = []
            if a != "D":
                s.memory = None
            arms[a] = s

        eval_days = list(range(cfg.days.warmup, cfg.n_days))
        for day in eval_days:
            counts = demand_for_day(cfg, self.world, day, self.rates)
            counts_by_day[day] = counts
            stops = np.flatnonzero(counts)
            st = day_streams(cfg.seed, day, counts)
            n_av = sum(1 for c in self.couriers if c.available(day))
            dyn = plan_dynamic(cfg, self.world, stops, counts, n_av, rng(cfg.seed, day, 99))
            clusters = self.cluster_views(day, dyn, counts)
            for a in ARMS:
                s = arms[a]
                if a == "A":
                    self._update_zone_owners(s, day)
                    routes = plan_fixed(cfg, self.world, stops, counts, self.zone_of, s.zone_owner, self.by_id, day, self.centroids)
                elif a == "B":
                    pol = self.policies[a]
                    ctx = self._ctx(s, day, use_memory=False)
                    cviews = self.courier_views(s, day)
                    dec = pol.assign(ctx, clusters, cviews)
                    validate_mapping(pol.name, dec.mapping, clusters, cviews)
                    routes = copy.deepcopy(dyn)
                    for r in routes:
                        r.courier = dec.mapping[r.id]
                    s.decisions[day] = dec
                elif a == "C":
                    routes, dec = self._anchored_day(s, a, day, stops, counts, n_av)
                    s.decisions[day] = dec
                else:
                    # D: hafıza planı değiştirir (C'nin rotası kopyalanmaz).
                    routes, dec, _ = self._memory_day(s, day, stops, counts, n_av)
                    s.decisions[day] = dec
                if a == "D" and s.memory is not None:
                    s.memory_snapshots[day] = s.memory.store.export(day)      # hasattan sonra: brifing bunu görür
                    s.counterfactuals[day] = self._counterfactuals(s, day, routes, counts, st)
                self._execute(s, day, routes, counts, st, use_hints=(a == "D"),
                              ingest=s.memory if a == "D" else None, record=True)
                if a == "D" and s.memory is not None:
                    for rr in s.results[day]:
                        cf = s.counterfactuals[day].get(rr.route_id)
                        if cf is not None:
                            cf["memory"] = self._route_summary(rr)
                            if "no_time" not in cf:
                                cf["no_time"] = cf["memory"]          # zaman onarımı bu rotayı değiştirmedi
                            else:
                                zd = cf["time_stops"]
                                cf["time_stops"] = {a: {"no_time": zd[a], "memory": self._stop_outcome(x)}
                                                         for x in rr.stops for a in [int(x.address)] if a in zd}
            say(f"gün {day - cfg.days.warmup + 1}/{cfg.days.eval} ({time.time() - t0:.1f} sn)")

        return SimResult(cfg=cfg, world=self.world, couriers=self.couriers, zone_of=self.zone_of, arms=arms,
                         warm=warm, eval_days=eval_days, counts=counts_by_day, elapsed=time.time() - t0)

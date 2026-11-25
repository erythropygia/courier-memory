"""Deterministik atama politikaları: geçmişe bakmadan (B) ve uyuma göre (C/D)."""
from __future__ import annotations

from typing import Sequence

import numpy as np

from ..estimation import assignment_totals, expected_cost, solve_assignment
from ..rng import S_ASSIGN, rng
from .base import AssignmentDecision, ClusterView, CourierView, DayContext


class BlindPolicy:
    """Kol B: kurye–küme ataması geçmişe bakmadan, tohumlu rastgele."""

    name = "blind"

    def __init__(self, seed: int):
        self.seed = seed

    def assign(self, ctx: DayContext, clusters: Sequence[ClusterView], couriers: Sequence[CourierView]) -> AssignmentDecision:
        av = sorted(c.id for c in couriers if c.available)
        perm = rng(self.seed, ctx.day, S_ASSIGN).permutation(len(av))
        return AssignmentDecision(mapping={cl.id: av[int(perm[i])] for i, cl in enumerate(clusters)})


class FitAssignPolicy:
    """Kol C/D: beklenen başarısızlık + süre maliyetiyle Hungarian. D'de hafıza kapsamı maliyete girer."""

    def __init__(self, name: str = "fit_assign", use_memory: bool = False):
        self.name = name
        self.use_memory = use_memory

    def assign(self, ctx: DayContext, clusters: Sequence[ClusterView], couriers: Sequence[CourierView]) -> AssignmentDecision:
        mem = ctx.memory if self.use_memory else None
        mat = expected_cost(ctx, clusters, couriers, mem)
        mapping = solve_assignment(mat["cost"], mat["couriers"], mat["clusters"])
        return AssignmentDecision(mapping=mapping, details={"matrix": mat, "totals": assignment_totals(mat, mapping)})


class AnchoredPlanPolicy:
    """Kol C/D: çekirdek bölgeli dinamik plan.

    Her kuryenin çekirdek bölgesi ziyaret geçmişinden öğrenilir (tanıdıklık ≥ anchor_min_f olan bloklar). Kümeler
    günün talebine göre yeniden çizilir ama her küme bir kuryenin çekirdeği etrafında kurulur: tanıdık bloktaki durak
    o kuryenin kümesine daha "yakın" sayılır. Böylece kurye çoğunlukla kendi bölgesinde kalır; yalnız sınırlar ve
    fazla iş esner. Hacim düşükse en az talepli çekirdekler komşulara katılır; hacim yüksekse çekirdeksiz (yeni/ödünç/
    yedek) kuryeler esnek kümelere gider. Performans puanı kullanılmaz: belirleyici olan süreklilik.
    """

    def __init__(self, name: str, bonus_km: float, alpha: float, slack: float, min_f: float, iters: int, use_memory: bool = False):
        self.name, self.bonus_km, self.alpha, self.slack, self.min_f, self.iters = name, bonus_km, alpha, slack, min_f, iters
        self.use_memory = use_memory

    def plan(self, ctx: DayContext, stops: Sequence, couriers: Sequence[CourierView], k: int, seed: int,
             extra_w: np.ndarray | None = None) -> tuple[np.ndarray, list[str]]:
        """extra_w: durak başına ek servis dakikası (kol D: hafızadaki bilinen püf noktalarının kalan süresi)."""
        av = [c for c in couriers if c.available]
        n = len(stops)
        xy = np.array([[s.x, s.y] for s in stops])
        blocks = np.array([s.block for s in stops], dtype=np.int64)
        w = np.array([ctx.service_per_stop + ctx.service_per_shipment * s.n_shipments for s in stops]) + 1.2
        if extra_w is not None:
            w = w + np.asarray(extra_w, dtype=float)
        bxy = np.asarray(ctx.block_xy)
        cores: dict[str, tuple[np.ndarray, dict[int, float]]] = {}
        for c in av:
            bs, fs = ctx.history.familiar_blocks(c.id, ctx.day, self.min_f)
            if len(bs):
                cores[c.id] = (np.average(bxy[bs], weights=fs, axis=0), dict(zip(bs.tolist(), fs.tolist())))
        # Bugünkü talebin çekirdeklere düşen payı → hangi kuryeler çalışır
        score = {cid: float(sum(w[i] for i in range(n) if fam.get(int(blocks[i]), 0.0) >= 0.3)) for cid, (_, fam) in cores.items()}
        core_ids = sorted(cores, key=lambda c: -score[c])
        chosen = core_ids[:k]
        rest = [c for c in av if c.id not in chosen]
        # Çekirdeksiz kuryeler: önce yedek/kıdemli/yeni; ödünçlerde bu şubede daha çok gün çalışmış olan (gözlemlenebilir).
        rest.sort(key=lambda c: (("reserve", "senior", "new", "borrowed").index(c.kind) if c.kind in ("reserve", "senior", "new", "borrowed") else 9,
                                 -c.days_in_branch))
        while len(chosen) < k and rest:
            chosen.append(rest.pop(0).id)
        k = len(chosen)
        g = np.random.default_rng([seed, ctx.day, 77])
        seeds = np.zeros((k, 2))
        F = np.zeros((n, k))
        for j, cid in enumerate(chosen):
            if cid in cores:
                seeds[j] = cores[cid][0]
                fam = cores[cid][1]
                F[:, j] = [fam.get(int(b), 0.0) for b in blocks]
        free = [j for j, cid in enumerate(chosen) if cid not in cores]
        for j in free:                                   # çekirdeksiz kurye: en az kapsanan yoğun alana tohum
            have = [seeds[i] for i in range(k) if i not in free or i < j]
            d2 = ((xy[:, None, :] - np.array(have)[None, :, :]) ** 2).sum(-1).min(1) if have else np.ones(n)
            p = d2 * w
            seeds[j] = xy[int(g.choice(n, p=p / p.sum()))] if p.sum() > 0 else xy[int(g.integers(n))]
        C = seeds.copy()
        cap = w.sum() / k * self.slack
        labels = np.zeros(n, dtype=np.int64)
        for _ in range(self.iters):
            D = np.sqrt(((xy[:, None, :] - C[None, :, :]) ** 2).sum(-1)) - self.bonus_km * F
            srt = np.sort(D, axis=1)
            regret = srt[:, 1] - srt[:, 0] if k > 1 else np.zeros(n)
            order = np.argsort(-regret, kind="stable")
            pref = np.argsort(D, axis=1, kind="stable")
            load = np.zeros(k)
            for i in order:
                ch = -1
                for c in pref[i]:
                    if load[c] + w[i] <= cap:
                        ch = int(c)
                        break
                if ch < 0:
                    ch = int(np.argmin(load))
                labels[i] = ch
                load[ch] += w[i]
            for j in range(k):
                m = labels == j
                if m.any():
                    mean = (xy[m] * w[m, None]).sum(0) / w[m].sum()
                    C[j] = self.alpha * seeds[j] + (1 - self.alpha) * mean if chosen[j] in cores else mean
        return labels, chosen

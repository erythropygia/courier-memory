"""Kurye–bölge uyum tahmincisi ve atama araçları (saf fonksiyonlar).

Kuryeye tek bir "performans puanı" verilmez. Uyum, kurye×blok düzeyinde ve bloğun genel oranına göre
standartlaştırılarak tahmin edilir (dolaylı standartlaştırma + büzülme). Zor bölgede çalışan kurye bu
yüzden haksız yere düşük görünmez.

Bu fonksiyonlar Atama Ajanı'nın araçlarıdır; simülatördeki C/D kolları da aynılarını kullanır.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from .history import HistoryReader
from .policies.base import ClusterView, CourierView, MemoryReader


@dataclass
class Estimates:
    r_fam: np.ndarray            # blok başına tanıdık kuryede kuryeye bağlı başarısızlık oranı (büzülmüş)
    r_absent: np.ndarray         # blok başına "alıcı yok" oranı (kuryeden bağımsız)
    r_global: float
    eta: float                   # yabancı blokta kuryeye bağlı oranın göreli artışı
    nav_min: float               # yabancı blokta ek dakika
    rho: dict[str, float]        # kurye etkisi (1 = blok ortalaması)
    speed: dict[str, float]      # kapıda süre çarpanı tahmini


def estimate(h: HistoryReader, couriers: Sequence[str], a_cfg) -> Estimates:
    """Neden kodları sayesinde kuryeden bağımsız başarısızlık (alıcı yok) ayrılır; kurye etkisi yalnız
    kuryeye bağlı başarısızlıklardan, bloğun tanıdık-kurye oranına göre standartlaştırılarak tahmin edilir."""
    unf_att, unf_rel, fam_att, fam_rel = h.split_counts()
    att, fail = h.block_counts()
    rel = h.block_relevant_fails()
    absent = fail - rel
    rg = float(fail.sum() / max(att.sum(), 1))
    k = a_cfg.shrink_block
    abs_g = float(absent.sum() / max(att.sum(), 1))
    r_absent = (absent + k * abs_g) / (att + k)
    fam_g = float(fam_rel.sum() / max(fam_att.sum(), 1)) if fam_att.sum() else float(rel.sum() / max(att.sum(), 1))
    # Blok türü düzeyinde havuzlanmış oran: farklı kuryelerin benzer bloklarını karşılaştırır. Sabit bölgede her
    # bloğa tek kurye gittiği için blok kendi oranıyla standartlaştırılırsa kurye etkisi bölgeden ayrılamaz.
    if h.block_kind is not None:
        kinds = np.array(h.block_kind)
        r_kind = np.full(len(kinds), fam_g)
        for kd in set(h.block_kind):
            m = kinds == kd
            r_kind[m] = (fam_rel[m].sum() + k * fam_g) / (fam_att[m].sum() + k)
    else:
        r_kind = np.full(len(fam_att), fam_g)
    r_fam = (fam_rel + k * r_kind) / (fam_att + k)

    # Yabancılık çarpanı: yabancı denemelerde gözlenen / tanıdık blok oranıyla beklenen.
    e_unf = float((unf_att * r_fam).sum())
    o_unf = float(unf_rel.sum())
    n_unf = float(unf_att.sum())
    eta_raw = (o_unf / e_unf - 1.0) if e_unf > 0 else a_cfg.eta_prior
    w = a_cfg.eta_prior_weight
    eta = max(0.0, (eta_raw * n_unf + a_cfg.eta_prior * w) / (n_unf + w))

    (x_unf, n_u), (x_fam, n_f) = h.extra_minutes()
    nav_raw = (x_unf / n_u if n_u else 0.0) - (x_fam / n_f if n_f else 0.0)
    nav = max(0.0, (nav_raw * n_u + 1.0 * 50) / (n_u + 50))

    rho: dict[str, float] = {}
    speed: dict[str, float] = {}
    kc = a_cfg.shrink_courier
    for c in couriers:
        cb = h.courier_block_attempts(c)
        expected = sum(n * float(r_kind[b]) for b, n in cb.items())
        expected += eta * sum(n * float(r_kind[b]) for b, n in h.courier_block_unfamiliar_attempts(c).items())
        rho[c] = float(np.clip((h.courier_relevant_fails(c) + kc) / (expected + kc), 0.4, 2.5))
        sa, sb = h.courier_service(c)
        ks = a_cfg.shrink_speed * 3.0
        speed[c] = float(np.clip((sa + ks) / (sb + ks), 0.7, 1.5)) if sb or sa else 1.0
    return Estimates(r_fam=r_fam, r_absent=r_absent, r_global=rg, eta=eta, nav_min=nav, rho=rho, speed=speed)


def expected_cost(ctx, clusters: Sequence[ClusterView], couriers: Sequence[CourierView],
                  memory: MemoryReader | None, est: Estimates | None = None) -> dict:
    """Kurye × küme beklenen başarısızlık, süre ve maliyet matrisleri."""
    a_cfg = ctx.assignment_cfg
    av = [c for c in couriers if c.available]
    ids = [c.id for c in av]
    est = est or estimate(ctx.history, ids, a_cfg)
    nC, nK = len(av), len(clusters)
    exp_fail = np.zeros((nC, nK))
    exp_min = np.zeros((nC, nK))
    unf = np.zeros((nC, nK), dtype=np.int64)
    cov_unf = np.zeros((nC, nK), dtype=np.int64)
    relief = a_cfg.memory_relief
    for k, cl in enumerate(clusters):
        blocks = np.array([s.block for s in cl.stops], dtype=np.int64)
        n = np.array([s.n_shipments for s in cl.stops], dtype=float)
        m = np.array([1.0 if memory is not None and memory.has_entry(s.address, ctx.day) else 0.0 for s in cl.stops])
        base_min = ctx.service_per_stop + ctx.service_per_shipment * n
        r = est.r_fam[blocks]
        r0 = est.r_absent[blocks]
        for i, c in enumerate(av):
            f = ctx.history.familiarity_vec(c.id, blocks, ctx.day)
            u = (1.0 - f) * (1.0 - relief * m)
            p = np.clip(r0 + r * est.rho.get(c.id, 1.0) * (1.0 + est.eta * u), 0, 0.95)
            exp_fail[i, k] = float((p * n).sum())
            exp_min[i, k] = float((base_min * est.speed.get(c.id, 1.0) + est.nav_min * u).sum())
            is_unf = f < ctx.unfamiliar_below
            unf[i, k] = int(is_unf.sum())
            cov_unf[i, k] = int((is_unf & (m > 0)).sum())
    cost = a_cfg.w_fail * exp_fail + a_cfg.w_time * exp_min
    return {"couriers": ids, "clusters": [c.id for c in clusters], "exp_fail": exp_fail, "exp_min": exp_min,
            "unfamiliar": unf, "covered_unfamiliar": cov_unf, "cost": cost,
            "estimates": {"eta": est.eta, "nav_min": est.nav_min, "rho": est.rho, "speed": est.speed}}


def solve_assignment(cost: np.ndarray, courier_ids: Sequence[str], cluster_ids: Sequence[int],
                     exclude: set[str] | None = None, fixed: dict[int, str] | None = None) -> dict[int, str]:
    """Hungarian. `exclude`: atanmayacak kuryeler. `fixed`: zorunlu küme→kurye eşlemeleri."""
    exclude = set(exclude or ())
    fixed = dict(fixed or {})
    out = dict(fixed)
    rows = [i for i, c in enumerate(courier_ids) if c not in exclude and c not in fixed.values()]
    cols = [j for j, k in enumerate(cluster_ids) if k not in fixed]
    if len(rows) < len(cols):
        raise ValueError(f"Yeterli kurye yok: {len(rows)} kurye, {len(cols)} küme")
    if cols:
        sub = cost[np.ix_(rows, cols)]
        ri, ci = linear_sum_assignment(sub)
        for a, b in zip(ri, ci):
            out[cluster_ids[cols[b]]] = courier_ids[rows[a]]
    return out


def assignment_totals(mat: dict, mapping: dict[int, str]) -> dict:
    ci = {c: i for i, c in enumerate(mat["couriers"])}
    ki = {k: j for j, k in enumerate(mat["clusters"])}
    tot = {"exp_fail": 0.0, "exp_min": 0.0, "unfamiliar": 0, "covered_unfamiliar": 0, "cost": 0.0}
    for k, c in mapping.items():
        i, j = ci[c], ki[k]
        for key in tot:
            tot[key] += float(mat[key][i, j])
    return tot


def report_recovery(h: HistoryReader, true_skill: dict[str, float], a_cfg, min_attempts: int = 200) -> dict:
    """Tahmin edilen kurye etkisi ile gizli gerçek becerinin sıra korelasyonu; naif oranla karşılaştırma."""
    from scipy.stats import spearmanr

    cs = [c for c in true_skill if h.courier_counts(c)[0] >= min_attempts]
    if len(cs) < 4:
        return {"n": len(cs), "spearman_estimate": None, "spearman_naive": None}
    est = estimate(h, cs, a_cfg)
    truth = [true_skill[c] for c in cs]
    rho = [est.rho[c] for c in cs]
    naive = [h.courier_counts(c)[1] / h.courier_counts(c)[0] for c in cs]   # ham oran: bölge ve nedenden arındırılmamış
    s_est = spearmanr(rho, truth).statistic
    s_naive = spearmanr(naive, truth).statistic
    return {"n": len(cs), "spearman_estimate": round(float(s_est), 3), "spearman_naive": round(float(s_naive), 3),
            "eta_hat": round(est.eta, 3), "nav_min_hat": round(est.nav_min, 2)}

"""Çalıştırma çıktıları (sözleşme: docs/sozlesmeler.md → "Çalıştırma klasörü").

Gözlemlenebilir dosyalar arayüz ve ajanlar içindir. Gizli gerçek dosyaları (`truth.json`,
`notes_truth.json`) açıkça ayrıdır ve yalnız değerlendirmede kullanılır.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
import yaml

from .config import config_to_dict
from .demand import WEEKDAY_TR, weekday
from .engine import ARM_LABELS, ARMS, SimResult
from .estimation import report_recovery
from .history import HistoryReader
from .outcome import PREVENTABLE, REASONS
from .config import ADDRESS_KINDS
from .delivery_time import (SLOT_NAMES, Params as TimeParams, alternative_text, counts_from_log, slot, proposal_text,
                            sms_text, time_findings)

STOP_FIELDS = ["address", "lat", "lng", "n", "eta", "ok", "fail", "deferred", "reason", "hint", "unfamiliar"]


def _pkg_version() -> str:
    try:
        return version("courier-memory")
    except PackageNotFoundError:
        return "dev"


def run_id_for(res: SimResult) -> str:
    cfgd = config_to_dict(res.cfg)
    h = hashlib.sha1(json.dumps(cfgd, sort_keys=True).encode()).hexdigest()[:8]
    sc = "+".join(res.cfg.scenarios) if res.cfg.scenarios else "normal"
    return f"{sc}-s{res.cfg.seed}-{h}"


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False), encoding="utf-8")


def _r(x: float, n: int) -> float:
    return float(round(float(x), n))


def summarize(res: SimResult) -> dict:
    out = {"app_data": True, "arms": {}}
    for a in ARMS:
        d = res.arms[a].daily
        att = sum(x["attempted"] for x in d)
        ok = sum(x["ok"] for x in d)
        reasons = {r: sum(x["fail_by_reason"][r] for x in d) for r in REASONS}
        n = len(d)
        out["arms"][a] = {
            "label": ARM_LABELS[a],
            "first_attempt_rate": round(ok / att, 5) if att else None,
            "attempted": att, "ok": ok, "fail": att - ok,
            "shipments": sum(x["shipments"] for x in d),
            "deferred": sum(x["deferred"] for x in d),
            "preventable_fail": sum(x["preventable_fail"] for x in d),
            "fail_by_reason": reasons,
            "couriers_per_day": round(sum(x["couriers"] for x in d) / n, 2),
            "vehicle_days": sum(x["couriers"] for x in d),
            "km_per_day": round(sum(x["km"] for x in d) / n, 1),
            "km_total": round(sum(x["km"] for x in d), 1),
            "in_band_share": round(sum(x["in_band"] for x in d) / max(1, sum(x["couriers"] for x in d)), 4),
            "in_band_planned_share": round(sum(x["in_band_planned_share"] * x["couriers"] for x in d) / max(1, sum(x["couriers"] for x in d)), 4),
            "planned_cv": round(sum(x["planned_cv"] for x in d) / n, 4),
            "overtime_minutes_per_day": round(sum(x["overtime_minutes"] for x in d) / n, 1),
            "route_minutes_per_day": round(sum(x["minutes_mean"] * x["couriers"] for x in d) / n, 1),
            "workload_cv": round(sum(x["workload_cv"] for x in d) / n, 4),
            "door_minutes_per_stop": round(sum(x["door_minutes_per_stop"] for x in d) / n, 3),
            "unfamiliar_share": round(sum(x["unfamiliar_share"] for x in d) / n, 4),
            "memory_coverage": round(sum(x["memory_coverage"] for x in d) / n, 4),
            "hint_helped": sum(x["hint_helped"] for x in d),
            "wrong_hint": sum(x["wrong_hint"] for x in d),
            "notes": sum(x["notes"] for x in d),
            "window_hits_per_day": round(sum(x.get("window_hits", 0) for x in d) / n, 2),
            "window_wait_minutes_per_day": round(sum(x.get("window_wait_minutes", 0) for x in d) / n, 1),
            "wasted_trips_per_day": round(sum(x.get("wasted_trips", 0) for x in d) / n, 2),
            "plan_deferred_stops": sum(x.get("plan_deferred_stops", 0) for x in d),
            "wrong_deferrals": sum(x.get("wrong_deferrals", 0) for x in d),
            "eta_abs_error": round(sum(x.get("eta_abs_error") or 0 for x in d) / n, 1),
            "recipient_absent_per_day": round(reasons["recipient_absent"] / n, 2),
            "revisit_stops_per_day": round(sum(x.get("revisit_stops", 0) for x in d) / n, 2),
            "departure_mean": round(sum(x.get("departure_mean", res.cfg.planning.start_minute) for x in d) / n, 1),
            "end_mean": round(sum(x.get("end_mean", 0) for x in d) / n, 1),
        }
    A = out["arms"]

    def delta(a: str, b: str) -> dict:
        return {
            "first_attempt_pp": round(100 * (A[a]["first_attempt_rate"] - A[b]["first_attempt_rate"]), 2),
            "preventable_fail_pct": round(100 * (A[a]["preventable_fail"] / max(1, A[b]["preventable_fail"]) - 1), 1),
            "vehicle_days_pct": round(100 * (A[a]["vehicle_days"] / max(1, A[b]["vehicle_days"]) - 1), 1),
            "km_pct": round(100 * (A[a]["km_total"] / max(1, A[b]["km_total"]) - 1), 1),
        }
    out["deltas"] = {"C_vs_B": delta("C", "B"), "D_vs_C": delta("D", "C"), "D_vs_B": delta("D", "B"),
                     "D_vs_A": delta("D", "A"), "B_vs_A": delta("B", "A")}
    out["preventable_reasons"] = list(PREVENTABLE)
    out["memory_routing"] = memory_routing_summary(res)
    hv = res.arms["D"].harvest_stats
    out["harvest"] = {k: sum(x.get(k, 0) for x in hv) for k in ("question", "handover", "answer", "record", "no_info", "falling", "target_stop")}
    out["harvest"]["day"] = len(hv)
    out["time_analysis"] = time_summary(res)
    out["morning"] = morning_summary(res)
    return out


def morning_summary(res: SimResult) -> dict:
    """Faz 5: şubeden çıkış. Kol başına ortalama çıkış ve dönüş; kol D'de aynı rotanın bugünkü sabahla karşı-olgusu
    (aynı plan, ipuçları ve rastgele sayılar; yalnız çıkış saati farklı). Ölçülen: fazla mesai (vardiya bitişinden),
    başarısız, alıcı yok, dönüş saati. Sabah süreleri saha bilgisidir (VARSAYIM)."""
    cfg = res.cfg
    sb = cfg.morning
    se = float(cfg.planning.start_minute) + float(cfg.planning.band[1])
    out = {"enabled": bool(sb.enabled), "shift_start": int(cfg.planning.start_minute), "shift_end": int(se),
           "current_min": sb.current_min, "presorted_min": sb.presorted_min, "deviation_min": sb.deviation_min,
           "presorted_arms": list(sb.presorted_arms),
           "arms": {a: {"departure_mean": round(sum(x.get("departure_mean", cfg.planning.start_minute) for x in res.arms[a].daily)
                                            / max(1, len(res.arms[a].daily)), 1),
                          "return_mean": round(sum(x.get("end_mean", 0) for x in res.arms[a].daily) / max(1, len(res.arms[a].daily)), 1)}
                      for a in ARMS},
           "counterfactual": None,
           "note": "Sabah süreleri (bugünkü süreç ~90 dk, ayrıştırma okutmaya gömülünce ~30 dk) şube sahibinin saha bilgisidir; "
                  "VARSAYIM, büyüklüğü pilot ölçer. Karşı-olgu: kol D'nin aynı rotası bugünkü sabahla."}
    cf = res.arms["D"].counterfactuals
    keys = ("fail", "preventable_fail", "recipient_absent", "revisit", "minutes", "ok")
    tot = {"memory": {k: 0.0 for k in keys}, "current_morning": {k: 0.0 for k in keys}}
    ot = {"memory": 0.0, "current_morning": 0.0}
    end = {"memory": [], "current_morning": []}
    dep = {"memory": [], "current_morning": []}
    n_days = 0
    for day, rows in cf.items():
        if not any("current_morning" in r for r in rows.values()):
            continue
        n_days += 1
        for r in rows.values():
            if "current_morning" not in r or "memory" not in r:
                continue
            for v in ("memory", "current_morning"):
                x = r[v]
                for k in keys:
                    tot[v][k] += float(x.get(k, 0))
                ot[v] += max(0.0, float(x["end"]) - se)
                end[v].append(float(x["end"]))
                dep[v].append(float(x["start"]))
    if n_days:
        per_day = {v: {**{k: round(tot[v][k] / n_days, 2) for k in keys}, "overtime_min": round(ot[v] / n_days, 1),
                   "departure_mean": round(float(np.mean(dep[v])), 1), "return_mean": round(float(np.mean(end[v])), 1),
                   "after_shift_returning_share": round(float(np.mean(np.array(end[v]) > se)), 4)}
               for v in ("memory", "current_morning")}
        out["counterfactual"] = {"day": n_days, "daily": per_day,
                             "diff_daily": {k: round(per_day["memory"][k] - per_day["current_morning"][k], 2)
                                             for k in ("fail", "preventable_fail", "recipient_absent", "revisit", "minutes", "overtime_min",
                                                       "departure_mean", "return_mean", "after_shift_returning_share")}}
    return out


def time_summary(res: SimResult) -> dict:
    """Teslim zamanı analizinin rotaya katkısı (kol D): aynı hafızalı rota, zaman onarımı var ↔ yok (aynı rastgele sayılar).

    `carried_stops`: zaman onarımının taşıdığı duraklarda gerçekleşen sonuç (zamansız ↔ zaman-farkında).
    `accuracy`: rotaya alınan bulguların gizli gerçekle uyumu (kötü dilimde gerçek bulunamama önerilenden ≥ 10 puan yüksek).
    """
    D = res.arms["D"]
    ts = D.time_stats
    nd = max(1, len(ts))
    keys = ("finding", "confirmation", "eligible", "route", "carried", "correct", "expected_before", "expected_after", "unshiftable",
            "transfer", "next_day", "evening_delivery_point", "transfer_gain")
    per_day = {k: round(sum(x.get(k, 0) for x in ts) / nd, 2) for k in keys}
    m = ("fail", "recipient_absent", "revisit", "km", "minutes", "preventable_fail")
    tot = {v: {k: 0.0 for k in m} for v in ("no_time", "memory")}
    over = {"no_time": 0.0, "memory": 0.0}
    hi = res.cfg.planning.band[1]
    mv = {"stop": 0, "fails_no_time": 0, "fails_memory": 0, "route": 0}
    plan = {"no_time": 0.0, "memory": 0.0}
    expected = {"no_time": 0.0, "memory": 0.0}
    ot_up = {"route": 0, "remaining": 0, "max_increase_min": 0.0}
    for day, routes in D.counterfactuals.items():
        rmap = {r.id: r for r in D.routes.get(day, [])}
        for rid, x in routes.items():
            if "memory" not in x:
                continue
            for v in tot:
                for k in m:
                    tot[v][k] += x[v][k]
                over[v] += max(0.0, x[v]["minutes"] - hi)
            r = rmap.get(rid)
            if r is not None:
                nt = r.extra.get("notime")
                plan["memory"] += r.planned_minutes
                plan["no_time"] += nt["planned"] if nt else r.planned_minutes
                L = r.extra.get("limits") or {}
                if L:
                    expected["memory"] += L["after_min"]
                    expected["no_time"] += (nt.get("expected_min") or L["after_min"]) if nt else L["after_min"]
                if nt:
                    ot_up["route"] += 1
                    dz = max(0.0, x["memory"]["minutes"] - hi) - max(0.0, x["no_time"]["minutes"] - hi)
                    ot_up["remaining"] += int(dz > 1e-6)
                    ot_up["max_increase_min"] = round(max(ot_up["max_increase_min"], dz), 1)
            zd = x.get("time_stops") or {}
            mv["route"] += int(bool(zd))
            for o in zd.values():
                mv["stop"] += 1
                mv["fails_no_time"] += int(o["no_time"]["fail"] > 0)
                mv["fails_memory"] += int(o["memory"]["fail"] > 0)
    days = max(1, len(D.counterfactuals))
    per = {v: {**{k: round(tot[v][k] / days, 2) for k in m}, "overtime_min": round(over[v] / days, 1),
               "planned_min": round(plan[v] / days, 1), "expected_duration_min": round(expected[v] / days, 1)} for v in tot}
    diff = {k: round(per["memory"][k] - per["no_time"][k], 2) for k in per["memory"]}
    return {"day": len(ts), "daily": per_day, "accuracy": round(per_day["correct"] / per_day["route"], 3) if per_day["route"] else None,
            "counterfactual_daily": per, "diff_daily": diff, "carried_stops": mv,
            "constraint": repair_limit_summary(res), "overtime_route": ot_up, "alternatives": alternatives_summary(res),
            "note": "Aynı kurye, aynı duraklar, aynı rastgele sayılar. zamansiz = hafızalı rota (erteleme, pencere, servis) ama "
                   "zaman onarımı yok; hafizali = yayımlanan kol D. Bulgular yalnız o günden önceki teslim kayıtlarından."}


def repair_limit_summary(res: SimResult) -> dict:
    """Faz 2c sert kısıtının doğrulaması (kol D, tüm rotalar): onarım öncesi ↔ sonrası beklenen süre ve km."""
    rc, hi = res.cfg.routing, float(res.cfg.planning.band[1])
    n = violation = band_new = 0
    dmax = kmax = -1e9
    dsum = 0.0
    for routes in res.arms["D"].routes.values():
        for r in routes:
            L = r.extra.get("limits")
            if not L:
                continue
            n += 1
            d, k = L["after_min"] - L["before_min"], L["after_km"] - L["before_km"]
            dsum += d
            dmax, kmax = max(dmax, d), max(kmax, k)
            violation += int(L["after_min"] > L["border_min"] + 1e-6 or k > L["tolerance_km"] + 1e-6)
            band_new += int(L["before_min"] <= hi < L["after_min"])
    return {"enabled": bool(rc.repair_limits), "tolerance_min": rc.repair_max_extra_min, "tolerance_km": rc.repair_max_extra_km,
            "band_min": hi, "route": n, "violation": violation, "new_over_band": band_new,
            "max_duration_diff_min": round(dmax, 2) if n else None, "max_km_diff": round(kmax, 3) if n else None,
            "mean_duration_diff_min": round(dsum / n, 2) if n else None,
            "note": "Onarım öncesi = erteleme sonrası, servis düzeltmeli düz sıra. Süre = sürüş + servis + bilinen öğle beklemesi "
                   "(planlanan dk). Pencere ve zaman onarımı birlikte bu sınırı aşamaz."}


def alternatives_summary(res: SimResult) -> dict:
    """Kısıt yüzünden kaydırılamayan bulgular ve önerilen alternatifler (müdür kararı; simülasyonda uygulanmaz)."""
    alts = [x for xs in res.arms["D"].time_alts.values() for x in xs]
    by = defaultdict(int)
    select = defaultdict(int)
    for x in alts:
        by[x["reason"]] += 1
        select[x["option"]] += 1
    return {"total": len(alts), "reason": dict(sorted(by.items())), "option": dict(sorted(select.items())),
            "transfer_expected_gain_stop": round(sum(float(x.get("gain_stop") or 0) for x in alts), 2),
            "note": "Öneriler müdür kararına sunulur; simülasyon (kol D) bunları uygulamaz, ölçülen etkide yoktur. Aktarma iki rotada "
                   "da kısıtı sağlar (toplam süre/km artmaz, hedef bant içinde, durak vardiya bitişinden önce)."}


def time_example(res: SimResult, crit_day: int) -> dict | None:
    """Demo için seçilmiş örnek (temsilî değil; büyüklük için `summary.time_analysis`): zaman onarımının AYNI ROTA içinde taşıdığı,
    zamansız yürütmede "alıcı yok" / zaman-farkında yürütmede teslim olan durak. Faz 2c: rota süresi artmamış, rota fazla mesaiye
    girmemiş (gerçekleşen ≤ bant), yeni varış vardiya içinde; öğle/sabah → öğleden sonra kayması tercih edilir; ≥ 6 geçmiş deneme,
    demo gününe en yakın, geçmişi uzun."""
    D = res.arms["D"]
    w = res.world
    hi = float(res.cfg.planning.band[1])
    se = float(res.cfg.planning.start_minute) + hi
    log = D.history.time.log if D.history.time is not None else []
    by_addr: dict[int, list] = defaultdict(list)
    for day, a, minute, ab in log:
        by_addr[a].append((day, minute, ab))
    names = {c.id: c.name for c in res.couriers}
    cands = []
    for day, routes in D.counterfactuals.items():
        rmap = {r.id: r for r in D.routes.get(day, [])}
        for rid, x in routes.items():
            r = rmap.get(rid)
            for a, o in (x.get("time_stops") or {}).items():
                if r is None:
                    continue
                hist = [h for h in by_addr.get(a, []) if h[0] < day]
                contrast = int(o["no_time"]["reason"] == "recipient_absent" and o["memory"]["fail"] == 0)
                ch = next(c for c in r.extra["changes"] if c["type"] == "time" and c["address"] == a)
                L = r.extra.get("limits") or {}
                calm = int(x["memory"]["minutes"] <= hi and o["memory"]["arrival"] <= se and ch.get("extra_min", 0) <= 1e-6
                           and L.get("after_min", 0) <= L.get("before_min", 0) + 1e-6)
                b_ = r.extra.get("time_findings", {}).get(a) or {}
                hit = int(slot(ch["new_arrival"]) == b_.get("good"))
                nice = int(slot(ch["old_arrival"]) <= 1 and 2 <= slot(ch["new_arrival"]) <= 3)
                cands.append((-contrast, -calm, -hit, -nice, -int(len(hist) >= 6), abs(day - crit_day), -len(hist), day, a, r, o, hist, x))
    if not cands:
        return None
    cands.sort(key=lambda c: c[:9])
    *_, day, a, r, o, hist, x = cands[0]
    ch = next(c for c in r.extra["changes"] if c["type"] == "time" and c["address"] == a)
    b = r.extra["time_findings"][a]

    def hm(t: int) -> str:
        return f"{int(t) // 60:02d}:{int(t) % 60:02d}"

    def res_of(x: dict) -> str:
        return "delivery" if x["fail"] == 0 else (x["reason"] or "fails")

    return {"day": day, "weekday": WEEKDAY_TR[weekday(day)], "courier": r.courier, "courier_name": names.get(r.courier),
            "cluster": r.id, "address": a, "label": w.addr_label[a], "address_type": w.addr_kind[a],
            "history": [{"day": d, "weekday": WEEKDAY_TR[weekday(d)], "hour": hm(t), "slot": SLOT_NAMES[slot(t)],
                        "result": "recipient_absent" if ab else "delivery"} for d, t, ab in hist],
            "finding": {**b, "bad_name": SLOT_NAMES[b["bad"]], "good_name": SLOT_NAMES[b["good"]], "text": proposal_text(b)},
            "change": ch,
            "result": {"no_time": {"arrival": hm(o["no_time"]["arrival"]), "result": res_of(o["no_time"])},
                      "memory": {"arrival": hm(o["memory"]["arrival"]), "result": res_of(o["memory"])}},
            "route": {"limits": r.extra.get("limits"), "planned_min": {"no_time": round(r.extra["notime"]["planned"], 1),
                                                                        "memory": round(r.planned_minutes, 1)},
                     "km": {"no_time": round(r.extra["notime"]["km"], 2), "memory": round(r.km, 2)},
                     "actual_min": {"no_time": x["no_time"]["minutes"], "memory": x["memory"]["minutes"]},
                     "overtime_min": {"no_time": round(max(0.0, x["no_time"]["minutes"] - hi), 1),
                                        "memory": round(max(0.0, x["memory"]["minutes"] - hi), 1)},
                     "shift_end": hm(se), "band_min": hi},
            "note": "Seçilmiş örnek (mekanizmayı gösterir). Büyüklük: summary.time_analysis. Aynı gün, aynı rastgele sayılar. "
                   "Faz 2c: aynı rota içinde, rota süresi artmadan, vardiya içinde."}


def alt_rows(res: SimResult) -> dict[int, list[dict]]:
    """Gün → kaydırılamayan bulgu alternatifleri (okunur metinle). Etiket ve kurye adları gözlemlenebilir bilgidir."""
    w = res.world
    names = {c.id: c.name for c in res.couriers}
    se = float(res.cfg.planning.start_minute) + float(res.cfg.planning.band[1])
    out = {}
    for day, xs in res.arms["D"].time_alts.items():
        rows = []
        for x in xs:
            y = {**x, "label": w.addr_label[x["address"]], "courier_name": names.get(x.get("courier")),
                 "target_courier_name": names.get(x.get("target_courier")) if x.get("target_courier") else None}
            y["text"] = alternative_text(y, y["label"], y["courier_name"], y["target_courier_name"], se)
            y["sms_text"] = sms_text(y["target_arrival"] if y["option"] == "transfer" else y["arrival"])
            rows.append(y)
        out[day] = rows
    return out


def time_example_blocked(res: SimResult, crit_day: int, alts: dict[int, list[dict]]) -> dict | None:
    """İkinci demo örneği: kısıt yüzünden aynı rotada kaydırılamayan bulgu ve ajanın alternatifi (aktarma tercih edilir, sonra
    ertesi gün). Geçmişi ≥ 4 deneme, demo gününe en yakın. Seçilmiş örnek; öneri müdür kararıdır, simülasyonda uygulanmaz."""
    D = res.arms["D"]
    if D.history.time is None:
        return None
    pref = {"transfer": 0, "next_day": 1, "evening_delivery_point": 2}
    lg = D.history.time.log
    days_ = np.array([t[0] for t in lg], dtype=np.int64)
    addrs_ = np.array([t[1] for t in lg], dtype=np.int64)
    mins_ = np.array([t[2] for t in lg], dtype=np.int64)
    abs_ = np.array([t[3] for t in lg], dtype=np.int64)
    cands = []
    for day, xs in alts.items():
        for x in xs:
            nh = int(((addrs_ == x["address"]) & (days_ < day)).sum())
            cands.append((pref[x["option"]], -int(nh >= 4), abs(day - crit_day), -nh, day, x["address"], x))
    if not cands:
        return None
    cands.sort(key=lambda c: c[:6])
    *_, day, a, x = cands[0]
    kind_idx = np.array([ADDRESS_KINDS.index(k) for k in res.world.addr_kind], dtype=np.int64)
    att, ab = counts_from_log(len(kind_idx), days_, addrs_, mins_, abs_, day)
    b = time_findings(att, ab, kind_idx, len(ADDRESS_KINDS), [a], weekday(day),
                        TimeParams.from_dict(res.cfg.time_analysis.model_dump())).get(a)
    m = (addrs_ == a) & (days_ < day)
    hist = [{"day": int(d), "weekday": WEEKDAY_TR[weekday(int(d))], "hour": f"{int(t) // 60:02d}:{int(t) % 60:02d}",
             "slot": SLOT_NAMES[slot(int(t))], "result": "recipient_absent" if int(z) else "delivery"}
            for d, t, z in zip(days_[m], mins_[m], abs_[m])]
    return {"day": day, "weekday": WEEKDAY_TR[weekday(day)], **x, "address_type": res.world.addr_kind[a],
            "finding": None if b is None else {**b, "bad_name": SLOT_NAMES[b["bad"]],
                                             "good_name": SLOT_NAMES[b["good"]] if b.get("good") is not None else None,
                                             "text": proposal_text(b)},
            "history": hist,
            "note": "Seçilmiş örnek: kısıt (rota uzamaz, fazla mesai yok) yüzünden aynı rotada kaydırılamadı; ajanın alternatifi müdür "
                   "kararına sunulur, simülasyonda uygulanmaz."}


def _pctile(v: list[float], q: float) -> float:
    return round(float(np.percentile(v, q)), 1) if v else 0.0


def memory_routing_summary(res: SimResult) -> dict:
    """Aynı kurye, aynı duraklar, aynı gün (ortak rastgele sayılar): hafızasız ↔ yalnız ipucu ↔ hafızalı (ipucu + rota).

    Rotanın katkısı = yalnız ipucu − hafızalı; kapı ipucunun katkısı = hafızasız − yalnız ipucu. Not: karşı-olgu, kuryenin
    o günkü bilgisiyle hesaplanır; hafıza olmasaydı kurye bazı püf noktalarını kendisi öğrenmiş olurdu (kol C bunu içerir).
    """
    cf = res.arms["D"].counterfactuals
    keys = ("minutes", "km", "fail", "preventable_fail", "window_hits", "window_wait", "wasted", "deferred", "recipient_absent", "revisit")
    tot = {v: {k: 0.0 for k in keys} for v in ("memoryless", "hint_only", "no_time", "memory")}
    by_kind: dict[str, dict] = {}
    saves: dict[str, list[float]] = defaultdict(list)
    n = 0
    for day, routes in cf.items():
        for rid, x in routes.items():
            if "memory" not in x:
                continue
            n += 1
            for v in tot:
                for k in keys:
                    tot[v][k] += x[v][k]
            bk = by_kind.setdefault(x["kind"], {"route": 0, **{f"{v}_{k}": 0.0 for v in tot for k in ("minutes", "preventable_fail")}})
            bk["route"] += 1
            for v in tot:
                bk[f"{v}_minutes"] += x[v]["minutes"]
                bk[f"{v}_preventable_fail"] += x[v]["preventable_fail"]
            saves[x["kind"]].append(x["memoryless"]["minutes"] - x["memory"]["minutes"])
    days = max(1, len(cf))
    per_day = {v: {k: round(tot[v][k] / days, 2) for k in keys} for v in tot}
    kinds = {}
    for kd, b in by_kind.items():
        r = max(1, b["route"])
        kinds[kd] = {"route": b["route"],
                     "min_gain_route_mean": round((b["memoryless_minutes"] - b["memory_minutes"]) / r, 1),
                     "min_gain_route_p10": _pctile(saves[kd], 10), "min_gain_route_p50": _pctile(saves[kd], 50),
                     "min_gain_route_p90": _pctile(saves[kd], 90),
                     "route_share_min_route_mean": round((b["hint_only_minutes"] - b["memory_minutes"]) / r, 1),
                     "prevented_fails_route_mean": round((b["memoryless_preventable_fail"] - b["memory_preventable_fail"]) / r, 2)}
    return {"route_day": n, "day": len(cf), "daily": per_day, "type": kinds,
            "note": "Aynı kurye, aynı duraklar, aynı rastgele sayılar. Hafızasız = düz sıra, ipucu yok; yalnız ipucu = düz sıra + "
                   "kapı ipucu; zamansız = hafıza-farkında rota + kapı ipucu, zaman onarımı yok; hafızalı = kol D (zaman onarımı dahil)."}


# Anlık görüntü ve depo koordinatları ~1 cm hassasiyetle: ajan rotayı bu koordinatlardan yeniden kurar; 5 ondalık (~1 m)
# eşit maliyetli iki konum arasında seçimi simülatörden ayırabiliyordu (Faz 5: gün 22'de 407/408).
ND_COORD = 7

# Hikayenin anı (ui-story Sahne 2–5 ve docs/sunum.md gün 32'yi ve Gökhan'ı anlatır). Sezgisel seçim veri değişince
# kayabilir (Faz 5'te gün 33 · Onur'a kaydı ve Sahne 4 başka kuryenin rakamını gösterecekti); bu an D kolunda varsa önceliklidir.
STORY_MOMENT = {"day": 32, "courier": "O02"}


def critical_moment(res: SimResult) -> dict:
    """Demoda gösterilecek gün ve kurye. Önce `STORY_MOMENT` (o gün D kolunda çalışmış ve ≥ 5 ipucu almışsa); yoksa D kolunda
    çalışan yeni/ödünç/yedek kuryeler arasında, bölgeye yabancı olduğu ve hafızadan en çok ipucu aldığı (gün, kurye).
    O da yoksa (D − C) farkının en büyük olduğu gündeki kurye."""
    idx = {day: i for i, day in enumerate(res.eval_days)}
    hk = STORY_MOMENT
    if hk["day"] in idx and any(r["day"] == hk["day"] and r["courier"] == hk["courier"] and r["hinted"] >= 5
                                for r in res.arms["D"].courier_daily):
        return {"day": hk["day"], "eval_index": idx[hk["day"]], "courier": hk["courier"]}
    gain = {day: (res.arms["D"].daily[i]["first_attempt_rate"] or 0) - (res.arms["C"].daily[i]["first_attempt_rate"] or 0)
            for day, i in idx.items()}
    cands = [r for r in res.arms["D"].courier_daily if r["kind"] in ("new", "borrowed", "reserve") and r["hinted"] >= 5]
    if cands:
        # Hikaye önceliği: komşu şubeden "kim gitsin" seçiminin yapıldığı gün (gelebilecek ödünç > kullanılan) >
        # ödünç (şubeler arası destek) > yeni > yedek; sonra ipucu × yabancılık.
        used = defaultdict(int)
        for r in res.arms["D"].courier_daily:
            if r["kind"] == "borrowed":
                used[r["day"]] += 1
        avail = {day: sum(1 for c in res.couriers if c.kind == "borrowed" and c.available(day)) for day in idx}
        choice = {day: int(avail[day] > used[day] > 0) for day in idx}
        pri = {"borrowed": 2, "new": 1, "reserve": 0}
        best = max(cands, key=lambda r: (choice[r["day"]] if r["kind"] == "borrowed" else 0, pri[r["kind"]],
                                         r["hinted"] * (0.5 + r["unfamiliar_share"]), gain[r["day"]]))
        return {"day": best["day"], "eval_index": idx[best["day"]], "courier": best["courier"]}
    day = max(gain, key=gain.get)
    rows = sorted((r for r in res.arms["D"].courier_daily if r["day"] == day), key=lambda r: -r["hinted"])
    return {"day": day, "eval_index": idx[day], "courier": rows[0]["courier"] if rows else None}


def learning_curves(res: SimResult) -> dict:
    out: dict[str, dict] = {}
    kinds = {c.id: c.kind for c in res.couriers}
    for a in ARMS:
        per: dict[str, list] = defaultdict(list)
        for r in res.arms[a].courier_daily:
            if kinds[r["courier"]] in ("new", "borrowed", "reserve") and r["attempted"]:
                per[r["courier"]].append({"day": r["day"], "rate": round(r["ok"] / r["attempted"], 4),
                                          "unfamiliar_share": r["unfamiliar_share"], "hinted": r["hinted"],
                                          "preventable_per100": round(100 * r.get("preventable_fail", 0) / max(1, r["stops"]), 2),
                                          "door_min_per_stop": round(r.get("door_minutes", 0) / max(1, r["stops"]), 2),
                                          "minutes": r["minutes"]})
        out[a] = {c: {"kind": kinds[c], "days": v} for c, v in sorted(per.items())}
    return out


def same_route_curves(res: SimResult) -> dict:
    """Yeni/ödünç/yedek kuryenin her günü için aynı rota karşı-olgusu: hafızasız ↔ hafızalı (kol D)."""
    kinds = {c.id: c.kind for c in res.couriers}
    per: dict[str, list] = defaultdict(list)
    for day in sorted(res.arms["D"].counterfactuals):
        for x in res.arms["D"].counterfactuals[day].values():
            if kinds[x["courier"]] not in ("new", "borrowed", "reserve") or "memory" not in x:
                continue
            row = {"day": day}
            for v in ("memoryless", "memory"):
                st = max(1, x[v]["stops"])
                row[v] = {"preventable_per100": round(100 * x[v]["preventable_fail"] / st, 2), "minutes": x[v]["minutes"],
                          "fail": x[v]["fail"]}
            per[x["courier"]].append(row)
    return {c: {"kind": kinds[c], "days": v} for c, v in sorted(per.items())}


def export_run(res: SimResult, out_root: str | Path, snapshots: bool | None = None) -> Path:
    cfg, w = res.cfg, res.world
    rid = run_id_for(res)
    out = Path(out_root) / rid
    out.mkdir(parents=True, exist_ok=True)
    nd = cfg.export.round
    snapshots = cfg.export.snapshots if snapshots is None else snapshots

    (out / "config.yaml").write_text(yaml.safe_dump(config_to_dict(res.cfg), allow_unicode=True, sort_keys=False), encoding="utf-8")
    crit = critical_moment(res)
    names = {c.id: c.name for c in res.couriers}
    cfd = res.arms["D"].counterfactuals.get(crit["day"], {})
    cx = next((x for x in cfd.values() if x["courier"] == crit["courier"] and "memory" in x), None)
    if cx:
        crit["memory_gain"] = {"memoryless_min": cx["memoryless"]["minutes"], "hint_only_min": cx["hint_only"]["minutes"],
                                  "memory_min": cx["memory"]["minutes"],
                                  "mins": round(cx["memoryless"]["minutes"] - cx["memory"]["minutes"], 1),
                                  "fails_memoryless": cx["memoryless"]["fail"], "fails_memory": cx["memory"]["fail"],
                                  "note": "Aynı kurye, aynı duraklar, aynı gün; hafızasız = düz sıra, ipucu yok."}
    zex = time_example(res, crit["day"])
    alts = alt_rows(res)
    zex2 = time_example_blocked(res, crit["day"], alts)
    _dump(out / "meta.json", {
        "app_data": True, "run_id": rid, "seed": cfg.seed, "package_version": _pkg_version(),
        "scenarios": cfg.scenarios, "elapsed_seconds": round(res.elapsed, 1),
        "warmup_days": cfg.days.warmup, "eval_days": res.eval_days,
        "weekday_names": WEEKDAY_TR, "arms": ARM_LABELS, "band": list(cfg.planning.band),
        "critical": {**crit, "courier_name": names.get(crit["courier"])},
        "depot": [_r(x, ND_COORD) for x in w.depot_latlng],
        "center": list(cfg.world.center),
        "label": "Uygulama verisi · 1 aylık geçmiş",
        "stop_fields": STOP_FIELDS,
        "time_example": zex,
        "time_example_constraint": zex2,
    })
    summ = summarize(res)
    _dump(out / "summary.json", summ)
    _dump(out / "daily.json", {"app_data": True, "arms": {a: res.arms[a].daily for a in ARMS}})
    _dump(out / "learning_curve.json", {"app_data": True, "arms": learning_curves(res), "same_route": same_route_curves(res),
                                        "note": "same_route: aynı kurye, aynı duraklar, aynı gün; hafızasız ↔ hafızalı (kol D)."})
    _dump(out / "harvest.json", {"app_data": True, "days": res.arms["D"].harvest_stats})
    _dump(out / "time.json", {"app_data": True, "days": res.arms["D"].time_stats, "summary": summ["time_analysis"],
                               "alternatives": {str(d): v for d, v in alts.items()}})
    zk = res.arms["D"].history.time
    if zk is not None:
        # Gözlemlenebilir teslim kaydı (kol D: ısınma + değerlendirme): bulunabilirliği sınayan denemeler. Ajanın teslim zamanı
        # analizi bundan (hedef günden ÖNCEKİ satırlar) yapılır; simülatörün kol D'si aynı sayımları kullanır.
        lg = zk.log
        _dump(out / "delivery_log.json", {"app_data": True, "arm": "D", "fields": ["day", "address", "minute", "absent"],
                                           "day": [x[0] for x in lg], "address": [x[1] for x in lg],
                                           "minute": [x[2] for x in lg], "absent": [x[3] for x in lg]})

    truth_skill = {c.id: c.skill for c in res.couriers}
    rec_w = report_recovery(HistoryReader(res.warm.history, res.warm.fam, cfg.familiarity.unfamiliar_below, w.block_kind), truth_skill, cfg.assignment)
    rec_c = report_recovery(HistoryReader(res.arms["C"].history, res.arms["C"].fam, cfg.familiarity.unfamiliar_below, w.block_kind), truth_skill, cfg.assignment)
    _dump(out / "recovery.json", {"app_data": True, "end_of_warmup": rec_w, "end_of_eval_C": rec_c})

    # Gözlemlenebilir dünya
    bm = cfg.world.block_m / 1000.0
    dlat = bm / 110.574
    dlng = bm / (111.320 * float(np.cos(np.radians(cfg.world.center[0]))))
    _dump(out / "blocks.json", {
        "app_data": True, "rows": w.n_rows, "cols": w.n_cols, "dlat": _r(dlat, 7), "dlng": _r(dlng, 7),
        "fields": ["id", "row", "col", "kind", "lat", "lng"],
        "blocks": [[i, int(w.block_rc[i, 0]), int(w.block_rc[i, 1]), w.block_kind[i],
                    _r(w.block_latlng[i, 0], nd), _r(w.block_latlng[i, 1], nd)] for i in range(w.n_blocks)],
    })
    _dump(out / "addresses.json", {
        "app_data": True, "fields": ["id", "lat", "lng", "kind", "block", "label"],
        "addresses": [[a, _r(w.addr_latlng[a, 0], ND_COORD), _r(w.addr_latlng[a, 1], ND_COORD), w.addr_kind[a],
                       int(w.addr_block[a]), w.addr_label[a]] for a in range(w.n_addresses)],
    })
    _dump(out / "couriers.json", {"app_data": True, "couriers": [
        {"id": c.id, "name": c.name, "kind": c.kind, "start_day": c.start_day, "end_day": c.end_day,
         "leave_days": sorted(c.leave_days)} for c in res.couriers]})

    # Günlük anlık görüntüler
    if snapshots:
        for a in ARMS:
            st = res.arms[a]
            for i, day in enumerate(res.eval_days):
                routes_out = []
                for r, rr in zip(st.routes[day], st.results[day]):
                    hints: dict[str, list[str]] = {}
                    rows = []
                    for s in rr.stops:
                        reason = max(s.reasons, key=s.reasons.get) if s.reasons else None
                        rows.append([s.address, _r(w.addr_latlng[s.address, 0], ND_COORD), _r(w.addr_latlng[s.address, 1], ND_COORD),
                                     s.n, int(round(s.arrival)), s.ok, s.fail, s.deferred, reason,
                                     int(s.hinted), int(s.unfamiliar)])
                        if s.hint_texts:
                            hints[str(s.address)] = s.hint_texts
                    c = next(x for x in res.couriers if x.id == rr.courier)
                    ro = {"route": r.id, "zone": r.zone, "courier": c.id, "courier_name": c.name,
                          "courier_kind": c.kind, "covered_by": r.covered_by,
                          "km": round(rr.km, 2), "minutes": round(rr.minutes, 1),
                          "planned_minutes": round(r.planned_minutes, 1), "stops": rows, "hints": hints,
                          "departure": round(rr.start_minute, 1)}
                    if "plain" in r.extra:
                        ro["plan"] = {
                            "plain_order": [int(x) for x in r.extra["plain"]], "plain_km": round(r.extra["plain_km"], 2),
                            "plain_planned_minutes": round(r.extra["plain_planned"], 1),
                            "deferred": [{"address": int(sd.address), "n": sd.n, "kind": d[1], "entry": d[2],
                                          "outcome": "correct" if sd.deferred else "wrong"}
                                         for d, sd in zip(r.extra.get("deferred", []), rr.plan_deferred)],
                            "changes": r.extra.get("changes", []), "time_fail": r.extra.get("time_fail"),
                            "limits": r.extra.get("limits"), "time_blocked": r.extra.get("time_blocked", []),
                            "extra_service": {str(k): v for k, v in r.extra.get("extra_service", {}).items()}}
                        cfx = st.counterfactuals.get(day, {}).get(r.id)
                        if cfx:
                            ro["counterfactual"] = {k: cfx[k] for k in ("memoryless", "hint_only", "no_time", "memory", "current_morning") if k in cfx}
                            if cfx.get("time_stops"):
                                ro["counterfactual"]["time_stops"] = {str(k): v for k, v in cfx["time_stops"].items()}
                    routes_out.append(ro)
                _dump(out / "snapshots" / a / f"{day}.json", {
                    "app_data": True, "run_id": rid, "arm": a, "day": day, "eval_index": i,
                    "weekday": weekday(day), "weekday_name": WEEKDAY_TR[weekday(day)],
                    "depot": [_r(x, ND_COORD) for x in w.depot_latlng], "stop_fields": STOP_FIELDS, "routes": routes_out,
                })

    # Atama girdileri (C ve D): ajan araçları bu matrislerle çalışır
    for a in ("C", "D"):
        st = res.arms[a]
        for day, dec in st.decisions.items():
            mat = dec.details["matrix"]
            routes = st.routes[day]
            clusters = []
            for r in routes:
                ll = w.addr_latlng[r.stops]
                clusters.append({"id": r.id, "stops": int(len(r.stops)), "shipments": int(res.counts[day][r.stops].sum()),
                                 "planned_minutes": round(r.planned_minutes, 1), "km": round(r.km, 2),
                                 "center": [_r(ll[:, 0].mean(), nd), _r(ll[:, 1].mean(), nd)],
                                 "blocks": sorted({int(w.addr_block[x]) for x in r.stops})})
            _dump(out / "assign" / a / f"{day}.json", {
                "app_data": True, "arm": a, "day": day, "weekday_name": WEEKDAY_TR[weekday(day)],
                "couriers": [{"id": c, "name": names[c], "kind": next(x.kind for x in res.couriers if x.id == c)} for c in mat["couriers"]],
                "clusters": clusters,
                "matrix_fields": ["exp_fail", "exp_min", "unfamiliar", "covered_unfamiliar", "cost"],
                "exp_fail": np.round(mat["exp_fail"], 3).tolist(), "exp_min": np.round(mat["exp_min"], 1).tolist(),
                "unfamiliar": mat["unfamiliar"].tolist(), "covered_unfamiliar": mat["covered_unfamiliar"].tolist(),
                "cost": np.round(mat["cost"], 3).tolist(),
                "chosen": {str(k): v for k, v in dec.mapping.items()},
                "totals": {k: round(v, 3) for k, v in dec.details["totals"].items()},
                "unavailable": [{"id": c.id, "name": c.name, "kind": c.kind} for c in res.couriers
                                if not c.available(day) and c.kind != "borrowed" and c.start_day <= day
                                and (c.end_day is None or day < c.end_day)],
            })

    # Hafıza (D) ve notlar
    d = res.arms["D"]
    for day, entries in d.memory_snapshots.items():
        _dump(out / "memory" / f"{day}.json", {"app_data": True, "day": day, "entries": entries})
    all_notes = res.warm.notes + d.notes
    _dump(out / "notes.json", {"app_data": True, "notes": [n.public() for n in all_notes]})
    _dump(out / "notes_truth.json", {"app_data": True, "hidden_truth": True, "notes": [n.truth() for n in all_notes]})
    _dump(out / "parse_stats.json", {"app_data": True, "warmup": res.warm.parse_stats, "D": d.parse_stats})

    # Gizli gerçek (yalnız değerlendirme)
    _dump(out / "truth.json", {
        "app_data": True, "hidden_truth": True,
        "couriers": [{"id": c.id, "skill": round(c.skill, 4), "speed": round(c.speed, 4),
                      "note_propensity": round(c.note_propensity, 4)} for c in res.couriers],
        "quirks": [{"id": q.id, "address": q.address, "kind": q.kind, "temporary": q.temporary,
                    "active_from": q.active_from, "active_to": q.active_to, "change_day": q.change_day}
                   for qs in w.quirks_by_addr for q in qs],
        "presence": {"profiles": sorted(set(w.addr_presence)), "profile": [sorted(set(w.addr_presence)).index(x) for x in w.addr_presence],
                     "m": [round(float(x), 3) for x in w.addr_presence_m]} if cfg.presence.enabled else None,
    })
    (out / "report.md").write_text(render_report(res, summ, crit, rec_c), encoding="utf-8")
    return out


def _pct(x: float | None, nd: int = 1) -> str:
    return "–" if x is None else f"%{100 * x:.{nd}f}".replace(".", ",")


def render_report(res: SimResult, summ: dict, crit: dict, rec: dict) -> str:
    A = summ["arms"]
    lines = [
        f"# Simülasyon raporu: {run_id_for(res)}",
        "",
        "> **Uygulama verisi · 1 aylık geçmiş.** Rakamlar bu varsayımlar altında geçerlidir; mekanizmayı gösterir, etkinin büyüklüğünü kanıtlamaz.",
        "",
        f"Senaryolar: {', '.join(res.cfg.scenarios) or 'normal'} · seed {res.cfg.seed} · "
        f"{res.cfg.days.warmup} gün ısınma + {res.cfg.days.eval} gün değerlendirme",
        "",
        "| Kol | İlk denemede teslim | Bilgiyle önlenebilir başarısızlık | Kurye/gün | Km/gün | Vardiya bandında | Yabancı durak payı | Hafıza kapsamı |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for a in ARMS:
        x = A[a]
        lines.append(f"| {a} · {x['label']} | {_pct(x['first_attempt_rate'], 2)} | {x['preventable_fail']} | "
                     f"{x['couriers_per_day']:.1f} | {x['km_per_day']:.0f} | {_pct(x['in_band_share'], 0)} | "
                     f"{_pct(x['unfamiliar_share'], 1)} | {_pct(x['memory_coverage'], 1)} |")
    dl = summ["deltas"]
    lines += [
        "",
        "## Farklar",
        f"- Uyuma göre atama (C), geçmişe bakmadan atamaya (B) göre: ilk denemede teslim {dl['C_vs_B']['first_attempt_pp']:+.2f} puan, "
        f"önlenebilir başarısızlık {dl['C_vs_B']['preventable_fail_pct']:+.1f}%.",
        f"- Hafıza (D), uyumlu atamanın (C) üstüne: {dl['D_vs_C']['first_attempt_pp']:+.2f} puan, önlenebilir başarısızlık {dl['D_vs_C']['preventable_fail_pct']:+.1f}%.",
        f"- Yeni yapı (D), mevcut yapıya (A) göre: araç-gün {dl['D_vs_A']['vehicle_days_pct']:+.1f}%, km {dl['D_vs_A']['km_pct']:+.1f}%, "
        f"ilk denemede teslim {dl['D_vs_A']['first_attempt_pp']:+.2f} puan.",
        "",
        "## Uyum tahmincisi doğrulaması",
        f"- Tahmin edilen kurye etkisi ile gizli gerçek beceri arasındaki sıra korelasyonu: {rec.get('spearman_estimate')} "
        f"(bölge zorluğundan arındırılmamış ham oran: {rec.get('spearman_naive')}; n = {rec.get('n')}).",
        "",
        f"## Demo anı\n- Gün {crit['day']} (değerlendirme günü {crit['eval_index'] + 1}), kurye {crit['courier']}."
        + (f" Hafıza bu kuryeye {crit['memory_gain']['mins']:+.0f} dk kazandırdı (aynı rota, hafızasız "
           f"{crit['memory_gain']['memoryless_min']:.0f} → hafızalı {crit['memory_gain']['memory_min']:.0f} dk)."
           if crit.get("memory_gain") else ""),
    ]
    mr = summ.get("memory_routing") or {}
    if mr.get("daily"):
        g = mr["daily"]
        lines += ["", "## Hafıza rotayı nasıl değiştiriyor (kol D, aynı rota karşı-olgusu, gün başına)",
                  "| | Hafızasız | Yalnız kapı ipucu | Hafızalı (ipucu + rota) |", "|---|---|---|---|"]
        for k, name in (("minutes", "Toplam rota dk"), ("km", "km"), ("preventable_fail", "Önlenebilir başarısız"),
                      ("window_hits", "Öğle arasına denk gelen varış"), ("wasted", "Kapalı kapıya gidiş")):
            lines.append(f"| {name} | {g['memoryless'][k]:.1f} | {g['hint_only'][k]:.1f} | {g['memory'][k]:.1f} |")
    za = summ.get("time_analysis") or {}
    if za.get("day"):
        f, g, tv = za["diff_daily"], za["daily"], za["carried_stops"]
        lines += ["", "## Teslim zamanı analizi (kol D, kayıtlardan; aynı rota zaman onarımı var ↔ yok, gün başına)",
                  f"- Rotaya alınan bulgu {num_tr(g['route'])}/gün, taşınan durak {num_tr(g['carried'])}/gün; bulguların gizli gerçekle "
                  f"uyumu {_pct(za['accuracy'] or 0, 0)}.",
                  f"- Alıcı yok {f['recipient_absent']:+.2f} gönderi/gün, tekrar ziyaret {f['revisit']:+.2f} durak/gün, km {f['km']:+.2f}, "
                  f"fazla mesai {f['overtime_min']:+.1f} dk/gün.",
                  f"- Taşınan {tv['stop']} durakta başarısız: zamansız {tv['fails_no_time']} → zaman-farkında {tv['fails_memory']}."]
        k, al = za.get("constraint") or {}, za.get("alternatives") or {}
        if k.get("route"):
            lines += [f"- Sert kısıt (Faz 2c): {k['route']} rotada ihlal {k['violation']}, yeni bant üstü {k['new_over_band']}; onarım "
                      f"öncesine göre en çok {k['max_duration_diff_min']:+.1f} dk, {k['max_km_diff']:+.2f} km (tolerans "
                      f"{k['tolerance_min']:+.0f} dk / {k['tolerance_km']:+.1f} km). Planlanan süre farkı {f['planned_min']:+.1f} dk/gün.",
                      f"- Kısıt yüzünden kaydırılamayan {al.get('total', 0)} bulgu: " +
                      ", ".join(f"{a} {n}" for a, n in (al.get("option") or {}).items()) + " (müdür kararı; uygulanmadı)."]
    return "\n".join(lines) + "\n"


def num_tr(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")

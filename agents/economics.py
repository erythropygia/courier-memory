"""Ekonomi: token maliyeti ↔ operasyonel kazanç (şube-gün, işlem başı, yıllık, ölçek).

python -m agents.economics             → data/demo_run/economics.json
API: GET /api/economics?usd_try=..&courier_daily_cost_tl=..&fails_other_tl=..&km_cost_tl=..&model_memory=..

Kazanç kaynakları (simülasyondan, uzun dönem varsa o):
  1. Önlenen başarısız ilk denemeler × başarısız deneme maliyeti (tekrar gitme dakikası + km + diğer)
  2. Önlenen fazla mesai dakikaları × kurye dakikası × fazla mesai çarpanı
  3. Kapıda kazanılan dakika (vardiya içi kapasite; ayrı gösterilir, manşet getiriye katılmaz)
Karşılaştırma: D (çekirdek bölge + hafıza) ← C (çekirdek bölgeli plan) ve D ← B (geçmişe bakmadan atama); manşet: A (bugün) → D operasyon maliyeti.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import yaml

from .rundata import RunData
from .tr import num

CONFIG = Path(__file__).parent / "economics.yaml"
AGENT_TYPE = {"propose_assignment": "assignment", "ask_assignment": "assignment", "memory": "memory", "briefing": "briefing",
            "orchestrator": "orchestrator", "ask_orchestrator": "orchestrator", "harvest": "harvest", "harvest_answer": "memory"}
AGENTS = ("assignment", "memory", "briefing", "orchestrator", "harvest")
TOKEN_PROFILE = {"harvest_answer": "memory"}             # hasat cevabı Hafıza Ajanı'ndan geçer: not profiliyle aynı


def load_assumptions(overrides: dict | None = None) -> dict:
    a = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    o = overrides or {}
    m = {"usd_try": ("money", "usd_try"), "courier_daily_cost_tl": ("courier", "daily_cost_tl"),
         "km_cost_tl": ("vehicle", "km_cost_tl"), "fails_other_tl": ("failed_delivery", "other_tl"),
         "second_attempt_min": ("failed_delivery", "second_attempt_min"), "daily_assignment_question": ("llm", "daily_assignment_question")}
    for k, (s1, s2) in m.items():
        if o.get(k) is not None:
            a[s1][s2] = float(o[k])
    for ag in AGENTS:
        a["llm"]["agent_model"].setdefault(ag, a["llm"]["agent_model"]["assignment"])
        v = o.get(f"model_{ag}")
        if v:
            if v not in a["llm"]["models"]:
                raise ValueError(f"Bilinmeyen model: {v}")
            a["llm"]["agent_model"][ag] = v
    sen = o.get("scenario")
    if sen:
        if sen not in a.get("scenarios", {}):
            raise ValueError(f"Bilinmeyen senaryo: {sen}")
        sc = a["scenarios"][sen]
        a["llm"]["cache"] = bool(sc["cache"])
        a["llm"]["agent_model"] = {**a["llm"]["agent_model"], **sc["agent_model"]}
        a["llm"]["scenario"] = sen
    for ag in AGENTS:                                  # senaryodan sonra tek tek ezme
        v = o.get(f"model_{ag}")
        if v:
            a["llm"]["agent_model"][ag] = v
    if o.get("cache") is not None:
        a["llm"]["cache"] = bool(o["cache"])
    return a


def _arm_day_avgs(daily: dict, arm: str) -> dict:
    d = daily[arm]
    n = len(d)
    return {
        "day": n,
        "shipment": sum(x["shipments"] for x in d) / n,
        "stop": sum(x["stops"] for x in d) / n,
        "fails": sum(x["fail"] for x in d) / n,
        "preventable": sum(x["preventable_fail"] for x in d) / n,
        "courier": sum(x["couriers"] for x in d) / n,
        "km": sum(x["km"] for x in d) / n,
        "overtime_min": sum(x["overtime_minutes"] for x in d) / n,
        "door_min": sum(x["door_minutes_per_stop"] * x["stops"] for x in d) / n,
        "note": sum(x["notes"] for x in d) / n,
        "first_attempt": sum(x["ok"] for x in d) / max(1, sum(x["attempted"] for x in d)),
    }


def _harvest_per_day(src_dir: Path) -> float:
    """Günde kaç hasat sorusu cevaplanır (her biri bir Hafıza Ajanı çağrısı): yayımlanan çalıştırmanın hasat istatistiği."""
    p = src_dir / "summary.json"
    if p.exists():
        h = json.loads(p.read_text(encoding="utf-8")).get("harvest") or {}
        if h.get("day"):
            return float(h["question"]) / float(h["day"])
    return 0.0


def call_cost_usd(tok: dict, price: dict, cached: bool) -> float:
    if cached:
        return (tok["cached_write"] * price["cache_write"] + tok["cached_read"] * price["cache_read"]
                + tok["output"] * price["output"]) / 1e6
    return (tok["input"] * price["input"] + tok["output"] * price["output"]) / 1e6


def compute(run: RunData, tokens: dict, assumptions: dict) -> dict:
    a = assumptions
    src_dir = run.dir / "long_term" if (run.dir / "long_term" / "daily.json").exists() else run.dir
    daily = json.loads((src_dir / "daily.json").read_text(encoding="utf-8"))["arms"]
    D, C, B, A = (_arm_day_avgs(daily, x) for x in "DCBA")
    # kol D'nin aynı rotası bugünkü sabahla (summary.sabah.counterfactual) → hafıza ile sabah kazancı ayrı kalem.
    summ_p = src_dir / "summary.json"
    sab = (json.loads(summ_p.read_text(encoding="utf-8")).get("morning") if summ_p.exists() else None) or {}
    ko = (sab.get("counterfactual") or {}).get("daily")
    if ko:
        D_current = dict(D, fails=D["fails"] + ko["current_morning"]["fail"] - ko["memory"]["fail"],
                       overtime_min=D["overtime_min"] + ko["current_morning"]["overtime_min"] - ko["memory"]["overtime_min"])
    else:
        D_current = D
    setup = a["money"]["usd_try"]
    min_tl = a["courier"]["daily_cost_tl"] / a["courier"]["shift_min"]
    bt = a["failed_delivery"]
    fails_tl = bt["second_attempt_min"] * min_tl + bt["second_attempt_km"] * a["vehicle"]["km_cost_tl"] + bt["other_tl"]
    fm = a["courier"]["overtime_multiplier"]
    cached = bool(a["llm"]["cache"])

    # --- hacim (şube-gün) ve LLM maliyeti
    q = float(a["llm"]["daily_assignment_question"])
    calls = {"propose_assignment": 1.0, "ask_assignment": q, "memory": D["note"], "briefing": D["courier"],
             "orchestrator": 1.0, "ask_orchestrator": q, "harvest": 1.0, "harvest_answer": _harvest_per_day(src_dir)}
    calls = {k: n for k, n in calls.items() if TOKEN_PROFILE.get(k, k) in tokens}
    per_agent = {}
    llm_usd = 0.0
    for k, n in calls.items():
        tk = tokens[TOKEN_PROFILE.get(k, k)]
        model = a["llm"]["agent_model"][AGENT_TYPE[k]]
        price = a["llm"]["models"][model]
        c = call_cost_usd(tk, price, cached)
        per_agent[k] = {"call_day": round(n, 1), "model": model, "token_call": {"input": tk["input"], "output": tk["output"]},
                        "per_call_tl": round(c * setup, 3), "daily_tl": round(c * n * setup, 1), "source": tk.get("source", "estimate")}
        llm_usd += c * n
    llm_tl = llm_usd * setup
    tok_day = {"input": round(sum(tokens[TOKEN_PROFILE.get(k, k)]["input"] * n for k, n in calls.items())),
               "output": round(sum(tokens[TOKEN_PROFILE.get(k, k)]["output"] * n for k, n in calls.items()))}

    def gain(base: dict, tag: str, ref: dict | None = None) -> dict:
        ref = D if ref is None else ref
        d_fail = base["fails"] - ref["fails"]
        d_ot = base["overtime_min"] - ref["overtime_min"]
        d_door = base["door_min"] - ref["door_min"]
        f_tl = d_fail * fails_tl
        ot_tl = d_ot * min_tl * fm
        direct = f_tl + ot_tl
        cap_tl = d_door * min_tl
        return {"comparison": tag,
                "prevented_fails_day": round(d_fail, 1), "fails_tl_day": round(f_tl),
                "prevented_overtime_min_day": round(d_ot), "overtime_tl_day": round(ot_tl),
                "gained_door_min_day": round(d_door), "capacity_tl_day": round(cap_tl),
                "capacity_courier_hour_day": round(d_door / 60, 1),
                "direct_gain_tl_day": round(direct), "net_tl_day": round(direct - llm_tl),
                "return_multiple": round(direct / llm_tl, 1) if llm_tl > 0 else None,
                "total_gain_tl_day": round(direct + cap_tl),
                "first_attempt_score": round(100 * (ref["first_attempt"] - base["first_attempt"]), 2)}

    # Hafızanın getirisi yalnız hafızayı ölçer: D bugünkü sabahla (sabah kazancı ayrı kalem, aşağıda).
    vs_c = gain(C, "Hafıza + Brifing (D, bugünkü sabahla) ← çekirdek bölgeli plan (C)", ref=D_current)
    vs_b = gain(B, "Ajan zinciri (D, sabah dahil) ← geçmişe bakmadan atama (B)")
    morning_k = gain(D_current, "Sabah: ayrıştırma indirme okutmasında (D) ← aynı rota bugünkü sabahla") if ko else None
    year = a["scale"]["workdays_per_year"]
    scale = [{"branch": s, "llm_tl_year": round(llm_tl * year * s), "direct_gain_tl_year_vs_C": round(vs_c["direct_gain_tl_day"] * year * s),
              "net_tl_year_vs_C": round(vs_c["net_tl_day"] * year * s), "net_tl_year_vs_B": round(vs_b["net_tl_day"] * year * s)}
             for s in a["scale"]["branch_counts"]]
    models = []
    for mid, p in a["llm"]["models"].items():
        usd = sum(call_cost_usd(tokens[TOKEN_PROFILE.get(k, k)], p, cached) * n for k, n in calls.items())
        models.append({"model": mid, "name": p["name"], "llm_tl_day": round(usd * setup, 1), "per_shipment_kurus": round(100 * usd * setup / D["shipment"], 2),
                         "return_multiple_vs_C": round(vs_c["direct_gain_tl_day"] / (usd * setup), 1) if usd else None})
    dynamic = {"explanation": "Dinamik planlamanın kazancı (bu çalışmanın değil). Hafıza bu kazancı kalite kaybı olmadan mümkün kılar.",
               "courier_day_diff": round(A["courier"] - D["courier"], 2),
               "courier_cost_tl_day": round((A["courier"] - D["courier"]) * a["courier"]["daily_cost_tl"]),
               "first_attempt_score_D_vs_A": round(100 * (D["first_attempt"] - A["first_attempt"]), 2),
               "first_attempt_score_B_vs_A": round(100 * (B["first_attempt"] - A["first_attempt"]), 2)}
    # --- Operasyon maliyeti (şube-gün): kurye + fazla mesai + başarısız teslim + km (+ LLM, ajanlı kollarda)
    km_tl = a["vehicle"]["km_cost_tl"]
    kg = a["courier"]["daily_cost_tl"]
    ARM_NAME = {"A": "Bugün · sabit bölge", "B": "Yeni yapı · ajansız", "C": "Yeni yapı + çekirdek bölge (Atama Ajanı)",
              "D": "Yeni yapı + Courier Memory"}

    def op(x: dict, arm: str) -> dict:
        parts = {"courier": x["courier"] * kg, "overtime": x["overtime_min"] * min_tl * fm, "fails": x["fails"] * fails_tl,
                 "km": x["km"] * km_tl, "llm": llm_tl if arm == "D" else (per_agent["propose_assignment"]["daily_tl"] + per_agent["ask_assignment"]["daily_tl"] if arm == "C" else 0.0)}
        tot = sum(parts.values())
        return {"name": ARM_NAME[arm], "courier": round(x["courier"], 1), "fails_per_day": round(x["fails"]), "preventable_day": round(x["preventable"]),
                "overtime_hour_day": round(x["overtime_min"] / 60, 1), "km_day": round(x["km"]), "first_attempt": round(x["first_attempt"], 5),
                "components_tl_day": {k: round(v) for k, v in parts.items()}, "total_tl_day": round(tot),
                "per_shipment_tl": round(tot / x["shipment"], 2), "total_tl_year": round(tot * year)}

    ops = {k: op(v, k) for k, v in (("A", A), ("B", B), ("C", C), ("D", D))}
    d_current_tl = op(D_current, "D")["total_tl_day"]
    plan = ops["A"]["total_tl_day"] - ops["A"]["components_tl_day"]["courier"] + ops["D"]["components_tl_day"]["courier"]
    waterfall = [
        {"code": "today", "step": "Bugün (sabit bölge)", "type": "start", "tl_day": ops["A"]["total_tl_day"]},
        {"code": "dynamic", "step": "Dinamik planlama: daha az kurye, dengeli iş yükü", "type": "decrease", "tl_day": round(plan - ops["A"]["total_tl_day"])},
        {"code": "agentless", "step": "Ajansız: bölge bilgisi kaybı (başarısız teslim, fazla mesai)", "type": "increase", "tl_day": round(ops["B"]["total_tl_day"] - plan)},
        {"code": "assignment", "step": "Atama Ajanı: çekirdek bölgeli plan, kurye kendi bölgesinde", "type": "decrease",
         "tl_day": round(ops["C"]["total_tl_day"] - ops["B"]["total_tl_day"])},
        {"code": "memory", "step": "Hafıza + Brifing: bilgi kişiden adrese", "type": "decrease", "tl_day": round(d_current_tl - ops["C"]["total_tl_day"])},
        *([{"code": "morning", "step": "Sabah: ayrıştırma indirme okutmasında (kurye ayrıştırma yapmaz, erken çıkar)", "type": "decrease",
            "tl_day": round(ops["D"]["total_tl_day"] - d_current_tl)}] if ko else []),
        {"code": "result", "step": "Yeni yapı + Courier Memory", "type": "result", "tl_day": ops["D"]["total_tl_day"]},
    ]
    saving_day = ops["A"]["total_tl_day"] - ops["D"]["total_tl_day"]
    agentless_day = ops["B"]["total_tl_day"] - ops["A"]["total_tl_day"]
    headline = {
        "savings_tl_day": round(saving_day), "savings_tl_year": round(saving_day * year),
        "savings_rate": round(saving_day / ops["A"]["total_tl_day"], 4),
        "per_shipment_before_tl": ops["A"]["per_shipment_tl"], "per_shipment_after_tl": ops["D"]["per_shipment_tl"],
        "agentless_extra_cost_tl_day": round(agentless_day), "agentless_extra_cost_tl_year": round(agentless_day * year),
        "agents_saved_tl_day": round(ops["B"]["total_tl_day"] - ops["D"]["total_tl_day"]),
        "quality": {"fails_per_day_current": ops["A"]["fails_per_day"], "fails_per_day_agentless": ops["B"]["fails_per_day"],
                   "fails_per_day_memory": ops["D"]["fails_per_day"]},
        "llm_share": round(llm_tl / saving_day, 4) if saving_day > 0 else None,
        "sentence": (f"Şube başına günde {num(saving_day, 0)} TL, yılda {num(saving_day * year / 1e6, 1)} milyon TL daha düşük operasyon maliyeti; "
                  f"başarısız teslim bugünkü düzeyde ({ops['A']['fails_per_day']} → {ops['D']['fails_per_day']}/gün). "
                  f"Ajansız aynı geçiş maliyeti günde {num(agentless_day, 0)} TL artırırdı."),
    }
    llm_scenario = []
    for sk, sc in a.get("scenarios", {}).items():
        usd = sum(call_cost_usd(tokens[TOKEN_PROFILE.get(k, k)], a["llm"]["models"][{**a["llm"]["agent_model"], **sc["agent_model"]}[AGENT_TYPE[k]]], bool(sc["cache"])) * n for k, n in calls.items())
        llm_scenario.append({"scenario": sk, "name": sc["name"], "llm_tl_day": round(usd * setup, 1), "llm_tl_year": round(usd * setup * year),
                            "per_shipment_kurus": round(100 * usd * setup / D["shipment"], 3),
                            "savings_rate": round(usd * setup / saving_day, 5) if saving_day > 0 else None,
                            "memory_return_multiple": round(vs_c["direct_gain_tl_day"] / (usd * setup), 1) if usd else None})
    scale_op = [{"branch": s_, "savings_tl_year": round(saving_day * year * s_), "agentless_extra_cost_tl_year": round(agentless_day * year * s_)}
                for s_ in a["scale"]["branch_counts"]]
    return {
        "app_data": True,
        "headline": headline,
        "llm_scenarios": llm_scenario,
        "scenario": a["llm"].get("scenario"),
        "operation": {"arms": ops, "waterfall": waterfall, "scale": scale_op,
                      "explanation": "Operasyon maliyeti = kurye-gün × kurye maliyeti + fazla mesai + başarısız teslim × deneme maliyeti + km × km maliyeti + LLM."},
        "source_running": "long_term" if src_dir != run.dir else "demo",
        "day_count": D["day"],
        "assumptions": {"usd_try": setup, "courier_daily_cost_tl": a["courier"]["daily_cost_tl"], "courier_min_tl": round(min_tl, 2),
                        "km_cost_tl": a["vehicle"]["km_cost_tl"], "failed_attempt_tl": round(fails_tl, 1),
                        "fails_other_tl": bt["other_tl"], "second_attempt_min": bt["second_attempt_min"],
                        "overtime_multiplier": fm, "cache": cached, "price_source": a["llm"]["price_source"],
                        "agent_model": a["llm"]["agent_model"], "daily_assignment_question": a["llm"]["daily_assignment_question"]},
        "volume_day": {"shipment": round(D["shipment"]), "stop": round(D["stop"]), "courier": round(D["courier"], 1),
                      "note": round(D["note"], 1), "llm_call": round(sum(calls.values()), 1), "token": tok_day},
        "llm": {"daily_tl": round(llm_tl, 1), "daily_usd": round(llm_usd, 2), "agents": per_agent,
                "per_shipment_kurus": round(100 * llm_tl / D["shipment"], 2),
                "per_note_tl": per_agent["memory"]["per_call_tl"], "per_briefing_tl": per_agent["briefing"]["per_call_tl"]},
        "gain": {"vs_C": vs_c, "vs_B": vs_b},
        "morning": ({"departure_current_min": sab.get("current_min"), "departure_presorted_min": sab.get("presorted_min"),
                   "overtime_min_day": round(ko["current_morning"]["overtime_min"] - ko["memory"]["overtime_min"]),
                   "fails_per_day": round(ko["current_morning"]["fail"] - ko["memory"]["fail"], 1),
                   "tl_day": round(d_current_tl - ops["D"]["total_tl_day"]), "tl_year": round((d_current_tl - ops["D"]["total_tl_day"]) * year),
                   "overtime_tl_day": morning_k["overtime_tl_day"], "fails_tl_day": morning_k["fails_tl_day"], "gain": morning_k,
                   "note": "Aynı rota bugünkü sabahla (summary.sabah.counterfactual). Sabah süreleri şube beyanıdır. Erken "
                          "çıkışın vardiya içinde açtığı kapasite (daha az kurye ihtiyacı) ayrıca para değerine çevrilmedi."} if ko else None),
        "branch_annual": {"llm_tl": round(llm_tl * year), "net_tl_vs_C": round(vs_c["net_tl_day"] * year), "net_tl_vs_B": round(vs_b["net_tl_day"] * year)},
        "scale": scale,
        "model_comparison": models,
        "dynamic_planning": dynamic,
        "warning": "Uygulama verisi · 1 aylık geçmiş. Maliyet parametreleri tahminidir; token sayıları canlı ölçümle güncellenir.",
    }


def load_tokens(run: RunData) -> dict:
    p = run.dir / "token_usage.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))["agents"]
    from .cost import estimate
    return estimate(str(run.dir))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agents.economics")
    ap.add_argument("--run", default=None)
    a = ap.parse_args(argv)
    run = RunData(a.run)
    res = compute(run, load_tokens(run), load_assumptions())
    (run.dir / "economics.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    L, K = res["llm"], res["gain"]
    print(f"Kaynak: {res['source_running']} ({res['day_count']} gün) · şube-gün: {res['volume_day']}")
    print(f"LLM: {L['daily_tl']:.0f} TL/gün · gönderi başı {L['per_shipment_kurus']} kuruş · not başı {L['per_note_tl']} TL")
    for k in ("vs_C", "vs_B"):
        x = K[k]
        print(f"{x['comparison']}: önlenen başarısız {x['prevented_fails_day']}/gün → {x['direct_gain_tl_day']} TL/gün doğrudan, "
              f"net {x['net_tl_day']} TL/gün, getiri {x['return_multiple']}×; kapasite {x['capacity_courier_hour_day']} kurye-saat/gün")
    print("Model karşılaştırma:", [(m["name"], m["llm_tl_day"], m["return_multiple_vs_C"]) for m in res["model_comparison"]])
    print(json.dumps(res["scale"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

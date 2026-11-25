"""Brifing Ajanı: sabah sesli brifingi ve kapıda tek cümlelik ipuçları.

Faz 2: rota ONAYLANMIŞ plandan okunur (müdür onayladıysa `SessionStore.planlar[gün]`, yoksa simülatörün D planı) ve
Orkestratör'ün `compute_route` aracıyla hesaplanır: dönüş saati kuryeye özgü `EtaModel` süresinden gelir (planlanan süre
değil), hafızanın rotada yaptığı değişiklikler (öğle arasından kaçırılan, plandan çıkan duraklar) brifinge girer. Kapı
ipuçları güne ve saate göre süzülür (Çarşamba "Cumartesi kapalı" okunmaz; varışı öğle arasından uzak durakta öğle uyarısı yok).
"""
from __future__ import annotations

from pathlib import Path

from .llm import LLM, AgentError, Tool, obj
from .memorybook import MemoryBook
from .rundata import KIND_TR, RunData
from .tr import hhmm

PROMPT = (Path(__file__).parent / "prompts" / "briefing.md").read_text(encoding="utf-8")
LUNCH = (720, 810)
LUNCH_HINT_BEFORE = 60          # varış öğle arasından en çok bu kadar önceyse öğle ipucu söylenir (kurye gecikebilir)
OUT_SCHEMA = obj({
    "morning_briefing": {"type": "string"},
    "door_sentences": {"type": "array", "items": obj({"address": {"type": "integer"}, "sentence": {"type": "string"}})},
    "warnings": {"type": "array", "items": {"type": "string"}},
})


def hint_today_valid(kind: str, weekday: int, eta: float, window: tuple[int, int] | None = None) -> bool:
    """Kapı ipucu bugün ve bu varış saatinde anlamlı mı? (D1: bağlama göre süzme)"""
    if kind == "saturday_closed":
        return weekday == 5
    if kind == "lunch_break":
        lo, hi = window or LUNCH
        return lo - LUNCH_HINT_BEFORE <= eta < hi
    return True


class BriefingTools:
    def __init__(self, run: RunData, book: MemoryBook, day: int, courier: str, plan: dict | None = None):
        from .orchestrator import DayTools

        self.run, self.book, self.day, self.courier = run, book, day, courier
        snap = run.snapshot("D", day)
        self.F = {k: i for i, k in enumerate(snap["stop_fields"])}
        row = next((r for r in (plan or {}).get("assignment", []) if r["courier"] == courier), None)
        if plan is not None and row is None:
            raise ValueError(f"{courier} gün {day} onaylı planda yok (yedekte)")
        if row is not None:
            cluster, self.plan_source = int(row["cluster"]), "approved_plan"
        else:
            r = run.route_of(day, courier)
            if r is None:
                raise ValueError(f"{courier} gün {day} çalışmıyor")
            cluster, self.plan_source = int(r["route"]), "simulation_plan"
        self.route = next(r for r in snap["routes"] if r["route"] == cluster)
        self.cluster = cluster
        ar = DayTools(run, book, day)
        self.route_result = ar.compute_route({"cluster_id": cluster, "courier_id": courier}) if courier in ar.cid else None

    def route_risks(self, _: dict | None = None) -> dict:
        F, r = self.F, self.route
        wd = self.day % 6
        by_addr = {int(s[F["address"]]): s for s in r["stops"]}
        hz = ((self.route_result or {}).get("comparison") or {}).get("memory", {})
        order = hz.get("order") or list(by_addr)
        # Sabah brifingi PLANLANAN beklenen varışı kullanır (rota aracından); simülasyonda gerçekleşen varış sabah bilinmez.
        plan_eta = dict(zip(hz.get("order") or [], hz.get("expected_arrival") or []))
        stops = [by_addr[a] for a in order if a in by_addr]
        hinted, warns, filtered = [], [], 0
        unf = sum(1 for s in stops if s[F["unfamiliar"]])
        unf_cov = 0
        for i, s in enumerate(stops):
            a = int(s[F["address"]])
            eta = float(plan_eta.get(a, s[F["eta"]]))
            mem = self.book.for_address(a, self.day)
            if s[F["unfamiliar"]] and mem:
                unf_cov += 1
            ok = [m for m in mem if hint_today_valid(m["kind"], wd, eta, m.get("window"))]
            filtered += len(mem) - len(ok)
            if ok:
                hinted.append({"order": i + 1, "address": a, "label": self.run.addr_label[a], "arrival": hhmm(eta),
                               "unfamiliar": bool(s[F["unfamiliar"]]), "hints": [m["text"] for m in ok],
                               "types": [m["kind"] for m in ok]})
                kinds = {m["kind"] for m in ok}
                if "lunch_break" in kinds and LUNCH[0] <= eta < LUNCH[1]:
                    warns.append(f"{i + 1}. durağa varış ({hhmm(eta)}) öğle arasına denk geliyor; önce ya da sonra uğrayın.")
                if "saturday_closed" in kinds:
                    warns.append(f"{i + 1}. durak cumartesi kapalı; gönderi pazartesiye kalabilir.")
                if "temporary_closed" in kinds:
                    warns.append(f"{i + 1}. durak geçici olarak kapalı olabilir (tek kaynak); kapıda teyit edin.")
        route_result = self.route_result or {}
        ch = route_result.get("changes") or []
        carried = [c for c in ch if c["type"] == "window"]
        deferred = [c for c in ch if c["type"] == "deferred"]
        change = []
        if carried:
            change.append(f"{len(carried)} durak öğle arasına denk gelmesin diye öne ya da sonraya alındı")
        if deferred:
            change.append(f"bugün kapalı {len(deferred)} durak plandan çıkarıldı, boşuna gitmeyeceksin")
        planned = float(r.get("planned_minutes", r["minutes"]))
        return {"courier": self.courier, "name": self.run.courier_name(self.courier),
                "type": KIND_TR.get(self.run.courier_kind(self.courier), "?"), "day": self.day,
                "weekday": self.run.weekday_name(self.day), "cluster": self.cluster, "plan_source": self.plan_source,
                "stop": len(stops), "shipment": int(sum(s[F["n"]] for s in stops)), "start": route_result.get("start") or "09:00",
                "estimated_return": route_result.get("estimated_return") or hhmm(float(route_result.get("start_min", 540)) + planned),
                "expected_min": route_result.get("expected_min") or round(planned),
                "planned_return": hhmm(float(route_result.get("start_min", 540)) + planned), "km": r["km"], "unfamiliar_stop": unf,
                "unfamiliar_and_memory": unf_cov, "hinted_stops": hinted, "filtered_hint": filtered,
                "route_changes": [c["text"] for c in ch], "route_change_summary": change,
                "warnings": [c["text"] for c in deferred + carried][:2] + warns}


class BriefingAgent:
    def __init__(self, run: RunData, book: MemoryBook, llm: LLM, plans: dict | None = None):
        self.run, self.book, self.llm = run, book, llm
        self.plans = plans if plans is not None else {}

    def prepare(self, day: int, courier: str) -> dict:
        self.book.ensure(day)
        ar = BriefingTools(self.run, self.book, day, courier, self.plans.get(day))
        if self.llm.uses_llm:
            try:
                tools = [Tool("route_risks", "Kuryenin bugünkü (onaylı plandaki) rotası: durak/gönderi, kuryeye özgü dönüş saati, "
                                               "hafızanın rotada yaptığı değişiklikler, yabancı ve hafızalı duraklar, güne/saate göre "
                                               "süzülmüş ipuçlu duraklar ve uyarılar.", obj({}), ar.route_risks,
                              lambda i, r: f"{r['stop']} durak, {len(r['hinted_stops'])} ipuçlu, dönüş {r['estimated_return']}")]
                run = self.llm.run_agent(agent="briefing", system=PROMPT, tools=tools, output_schema=OUT_SCHEMA, effort="low",
                                         user=f"Gün {day}, kurye {courier} için sabah brifingini ve kapı cümlelerini hazırla.")
                if not run.final_input:
                    raise AgentError("Brifing üretilmedi")
                return self._result(ar, run.final_input, run.steps, degraded=False)
            except Exception as e:
                res = self._mock(ar)
                res.update(degraded=True, error=str(e))
                return res
        return self._mock(ar)

    def _result(self, ar: BriefingTools, out: dict, steps: list[dict], degraded: bool) -> dict:
        order = {int(s[ar.F["address"]]): i + 1 for i, s in enumerate(ar.route["stops"])}
        kc = []
        for k in out.get("door_sentences", []):
            a = int(k["address"])
            if a not in order:
                continue
            mem = self.book.for_address(a, ar.day)
            kc.append({"address": a, "sentence": k["sentence"], "order": order[a],
                       "records": [{"id": m["id"], "type": m["kind"], "text": m["text"]} for m in mem]})
        kc.sort(key=lambda x: x["order"])
        rr = ar.route_result or {}
        return {"day": ar.day, "courier": ar.courier, "courier_name": self.run.courier_name(ar.courier),
                "courier_type": self.run.courier_kind(ar.courier), "mode": self.llm.mode, "degraded": degraded,
                "plan_source": ar.plan_source, "estimated_return": rr.get("estimated_return"), "expected_min": rr.get("expected_min"),
                "morning_briefing": out.get("morning_briefing", ""), "door_sentences": kc, "warnings": out.get("warnings", [])[:3],
                "route_changes": rr.get("changes", []), "route_comparison": rr.get("comparison"),
                "route": ar.route, "stop_fields": self.run.snapshot("D", ar.day)["stop_fields"], "steps": steps}

    def _mock(self, ar: BriefingTools) -> dict:
        r = ar.route_risks()
        steps = [{"tool": "route_risks", "input": {}, "summary": f"{r['stop']} durak, {len(r['hinted_stops'])} ipuçlu, dönüş {r['estimated_return']}"}]
        parts = [f"Günaydın {r['name']}. Bugün {r['stop']} durak, {r['shipment']} gönderi var; tahmini dönüş {r['estimated_return']}."]
        if r["unfamiliar_stop"]:
            parts.append(f"{r['unfamiliar_stop']} durakta bölgeyi ilk kez görüyorsun; bunların {r['unfamiliar_and_memory']} tanesinde "
                         f"hafızada not var, kapıya yaklaşınca söyleyeceğim.")
        elif r["hinted_stops"]:
            parts.append(f"{len(r['hinted_stops'])} durakta hafızada not var; kapıya yaklaşınca söyleyeceğim.")
        if r["route_change_summary"]:
            parts.append("Hafıza rotanı düzenledi: " + "; ".join(r["route_change_summary"]) + ".")
        elif r["warnings"]:
            parts.append(r["warnings"][0])
        parts.append("İyi yolculuklar.")
        kc = [{"address": h["address"], "sentence": h["hints"][0]} for h in r["hinted_stops"]]
        return self._result(ar, {"morning_briefing": " ".join(parts), "door_sentences": kc, "warnings": r["warnings"]}, steps, False)

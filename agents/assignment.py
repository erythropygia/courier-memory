"""Atama Ajanı: günün kümelerine kurye atanmasını önerir, gerekçelendirir, senaryo sorularını yanıtlar.

Hesap (beklenen başarısızlık, Hungarian) deterministik araçlardadır; ajan araçları çağırır, kararı ve
açıklamayı üretir. mock modunda ya da canlı çağrı hata verirse aynı araçlarla şablon gerekçe üretilir.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from .llm import LLM, AgentError, Tool, obj
from .rundata import KIND_TR, RunData
from .tr import dative, num

PROMPT = (Path(__file__).parent / "prompts" / "assignment.md").read_text(encoding="utf-8")


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def solve(cost: np.ndarray, rows_ok: list[int], cols: list[int], fixed: dict[int, int]) -> dict[int, int]:
    """Hungarian: {sütun: satır}. fixed: {sütun: satır} zorunlu eşlemeler."""
    out = dict(fixed)
    rows = [r for r in rows_ok if r not in fixed.values()]
    cs = [c for c in cols if c not in fixed]
    if len(rows) < len(cs):
        raise ValueError(f"Yeterli kurye yok: {len(rows)} kurye, {len(cs)} küme")
    if cs:
        ri, ci = linear_sum_assignment(cost[np.ix_(rows, cs)])
        for a, b in zip(ri, ci):
            out[cs[b]] = rows[a]
    return out


class AssignmentTools:
    """Atama Ajanı'nın deterministik araçları (assign/D/<gün>.json üzerinde)."""

    def __init__(self, run: RunData, day: int, arm: str = "D"):
        self.run, self.day = run, day
        ai = run.assign_input(arm, day)
        self.ai = ai
        self.cour = ai["couriers"]
        self.clus = ai["clusters"]
        self.cid = [c["id"] for c in self.cour]
        self.kid = [k["id"] for k in self.clus]
        self.M = {k: np.array(ai[k], dtype=float) for k in ai["matrix_fields"]}
        self.baseline = {int(k): v for k, v in ai["chosen"].items()}
        self.unavailable = ai.get("unavailable", [])

    # --- yardımcılar
    def ci(self, courier: str) -> int:
        if courier not in self.cid:
            raise ValueError(f"Bilinmeyen ya da bugün müsait olmayan kurye: {courier}")
        return self.cid.index(courier)

    def ki(self, cluster: int) -> int:
        if cluster not in self.kid:
            raise ValueError(f"Bilinmeyen küme: {cluster}")
        return self.kid.index(cluster)

    def resolve_courier(self, text: str) -> list[str]:
        """Metinde geçen kurye kimlik/adları (geçiş sırasıyla)."""
        t = tr_lower(text)
        found: list[tuple[int, str]] = []
        for c in self.run.couriers.values():
            for token in (tr_lower(c["id"]), tr_lower(c["name"])):
                m = re.search(r"\b" + re.escape(token), t)
                if m:
                    found.append((m.start(), c["id"]))
                    break
        found.sort()
        out: list[str] = []
        for _, c in found:
            if c not in out:
                out.append(c)
        return out

    def rows(self, mapping: dict[int, str]) -> list[dict]:
        out = []
        for k in sorted(mapping):
            c = mapping[k]
            i, j = self.ci(c), self.ki(k)
            cl = self.clus[j]
            out.append({"cluster": k, "courier": c, "courier_name": self.run.courier_name(c), "courier_type": self.run.courier_kind(c),
                        "stop": cl["stops"], "shipment": cl["shipments"],
                        "expected_fails": round(float(self.M["exp_fail"][i, j]), 2),
                        "unfamiliar_stop": int(self.M["unfamiliar"][i, j]),
                        "memory_unfamiliar": int(self.M["covered_unfamiliar"][i, j]),
                        "planned_min": cl["planned_minutes"], "center": cl["center"]})
        return out

    def totals(self, mapping: dict[int, str]) -> dict:
        t = {"expected_fails": 0.0, "unfamiliar_stop": 0, "memory_unfamiliar": 0, "cost": 0.0}
        for k, c in mapping.items():
            i, j = self.ci(c), self.ki(k)
            t["expected_fails"] += float(self.M["exp_fail"][i, j])
            t["unfamiliar_stop"] += int(self.M["unfamiliar"][i, j])
            t["memory_unfamiliar"] += int(self.M["covered_unfamiliar"][i, j])
            t["cost"] += float(self.M["cost"][i, j])
        t["expected_fails"] = round(t["expected_fails"], 1)
        t["cost"] = round(t["cost"], 1)
        return t

    def own_share(self, mapping: dict[int, str]) -> float:
        """Kuryelerin kendi (çekirdek) bölgesinde olduğu durak payı."""
        tot = sum(k["stops"] for k in self.clus)
        unf = self.totals(mapping)["unfamiliar_stop"]
        return 1 - unf / max(1, tot)

    def random_expected(self) -> float:
        """Geçmişe bakmadan (rastgele) atamada beklenen başarısız teslim: küme başına kurye ortalaması."""
        return round(float(self.M["exp_fail"].mean(axis=0).sum()), 1)

    def idle(self, mapping: dict[int, str]) -> list[dict]:
        used = set(mapping.values())
        return [{"id": c, "name": self.run.courier_name(c), "type": self.run.courier_kind(c)} for c in self.cid if c not in used]

    # --- araçlar
    def day_summary(self, _: dict | None = None) -> dict:
        return {
            "day": self.day, "weekday": self.run.weekday_name(self.day), "cluster_count": len(self.kid),
            "available_couriers": [{"id": c["id"], "name": c["name"], "type": KIND_TR.get(c["kind"], c["kind"])} for c in self.cour],
            "on_leave_or_absent": [{"id": u["id"], "name": u["name"], "type": KIND_TR.get(u["kind"], u["kind"])} for u in self.unavailable],
            "total_stop": sum(k["stops"] for k in self.clus), "total_shipment": sum(k["shipments"] for k in self.clus),
            "own_zone_stop_share": round(self.own_share(self.baseline), 3),
            "history_blind_expected_fails": self.random_expected(),
        }

    def cluster_detail(self, inp: dict) -> dict:
        k = int(inp["cluster_id"])
        j = self.ki(k)
        cl = self.clus[j]
        order = np.argsort(self.M["cost"][:, j])[:4]
        return {"cluster": k, "stop": cl["stops"], "shipment": cl["shipments"], "planned_min": cl["planned_minutes"],
                "km": cl["km"], "block_count": len(cl["blocks"]),
                "best_couriers": [{"courier": self.cid[i], "name": self.run.courier_name(self.cid[i]),
                                       "expected_fails": round(float(self.M["exp_fail"][i, j]), 2),
                                       "unfamiliar_stop": int(self.M["unfamiliar"][i, j]),
                                       "memory_unfamiliar": int(self.M["covered_unfamiliar"][i, j])} for i in order]}

    def courier_detail(self, inp: dict) -> dict:
        c = inp["courier_id"]
        i = self.ci(c)
        order = np.argsort(self.M["cost"][i, :])[:3]
        return {"courier": c, "name": self.run.courier_name(c), "type": KIND_TR.get(self.run.courier_kind(c), "?"),
                "best_clusters": [{"cluster": self.kid[j], "expected_fails": round(float(self.M["exp_fail"][i, j]), 2),
                                      "unfamiliar_stop": int(self.M["unfamiliar"][i, j]),
                                      "memory_unfamiliar": int(self.M["covered_unfamiliar"][i, j])} for j in order]}

    def solve_assignment(self, inp: dict) -> dict:
        excl = set(inp.get("exclude") or [])
        fixed_in = inp.get("pin") or []
        for c in excl:
            self.ci(c)
        fixed = {self.ki(int(f["cluster_id"])): self.ci(f["courier_id"]) for f in fixed_in}
        rows_ok = [i for i, c in enumerate(self.cid) if c not in excl]
        left = solve(self.M["cost"], rows_ok, list(range(len(self.kid))), fixed)
        mapping = {self.kid[j]: self.cid[i] for j, i in left.items()}
        base_t = self.totals(self.baseline)
        t = self.totals(mapping)
        changed = [k for k in mapping if self.baseline.get(k) != mapping[k]]
        return {"assignment": [{"cluster_id": k, "courier_id": c} for k, c in sorted(mapping.items())],
                "rows": self.rows(mapping), "total": t,
                "previous_total": base_t,
                "diff": {"expected_fails": round(t["expected_fails"] - base_t["expected_fails"], 1),
                         "unfamiliar_stop": t["unfamiliar_stop"] - base_t["unfamiliar_stop"],
                         "memory_unfamiliar": t["memory_unfamiliar"] - base_t["memory_unfamiliar"]},
                "changed_clusters": changed, "idle_couriers": self.idle(mapping)}

    def validate(self, assignment: list[dict]) -> dict[int, str]:
        mapping = {int(a["cluster_id"]): a["courier_id"] for a in assignment}
        if set(mapping) != set(self.kid):
            raise ValueError(f"Atama tüm kümeleri kapsamalı (eksik: {sorted(set(self.kid) - set(mapping))})")
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("Aynı kurye birden fazla kümeye atanmış")
        for c in mapping.values():
            self.ci(c)
        return mapping


ASSIGNMENT_ITEM = obj({"cluster_id": {"type": "integer"}, "courier_id": {"type": "string"}})


class AssignmentAgent:
    def __init__(self, run: RunData, llm: LLM):
        self.run, self.llm = run, llm

    def _tools(self, ar: AssignmentTools, finish: str) -> list[Tool]:
        tools = [
            Tool("day_summary", "Günün kümeleri, müsait ve izinli kuryeler, geçmişe bakmadan atamada beklenen başarısız teslim.",
                 obj({}), ar.day_summary, lambda i, r: f"{r['cluster_count']} küme, {len(r['available_couriers'])} müsait kurye"),
            Tool("cluster_detail", "Bir kümenin durak/gönderi/süre bilgisi ve bu küme için en uygun 4 kurye.",
                 obj({"cluster_id": {"type": "integer"}}), ar.cluster_detail, lambda i, r: f"küme {r['cluster']}: {r['stop']} durak"),
            Tool("courier_detail", "Bir kurye için en uygun 3 küme ve kuryenin türü.",
                 obj({"courier_id": {"type": "string"}}), ar.courier_detail, lambda i, r: f"{r['name']} ({r['type']})"),
            Tool("solve_assignment", "Hungarian ile en düşük maliyetli atamayı çözer. exclude: atanmayacak kurye kimlikleri; "
                              "sabitle: zorunlu küme→kurye eşlemeleri. Önceki atamaya göre farkı da döndürür.",
                 obj({"exclude": {"type": "array", "items": {"type": "string"}},
                      "pin": {"type": "array", "items": ASSIGNMENT_ITEM}}), ar.solve_assignment,
                 lambda i, r: f"beklenen başarısız {r['total']['expected_fails']} (fark {r['diff']['expected_fails']:+})"),
        ]
        if finish == "save_assignment":
            tools.append(Tool("save_assignment", "Önerilen atamayı, gerekçeyi ve öne çıkanları kaydeder (son adım).",
                              obj({"assignment": {"type": "array", "items": ASSIGNMENT_ITEM},
                                   "rationale": {"type": "array", "items": {"type": "string"}},
                                   "highlights": {"type": "array", "items": {"type": "string"}}})))
        else:
            tools.append(Tool("respond", "Şube müdürüne cevabı verir (son adım). Atama değiştiyse yeni atamayı da ver, değişmediyse boş liste.",
                              obj({"response": {"type": "string"}, "assignment": {"type": "array", "items": ASSIGNMENT_ITEM}})))
        return tools

    # ------------------------------------------------------------------ öneri
    def propose(self, day: int) -> dict:
        ar = AssignmentTools(self.run, day)
        if self.llm.uses_llm:
            try:
                run = self.llm.run_agent(agent="assignment", system=PROMPT, tools=self._tools(ar, "save_assignment"),
                                         finish_tool="save_assignment", effort="medium",
                                         user=f"Gün {day} ({self.run.weekday_name(day)}) için kurye atamasını öner.")
                if not run.final_input:
                    raise AgentError("Ajan atamayı kaydetmedi")
                mapping = ar.validate(run.final_input["assignment"])
                return self._result(ar, mapping, run.final_input.get("rationale", []), run.final_input.get("highlights", []),
                                    run.steps, degraded=False)
            except Exception as e:  # canlı yol başarısız → deterministik yedek
                res = self._propose_mock(ar)
                res.update(degraded=True, error=str(e))
                return res
        return self._propose_mock(ar)

    def _propose_mock(self, ar: AssignmentTools) -> dict:
        steps = [{"tool": "day_summary", "input": {}, "summary": ""}, {"tool": "solve_assignment", "input": {"exclude": [], "pin": []}, "summary": ""}]
        oz = ar.day_summary()
        steps[0]["summary"] = f"{oz['cluster_count']} küme, {len(oz['available_couriers'])} müsait kurye"
        r = ar.solve_assignment({"exclude": [], "pin": []})
        mapping = {a["cluster_id"]: a["courier_id"] for a in r["assignment"]}
        steps[1]["summary"] = f"beklenen başarısız {r['total']['expected_fails']}"
        rationale, one = self._template(ar, mapping, oz)
        return self._result(ar, mapping, rationale, one, steps, degraded=False)

    def _template(self, ar: AssignmentTools, mapping: dict[int, str], oz: dict) -> tuple[list[str], list[str]]:
        t = ar.totals(mapping)
        rnd = oz["history_blind_expected_fails"]
        g = [f"Önerilen atamada beklenen başarısız teslim {t['expected_fails']:.0f}; kuryeler geçmişe bakmadan atansaydı "
             f"{rnd:.0f} olurdu (%{100 * (1 - t['expected_fails'] / rnd):.0f} daha az)."]
        g.insert(0, f"Kendi çekirdek bölgesinde kalınan durak payı: %{100 * ar.own_share(mapping):.0f}. Dinamik plan kuryeyi kaydırmıyor; "
                    f"yalnız sınırları ve fazla işi günün talebine göre esnetiyor.")
        g.append(f"Kuryenin bölgeye yabancı olduğu {t['unfamiliar_stop']} durağın {t['memory_unfamiliar']} tanesinde hafızada not var; "
                 f"bu duraklarda kapıda ipucu verilecek.")
        if oz["on_leave_or_absent"]:
            g.append("Bugün çalışmayan: " + ", ".join(f"{u['name']} ({u['type']})" for u in oz["on_leave_or_absent"]) + ".")
        idle = ar.idle(mapping)
        if idle:
            g.append(f"{len(mapping)} küme için {len(mapping)} kurye yeterli; {len(idle)} kurye yedekte bekliyor: "
                     + ", ".join(i["name"] for i in idle[:4]) + ".")
        one = []
        rows = [x for x in ar.rows(mapping) if x["courier_type"] in ("new", "borrowed", "reserve")]
        rows.sort(key=lambda x: -x["unfamiliar_stop"])
        for x in rows[:3]:
            one.append(f"{x['courier_name']} ({KIND_TR.get(x['courier_type'], '')}) küme {x['cluster']}{dative(x['cluster'])} gidiyor: "
                       f"{x['unfamiliar_stop']} yabancı durağın {x['memory_unfamiliar']} tanesinde hafıza notu var.")
        if not one:
            x = max(ar.rows(mapping), key=lambda x: x["unfamiliar_stop"])
            one.append(f"En çok yabancı durak küme {x['cluster']}'de ({x['courier_name']}): {x['unfamiliar_stop']} durak, "
                       f"{x['memory_unfamiliar']} tanesi hafızalı.")
        return g, one

    def _result(self, ar: AssignmentTools, mapping: dict[int, str], rationale: list[str], one: list[str], steps: list[dict],
                degraded: bool) -> dict:
        idle = ar.idle(mapping)
        return {"day": ar.day, "mode": self.llm.mode, "degraded": degraded, "assignment": ar.rows(mapping),
                "total": ar.totals(mapping), "comparison": {"history_blind_expected_fails": ar.random_expected()},
                "on_leave": [{"id": u["id"], "name": u["name"], "type": u["kind"]} for u in ar.unavailable],
                "idle_available": idle, "rationale": rationale, "highlights": one, "steps": steps}

    # ------------------------------------------------------------------ senaryo sorusu
    def ask(self, day: int, question: str, history: list[dict] | None = None, current: list[dict] | None = None) -> dict:
        ar = AssignmentTools(self.run, day)
        if current:
            try:
                ar.baseline = ar.validate([{"cluster_id": int(m["cluster"]), "courier_id": m["courier"]} for m in current])
            except ValueError:
                pass
        if self.llm.uses_llm:
            try:
                hist = []
                for h in history or []:
                    hist.append({"role": "user" if h.get("role") == "manager" else "assistant", "content": str(h.get("text", ""))})
                if hist and hist[0]["role"] != "user":
                    hist.insert(0, {"role": "user", "content": "(önceki konuşma)"})
                cur = ", ".join(f"küme {k}→{c}" for k, c in sorted(ar.baseline.items()))
                run = self.llm.run_agent(agent="ask_assignment", system=PROMPT, tools=self._tools(ar, "respond"), finish_tool="respond",
                                         history=hist, effort="medium",
                                         user=f"Gün {day}. Şu anki atama: {cur}.\nŞube müdürünün sorusu: {question}")
                fi = run.final_input or {}
                new = ar.validate(fi["assignment"]) if fi.get("assignment") else None
                return self._answer(ar, fi.get("response") or run.final_text or "", new, run.steps, degraded=False)
            except Exception as e:
                res = self._ask_mock(ar, question)
                res.update(degraded=True, error=str(e))
                return res
        return self._ask_mock(ar, question)

    def _answer(self, ar: AssignmentTools, response: str, new: dict[int, str] | None, steps: list[dict], degraded: bool) -> dict:
        out = {"response": response, "assignment": None, "total": None, "diff": None, "mode": self.llm.mode, "degraded": degraded, "steps": steps}
        if new and new != ar.baseline:
            t, b = ar.totals(new), ar.totals(ar.baseline)
            out.update(assignment=ar.rows(new), total=t,
                       diff={"expected_fails": round(t["expected_fails"] - b["expected_fails"], 1),
                             "unfamiliar_stop": t["unfamiliar_stop"] - b["unfamiliar_stop"],
                             "memory_unfamiliar": t["memory_unfamiliar"] - b["memory_unfamiliar"],
                             "changed_clusters": sorted(k for k in new if ar.baseline.get(k) != new[k])})
        return out

    def _ask_mock(self, ar: AssignmentTools, question: str) -> dict:
        q = tr_lower(question)
        names = ar.resolve_courier(question)
        steps: list[dict] = []
        if not names:
            oz = ar.day_summary()
            return self._answer(ar, f"Bugün {oz['cluster_count']} küme ve {len(oz['available_couriers'])} müsait kurye var. "
                                    "Bir kuryenin adını vererek sorabilirsiniz; örneğin \"Onur gelmezse ne olur?\" ya da "
                                    "\"Onur yerine yedek kurye gönderirsem?\".", None, steps, False)
        a = names[0]
        name_a = ar.run.courier_name(a)
        k_a = next((k for k, c in ar.baseline.items() if c == a), None)
        if a not in ar.cid:
            return self._answer(ar, f"{name_a} bugün müsait değil; atamada yer almıyor.", None, steps, False)
        inp: dict = {"exclude": [a], "pin": []}
        if len(names) >= 2 and ("yerine" in q or "gönder" in q or "give" in q) and k_a is not None:
            b = names[1]
            inp = {"exclude": [a], "pin": [{"cluster_id": k_a, "courier_id": b}]}
        elif "fallback" in q and k_a is not None:
            idle = [i["id"] for i in ar.idle(ar.baseline) if ar.run.courier_kind(i["id"]) in ("reserve", "senior", "new")]
            if idle:
                j = ar.ki(k_a)
                best = min(idle, key=lambda c: ar.M["cost"][ar.ci(c), j])
                inp = {"exclude": [a], "pin": [{"cluster_id": k_a, "courier_id": best}]}
        r = ar.solve_assignment(inp)
        steps.append({"tool": "solve_assignment", "input": inp, "summary": f"beklenen başarısız {r['total']['expected_fails']}"})
        new = {x["cluster_id"]: x["courier_id"] for x in r["assignment"]}
        d = r["diff"]
        txt = (f"{name_a} atamadan çıkarılınca yeniden çözdüm. Beklenen başarısız teslim "
               f"{num(r['previous_total']['expected_fails'])} → {num(r['total']['expected_fails'])} ({num(d['expected_fails'], sign=True)}); "
               f"{len(r['changed_clusters'])} kümede kurye değişiyor.")
        if k_a is not None:
            row = next(x for x in r["rows"] if x["cluster"] == k_a)
            txt += (f" Küme {k_a}{dative(k_a)} {row['courier_name']} ({KIND_TR.get(row['courier_type'], '')}) gidiyor: "
                    f"{row['unfamiliar_stop']} yabancı durağın {row['memory_unfamiliar']} tanesinde hafıza notu var.")
        txt += " Onaylarsanız atamayı güncelliyorum."
        return self._answer(ar, txt, new, steps, False)

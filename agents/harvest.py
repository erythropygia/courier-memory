"""Hasat Ajanı: kuryenin bildiğini sistematik toplar (Hedef 1/2).

İki kaynak:
1. **Proaktif hasat (boşluk tespiti):** bugünkü planda bölgeye yabancı kuryenin gideceği, hafızası boş ve sık teslim alan
   adresler bulunur; adresi en son (tanıdık olarak) teslim eden kuryeye hedefli soru gider (kurye başına günde ≤ 3).
2. **Teslim olaylarından öğrenme:** son günlerde aynı adreste tekrarlayan bilgiyle önlenebilir başarısızlık taranır; ajan
   nedeni gün/saat örüntüsünden hipotez olarak çıkarır (Cumartesi → cumartesi kapalı, öğle penceresi → öğle arası, "giriş
   yapılamadı" → arka giriş …) ve adresi son deneyen kuryeye teyit sorusu yazar. Hipotez teyitsiz hafızaya yazılmaz.
3. **Saat örüntüsü teyidi:** teslim kayıtlarında bir saatte kimse bulunmuyor ama başka saatte kayıt yok (ya da güven
   düşük): "Bu adreste öğlen kimse yok gibi, doğru mu? Hangi saatte bulunuyorlar?" Cevap hafızaya değil teslim zamanı kaynağına
   yazılır (evet/hayır + "X'ten sonra" saati); teyitli bulgu rotaya girer, reddedilen girmez.

Cevaplar Hafıza Ajanı'ndan geçer (adres belli, `source="harvest"`): kişisel veri ayıklanır, tür ve (varsa) pencere çıkarılır.
Kararı LLM verir (hangi boşluk, kime, hangi soru, hangi hipotez); seçimi ve sayıları araçlar üretir. Mock'ta kurallı yedek
aynı araçları aynı sırayla çağırır ve Orkestratör ile aynı iz biçimini (`agents/trace.py`) yazar.

Demo için `SeniorSimulator` kıdemli kuryenin cevabını simülasyonun gizli gerçeğinden üretir (simüle edilen insan; açıkça
`simulate: true` etiketli). Gerçekte cevap kuryenin uygulamasından sesle/yazıyla gelir.
"""
from __future__ import annotations

import itertools
import threading
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from .trace import Trace
from .llm import LLM, AgentError, Tool, nullable, obj
from .memorybook import MemoryBook
from cm_sim.delivery_time import SLOT_NAMES, LEVEL_ORDER, proposal_text

from .guardrails import redact
from .rundata import KIND_TR, QUIRK_KINDS, RunData
from .delivery_time import parse_confirmation, time_source
from .tr import REASON_TR, hhmm

PROMPT = (Path(__file__).parent / "prompts" / "harvest.md").read_text(encoding="utf-8")
FINISH = "harvest_plan"
PER_COURIER = 3
DAILY_MAX = 30
LUNCH = (720, 810)
HYPOTHESIS_TYPE = {"entry_failed": "back_entry", "recipient_unreachable": "bell", "address_not_found": "position_wrong"}
QUESTION_TEMPLATE = {
    "gap": "{assigned} bugün {label} adresine gidecek, bölgeyi bilmiyor. Bu adreste giriş, saat ya da teslimle ilgili bilmesi gereken bir şey var mı?",
    "hypothesis": "{label} adresinde son günlerde {evidence}. {question_type} Doğru mu, ne önerirsin?",
    "time": "{label}: teslim kayıtlarına göre {bad} arası gidildiğinde kimse bulunmuyor ({evidence}). Doğru mu, hangi saatte bulunuyorlar?",
}
TIME_ANSWER = {
    "worker": "Evet, gündüz çalışıyorlar; akşam 5'ten sonra evdeler.",
    "shop": "Evet, öğlen dükkânı kapatıp çıkıyor; 2'den sonra uğra.",
    "office": "Evet, mesai saatinde açıklar ama akşam geç saatte kimse kalmıyor; gündüz uğra.",
    "home": "Hayır, genelde evde biri oluyor.",
    "reception": "Hayır, resepsiyon hep açık.",
}
TIME_QUESTION_MAX = 5
HYPOTHESIS_QUESTION = {
    "saturday_closed": "Cumartesileri kapalı olabilir mi?", "lunch_break": "Öğle arasında kapalı olabilir mi?",
    "temporary_closed": "Geçici olarak kapalı olabilir mi (tadilat vb.)?", "back_entry": "Giriş başka bir kapıdan mı?",
    "bell": "Zil çalışmıyor olabilir mi?", "position_wrong": "Haritadaki konum yanlış olabilir mi?",
}
ANSWER_TEMPLATE = {
    "lunch_break": "Orası öğlen 12 ile 1.5 arası kapalı oluyor, öğleden önce uğra.",
    "saturday_closed": "Cumartesi kapalı oluyorlar, o gün boşuna gitme.",
    "back_entry": "Ön kapı kullanılmıyor, arka sokaktan gir.",
    "safety": "Site güvenliği kimlik istiyor, kayıt birkaç dakika sürüyor.",
    "bell": "Zil bozuk, alıcıyı telefonla ara.",
    "position_wrong": "Haritada yanlış yerde gösteriyor, bina bir sonraki sokakta.",
    "reception": "Gönderileri resepsiyona bırakıyoruz.",
    "temporary_closed": "Tadilat var, geçici olarak kapalılar.",
    "roadwork": "Sokakta yol çalışması var, yakına park edip yürü.",
}


@lru_cache(maxsize=4)
def _history(run: RunData, day: int) -> dict[int, list[tuple]]:
    """Adres → [(gün, kurye, yabancı, neden, varış, başarısız)] (kol D, o günden önceki günler; gözlemlenebilir teslim kaydı)."""
    out: dict[int, list[tuple]] = defaultdict(list)
    for d in run.eval_days:
        if d >= day:
            break
        snap = run.snapshot("D", d)
        F = {k: i for i, k in enumerate(snap["stop_fields"])}
        for r in snap["routes"]:
            for s in r["stops"]:
                out[int(s[F["address"]])].append((d, r["courier"], int(s[F["unfamiliar"]]), s[F["reason"]], int(s[F["eta"]]),
                                                  int(s[F["fail"]])))
    return out


class HarvestTools:
    def __init__(self, run: RunData, book: MemoryBook, day: int, plan: dict | None = None):
        self.run, self.book, self.day = run, book, day
        book.ensure(day)
        snap = run.snapshot("D", day)
        self.F = {k: i for i, k in enumerate(snap["stop_fields"])}
        self.routes = {r["route"]: r for r in snap["routes"]}
        if plan:
            self.mapping = {int(x["cluster"]): x["courier"] for x in plan["assignment"]}
            self.plan_source = "approved_plan"
        else:
            self.mapping = {r["route"]: r["courier"] for r in snap["routes"]}
            self.plan_source = "simulation_plan"
        self.today = set(self.mapping.values())
        self.hist = _history(run, day)
        self.time = time_source(run)
        self.questions: list[dict] = []
        self._n = itertools.count(1)
        kinds = run.addr_kind
        tot, withm = defaultdict(int), defaultdict(int)
        for k in kinds:
            tot[k] += 1
        for a in {e["address"] for e in book.entries if e.get("status", "active") == "active"}:
            withm[kinds[a]] += 1
        self.density = {k: (withm[k] + 1) / (tot[k] + 10) for k in tot}

    def _local(self, c: str) -> bool:
        return self.run.courier_kind(c) != "borrowed"

    def _quota_left(self, c: str) -> int:
        return PER_COURIER - sum(1 for q in self.questions if q["courier"] == c)

    # ---------------------------------------------------------------- araçlar
    def memory_gaps(self, inp: dict | None = None) -> dict:
        n_max = int((inp or {}).get("max_count") or DAILY_MAX)
        F = self.F
        cands = []
        for k, c in self.mapping.items():
            r = self.routes.get(k)
            if r is None:
                continue
            for s in r["stops"]:
                a = int(s[F["address"]])
                if not s[F["unfamiliar"]] or self.book.for_address(a, self.day):
                    continue
                h = self.hist.get(a, [])
                knowers = [x for x in reversed(h) if not x[2] and x[1] != c and x[1] in self.today and self._local(x[1])]
                if not knowers:
                    continue
                score = (1 + len({x[0] for x in h})) * self.density[self.run.addr_kind[a]]
                cands.append({"address": a, "label": self.run.addr_label[a], "address_type": self.run.addr_kind[a],
                              "assigned": c, "assigned_name": self.run.courier_name(c), "assigned_type": KIND_TR.get(self.run.courier_kind(c), "?"),
                              "ask_courier": knowers[0][1], "ask_courier_name": self.run.courier_name(knowers[0][1]),
                              "last_delivery_day": knowers[0][0], "history_stop_day": len({x[0] for x in h}), "score": round(score, 3)})
        cands.sort(key=lambda x: (-x["score"], x["address"]))
        unf = sum(1 for k, c in self.mapping.items() for s in self.routes.get(k, {}).get("stops", []) if s[F["unfamiliar"]])
        return {"day": self.day, "plan_source": self.plan_source, "unfamiliar_stop": unf, "gap": len(cands),
                "candidates": cands[:n_max], "per_courier_quota": PER_COURIER, "daily_max": DAILY_MAX}

    def recurring_failure(self, inp: dict | None = None) -> dict:
        n_days = int((inp or {}).get("day_count") or 10)
        lo_day = self.day - n_days
        out = []
        for a, h in self.hist.items():
            ev = [x for x in h if x[0] >= lo_day and x[5] and x[3] not in (None, "recipient_absent", "other", "wrong_deferral")]
            if not ev:
                continue
            reasons = [x[3] for x in ev]
            if "closed" in reasons:
                container = [x for x in ev if x[3] == "closed"]
                if all(x[0] % 6 == 5 for x in container):
                    kind = "saturday_closed"
                elif all(LUNCH[0] <= x[4] < LUNCH[1] for x in container):
                    kind = "lunch_break"
                else:
                    kind = "temporary_closed"
                ev_k = container
            else:
                top = max(set(reasons), key=reasons.count)
                ev_k = [x for x in ev if x[3] == top]
                if len(ev_k) < 2:
                    continue
                kind = HYPOTHESIS_TYPE.get(top)
                if kind is None:
                    continue
            if any(e["kind"] == kind for e in self.book.for_address(a, self.day)):
                continue
            last = ev_k[-1]
            ask = last[1] if last[1] in self.today else next((c for k, c in self.mapping.items()
                                                              if any(int(s[self.F["address"]]) == a for s in self.routes.get(k, {}).get("stops", []))), None)
            if ask is None:
                continue
            evidence = ", ".join(f"{self.run.weekday_name(x[0])} {hhmm(x[4])} {REASON_TR.get(x[3], x[3].replace('_', ' '))}" for x in ev_k[-3:])
            out.append({"address": a, "label": self.run.addr_label[a], "hypothesis_type": kind, "evidence": evidence, "event": len(ev_k),
                        "ask_courier": ask, "ask_courier_name": self.run.courier_name(ask), "last_event_day": last[0]})
        out.sort(key=lambda x: (-x["event"], -x["last_event_day"], x["address"]))
        return {"day": self.day, "swept_day": n_days, "hypotheses": out[:10], "total": len(out)}

    def time_confirmations(self, inp: dict | None = None) -> dict:
        """Bugünkü planın duraklarında teyit bekleyen saat örüntüleri: kötü saat kayıtlı ama başka saatte kayıt yok ya da güven
        düşük. Sorulacak kurye: adrese en son giden ve bugün çalışan kurye, yoksa bugün o durağa gidecek kurye."""
        n_max = int((inp or {}).get("max_count") or 10)
        if not self.time.enabled:
            return {"day": self.day, "candidates": [], "total": 0}
        F = self.F
        of = {}
        for k, c in self.mapping.items():
            r = self.routes.get(k)
            if r is None:
                continue
            addrs = [int(a) for a in (r.get("plan") or {}).get("plain_order", [])] or [int(st[F["address"]]) for st in r["stops"]]
            for a in addrs:
                of[a] = c
        out = []
        for a, b in self.time.data.findings(self.day, list(of)).items():
            weak = b["type"] == "confirmation" or (b["type"] == "window" and LEVEL_ORDER[b["level"]] < LEVEL_ORDER[self.time._selection(self.day)["min_confidence"]])
            if not weak or self.time._confirmation(a, self.day) is not None:
                continue
            h = self.hist.get(a, [])
            last = next((x[1] for x in reversed(h) if x[1] in self.today), None)
            ask = last or of[a]
            k = b["bad"]
            out.append({"address": a, "label": self.run.addr_label[a], "address_type": self.run.addr_kind[a], "type": b["type"],
                        "bad_slot": SLOT_NAMES[k], "evidence": proposal_text(b), "estimate_bad": b["estimate"][k],
                        "ask_courier": ask, "ask_courier_name": self.run.courier_name(ask), "today_outgoing": of[a]})
        out.sort(key=lambda x: (-x["estimate_bad"], x["address"]))
        return {"day": self.day, "candidates": out[:n_max], "total": len(out)}

    def save_question(self, inp: dict) -> dict:
        c, a = inp["courier_id"], int(inp["address_id"])
        if c not in self.today:
            raise ValueError(f"{c} bugün planda değil; soru bugün çalışan kuryeye gider")
        if not (0 <= a < len(self.run.addr_kind)):
            raise ValueError(f"Geçersiz adres: {a}")
        if self._quota_left(c) <= 0:
            raise ValueError(f"{self.run.courier_name(c)} için günlük soru kotası ({PER_COURIER}) doldu")
        if len(self.questions) >= DAILY_MAX:
            raise ValueError(f"Günlük soru sınırı ({DAILY_MAX}) doldu")
        if any(q["address"] == a for q in self.questions):
            raise ValueError("Bu adres için bugün zaten soru var")
        hk = inp.get("hypothesis_type")
        if hk is not None and hk not in QUIRK_KINDS:
            raise ValueError(f"Bilinmeyen hipotez türü: {hk}")
        q = {"id": f"H{self.day}-{next(self._n):02d}", "day": self.day, "courier": c, "courier_name": self.run.courier_name(c),
             "address": a, "label": self.run.addr_label[a], "question": str(inp["question"])[:300], "reason": inp.get("reason") or "gap",
             "hypothesis_type": hk, "status": "waiting"}
        self.questions.append(q)
        return {"question_id": q["id"], "remaining_quota": self._quota_left(c), "total_question": len(self.questions)}

    def save_questions(self, inp: dict) -> dict:
        """Toplu kayıt (tek araç çağrısı; canlı ajanın geçmişi tekrar tekrar göndermemesi için). Kural dışı soru reddedilir."""
        ok, bad = [], []
        for x in inp.get("questions") or []:
            try:
                ok.append(self.save_question(x)["question_id"])
            except (ValueError, KeyError, TypeError) as e:
                bad.append({"address_id": x.get("address_id"), "courier_id": x.get("courier_id"), "reason": str(e)})
        return {"saved": ok, "rejected": bad, "total_question": len(self.questions)}


SUMMARY = {
    "memory_gaps": lambda i, r: f"{r['unfamiliar_stop']} yabancı durak, {r['gap']} hafıza boşluğu (soracak kıdemlisi olan)",
    "recurring_failure": lambda i, r: f"{r['total']} adreste tekrarlayan başarısızlık hipotezi",
    "time_confirmations": lambda i, r: f"{r['total']} adreste teyit bekleyen saat örüntüsü",
    "save_questions": lambda i, r: f"{len(r['saved'])} soru kaydedildi, {len(r['rejected'])} reddedildi (toplam {r['total_question']})",
}


class HarvestAgent:
    def __init__(self, run: RunData, book: MemoryBook, llm: LLM, plans: dict | None = None):
        self.run, self.book, self.llm = run, book, llm
        self.plans = plans if plans is not None else {}

    def _tools(self, ar: HarvestTools, trace: Trace) -> tuple[list[Tool], dict]:
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
            ("memory_gaps", "Bugünkü planda bölgeye yabancı kuryenin gideceği, hafızası boş adresler; her biri için adresi en son "
                                  "tanıdık olarak teslim eden ve bugün çalışan kurye (sorulacak). Puan: geçmiş durak günü × adres "
                                  "türündeki hafıza yoğunluğu.", obj({"max_count": {"type": "integer"}}), ar.memory_gaps),
            ("recurring_failure", "Son günlerde aynı adreste tekrarlayan bilgiyle önlenebilir başarısızlıklar; gün/saat "
                                         "örüntüsünden neden hipotezi ve sorulacak kurye.", obj({"day_count": {"type": "integer"}}),
             ar.recurring_failure),
            ("time_confirmations", "Teslim kayıtlarında teyit bekleyen saat örüntüleri (bir saatte kimse yok ama başka saatte kayıt yok "
                                "ya da güven düşük) ve sorulacak kurye. Cevap teslim zamanı kaynağına yazılır.",
             obj({"max_count": {"type": "integer"}}), ar.time_confirmations),
            ("save_questions", "Kuryelere hedefli soruları toplu kaydeder (kurye başına günde en çok 3, şubede 30; kural dışı soru "
                                "reddedilir ve nedeni döner). neden: bosluk | hipotez | zaman.",
             obj({"questions": {"type": "array", "items": obj({
                 "courier_id": {"type": "string"}, "address_id": {"type": "integer"}, "question": {"type": "string"},
                 "reason": {"type": "string", "enum": ["gap", "hypothesis", "time"]},
                 "hypothesis_type": nullable({"type": "string", "enum": list(QUIRK_KINDS)})})}}), ar.save_questions),
        ]
        fns = {n: wrap(n, fn) for n, _, _, fn in specs}
        tools = [Tool(n, d, s, fns[n], lambda i, r, n=n: SUMMARY[n](i, r)) for n, d, s, _ in specs]
        tools.append(Tool(FINISH, "Günün hasat planını bitirir (son adım). Sorular save_questions ile kaydedilmiş olmalı.",
                          obj({"summary": {"type": "string"}})))
        return tools, fns

    def plan(self, day: int, trace: Trace | None = None) -> dict:
        trace = Trace() if trace is None else trace
        ar = HarvestTools(self.run, self.book, day, self.plans.get(day))
        trace.source = "llm" if self.llm.uses_llm else "rule"
        trace.emit("start", day=day, mod=self.llm.mode, task="harvest")
        tools, fns = self._tools(ar, trace)
        degraded, error, summary = False, None, ""
        if self.llm.uses_llm:
            try:
                run = self.llm.run_agent(agent="harvest", system=PROMPT, tools=tools, finish_tool=FINISH, effort="medium", max_turns=40,
                                         on_text=lambda t: trace.emit("decision", text=t),
                                         user=f"Gün {day} ({self.run.weekday_name(day)}): planı kesinleşen günün hafıza boşluklarını ve "
                                              f"tekrarlayan başarısızlıklarını tara, kuryelere hedefli soruları kaydet.")
                if not run.final_input:
                    raise AgentError("Ajan hasat planını bitirmedi")
                summary = run.final_input.get("summary", "")
                trace.emit("tool", tool=FINISH, input=run.final_input)
            except Exception as e:
                degraded, error = True, str(e)
                trace.source = "rule"
                trace.emit("fallback", text=f"Canlı ajan tamamlanamadı ({e}); kurallı yedek aynı araçlarla devam ediyor.")
                ar.questions.clear()
                summary = self._rule(ar, trace, fns)
        else:
            summary = self._rule(ar, trace, fns)
        trace.emit("done", status="done", question=len(ar.questions))
        out = {"day": day, "mode": self.llm.mode, "degraded": degraded, "plan_source": ar.plan_source, "summary": summary,
               "questions": ar.questions, "trace": trace.events}
        if error:
            out["error"] = error
        return out

    def _rule(self, ar: HarvestTools, trace: Trace, T: dict) -> str:
        trace.emit("decision", text="Bugün bölgeye yabancı kuryelerin gideceği ve hafızası boş adresleri arıyorum.")
        b = T["memory_gaps"]({"max_count": DAILY_MAX})
        if b["candidates"]:
            trace.emit("decision", text=f"{b['gap']} boşluk var; en sık teslim alan adresleri, oraya en son giden kıdemliye soruyorum "
                                   f"(kurye başına en çok {PER_COURIER}).")
        quota: dict[str, int] = {}
        selection = []
        for x in b["candidates"]:
            if len(selection) >= DAILY_MAX - 5:
                break
            if quota.get(x["ask_courier"], 0) >= PER_COURIER:
                continue
            quota[x["ask_courier"]] = quota.get(x["ask_courier"], 0) + 1
            selection.append({"courier_id": x["ask_courier"], "address_id": x["address"], "reason": "gap", "hypothesis_type": None,
                          "question": QUESTION_TEMPLATE["gap"].format(assigned=x["assigned_name"], label=x["label"])})
        n_b = len(T["save_questions"]({"questions": selection})["saved"]) if selection else 0
        trace.emit("decision", text="Son günlerin teslim kayıtlarında aynı adreste tekrarlayan başarısızlık arıyorum.")
        h = T["recurring_failure"]({"day_count": 10})
        selection = []
        asked = {q["address"] for q in ar.questions}
        for x in h["hypotheses"][:5]:
            pending = sum(1 for y in selection if y["courier_id"] == x["ask_courier"])
            if len(ar.questions) + len(selection) >= DAILY_MAX or ar._quota_left(x["ask_courier"]) - pending <= 0 or x["address"] in asked:
                continue
            asked.add(x["address"])
            selection.append({"courier_id": x["ask_courier"], "address_id": x["address"], "reason": "hypothesis", "hypothesis_type": x["hypothesis_type"],
                          "question": QUESTION_TEMPLATE["hypothesis"].format(label=x["label"], evidence=x["evidence"],
                                                                question_type=HYPOTHESIS_QUESTION.get(x["hypothesis_type"], ""))})
        n_h = len(T["save_questions"]({"questions": selection})["saved"]) if selection else 0
        n_z = 0
        if ar.time.enabled:
            trace.emit("decision", text="Teslim kayıtlarında saat örüntüsü teyit bekleyen adresleri (öğlen kimse yok gibi) kuryelere soruyorum.")
            zt = T["time_confirmations"]({"max_count": 10})
            selection = []
            asked = {q["address"] for q in ar.questions}
            for x in zt["candidates"]:
                pending = sum(1 for y in selection if y["courier_id"] == x["ask_courier"])
                if (len(selection) >= TIME_QUESTION_MAX or len(ar.questions) + len(selection) >= DAILY_MAX
                        or ar._quota_left(x["ask_courier"]) - pending <= 0 or x["address"] in asked):
                    continue
                asked.add(x["address"])
                selection.append({"courier_id": x["ask_courier"], "address_id": x["address"], "reason": "time", "hypothesis_type": None,
                              "question": QUESTION_TEMPLATE["time"].format(label=x["label"], bad=x["bad_slot"], evidence=x["evidence"])})
            n_z = len(T["save_questions"]({"questions": selection})["saved"]) if selection else 0
        summary = (f"{n_b} boşluk sorusu, {n_h} teyit sorusu, {n_z} saat teyidi sorusu kaydedildi. Cevaplar Hafıza Ajanı'ndan geçip "
                f"hafızaya yazılacak (saat teyidi teslim zamanı kaynağına); hipotezler teyit gelmeden yazılmaz.")
        trace.emit("decision", text=summary)
        trace.emit("tool", tool=FINISH, input={"summary": summary})
        return summary


class SeniorSimulator:
    """Demo: sorulan kuryenin cevabını simülasyonun gizli gerçeğinden üretir (simüle edilen insan, `simulate: true`)."""

    def __init__(self, run: RunData):
        self.run = run
        self._q: dict[int, list[dict]] | None = None

    def answer(self, address: int, day: int, reason: str | None = None) -> str:
        if reason == "time":
            pr = self.run.file("truth.json").get("presence")
            if not pr:
                return "Bilmiyorum."
            return TIME_ANSWER.get(pr["profiles"][pr["profile"][int(address)]], "Bilmiyorum.")
        if self._q is None:
            self._q = defaultdict(list)
            for q in self.run.file("truth.json")["quirks"]:
                self._q[int(q["address"])].append(q)
        act = [q for q in self._q.get(int(address), []) if q["active_from"] <= day and (q["active_to"] is None or day <= q["active_to"])]
        if not act:
            return "Bildiğim bir sorun yok, normal teslim ediyorum."
        return " ".join(ANSWER_TEMPLATE[q["kind"]] for q in act[:2])


class HarvestStore:
    """Günün hasat soruları (bellek içi, demo). Cevap → Hafıza Ajanı → hafıza."""

    def __init__(self, agent: HarvestAgent, memory):
        self.agent, self.memory = agent, memory
        self.days: dict[int, dict] = {}
        self.sim = SeniorSimulator(agent.run)
        self._lock = threading.Lock()

    def plan(self, day: int) -> dict:
        res = self.agent.plan(day)
        with self._lock:
            self.days[day] = res
        return res

    def items(self, day: int) -> dict:
        r = self.days.get(day)
        if r is None:
            raise KeyError(day)
        return {k: r[k] for k in ("day", "mode", "degraded", "plan_source", "summary", "questions")}

    def _question(self, question_id: str) -> dict:
        for r in self.days.values():
            for q in r["questions"]:
                if q["id"] == question_id:
                    return q
        raise KeyError(question_id)

    def reply(self, question_id: str, text: str, simulate: bool = False) -> dict:
        q = self._question(question_id)
        if q["status"] != "waiting":
            raise ValueError(f"Soru zaten cevaplandı ({q['status']})")
        if q.get("reason") == "time":
            # Saat teyidi: Hafıza Ajanı'na değil teslim zamanı kaynağına (evet/hayır + "X'ten sonra" saati); metin ayıklanır.
            decision, hour = parse_confirmation(text)
            zk = time_source(self.agent.run)
            t = zk.write_confirmation(q["address"], q["day"], decision, hour, text)
            status = "confirmation" if decision else "ret" if decision is False else "uncertain"
            summary = ({"confirmation": "Kurye örüntüyü doğruladı; bulgu rota hesabına girer (kural: rota uzamaz)" + (f" ({hhmm(hour)} sonrası önerilir)." if hour else "."),
                     "ret": "Kurye örüntüyü doğrulamadı; bulgu rotaya girmeyecek.",
                     "uncertain": "Cevaptan evet/hayır çıkarılamadı; bulgu değişmedi."})[status]
            q.update(status="answered", answer=redact(text), simulate=simulate,
                     result={"status": status, "type": "time", "hint": None, "record": None, "summary": summary})
            return {"question": q, "memory": None, "time": {**t, "status": status, "hour_text": hhmm(hour) if hour else None, "summary": summary}}
        res = self.memory.process(q["day"], q["courier"], text, address_id=q["address"], source="harvest")
        q.update(status="answered", answer=text, simulate=simulate, result={k: res.get(k) for k in ("status", "type", "hint", "record", "summary")})
        return {"question": q, "memory": res}

    def simulate_answer(self, question_id: str) -> dict:
        q = self._question(question_id)
        return self.reply(question_id, self.sim.answer(q["address"], q["day"], q.get("reason")), simulate=True)

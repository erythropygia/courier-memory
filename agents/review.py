"""Değerlendirme Ajanı (öz-iyileştirme): her sabah son günleri kurye bazında gözden geçirir, sistemin kararlarını düzeltir.

Kuryeyi puanlamaz; sistemin kararlarını değerlendirir: atama, hafıza kayıtları, süre tahmini. Soru: "yapılan değişiklikler iyi
yönde mi gidiyor?" Son WINDOW_DAYS gün ↔ önceki WINDOW_DAYS gün.

Araçlar (deterministik; karar LLM'de, mock'ta kurallı yedek aynı araçları aynı sırayla çağırır):
  trend               ilk denemede başarı, yabancı/ipuçlu durakta başarısız, süre tahmini hatası: son ↔ önceki pencere
  hint_outcomes       ipucu gösterildiği halde bilgiyle ilgili nedenle başarısız olan duraklar → şüpheli hafıza kayıtları
  recurring_problems  hafızası olmayan adreste tekrarlayan bilgiyle ilgili başarısızlık → kıdemliye soru adayı
  duration_estimate   sistem düzeyi: (gerçekleşen − planlanan) ~ genel sapma + yabancı durak başına ek dk; son günde sınama
  assignment_check    aynı kuryenin rotası art arda günlerde büyük ölçüde yabancı bloklarda mı (atama ağırlığı önerisi)
  apply               eylemler; korkuluklar: tek kaynaklı + ≥2 çelişki → düşür, aksi halde teyide al; parametre sınırlı;
                      atama değişikliği yalnız öneri (müdür onayı); günde en çok AUTO_MAX otomatik eylem
Bitiş: present_report {summary, going_well[], going_badly[]}. Her eylem ajan akışına (agents/feed.py) yazılır ve geri alınabilir.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

from .feed import AgentFeed
from .trace import Trace
from .llm import LLM, AgentError, Tool, obj
from .memorybook import MemoryBook
from .rundata import KIND_TR, RunData

PROMPT = (Path(__file__).parent / "prompts" / "review.md").read_text(encoding="utf-8")
WINDOW_DAYS = 5
AUTO_MAX = 12
ASSIGNMENT_THRESHOLD = 0.2           # rotanın bu kadarı yabancı blokta (sim kol D rotalarının p90 ≈ 0,18)
INFO_REASONS = {"address_not_found", "entry_failed", "closed", "recipient_unreachable"}
CONTRADICTS = {  # tür → ipucuyla çelişen başarısızlık nedenleri
    "bell": {"recipient_unreachable"}, "saturday_closed": {"closed"}, "temporary_closed": {"closed"}, "lunch_break": {"closed"},
    "reception": {"closed", "entry_failed"},
}
DEFAULT_CONTRADICTS = {"address_not_found", "entry_failed"}
PARAM_LIMITS = {"unfamiliar_stop_extra_min": (0.0, 8.0), "general_bias_min": (-120.0, 120.0)}
FINISH = "present_report"
ACTION_TYPES = ["drop_record", "flag_for_confirmation", "open_question", "parameter", "proposal"]


class ReviewTools:
    def __init__(self, run: RunData, book: MemoryBook, day: int, store: "ReviewStore"):
        self.run, self.book, self.day, self.store = run, book, day, store
        days = [d for d in run.eval_days if d < day]
        self.last, self.previous = days[-WINDOW_DAYS:], days[-2 * WINDOW_DAYS:-WINDOW_DAYS]
        self._snap = {d: run.snapshot("D", d) for d in self.last + self.previous}
        self.F = {k: i for i, k in enumerate(run.snapshot("D", day)["stop_fields"])}
        self.suspect: dict[str, dict] = {}
        self.auto = 0

    def _stops(self, days):
        F = self.F
        for d in days:
            for r in self._snap[d]["routes"]:
                hints = r.get("hints") or {}
                for s in r["stops"]:
                    yield d, r, s, str(int(s[F["address"]])) in hints

    # ------------------------------------------------------------------ araçlar
    def trend(self, _: dict | None = None) -> dict:
        F = self.F

        def measure(days):
            ok = fail = offline = ufail = hn = hfail = 0
            error = []
            for d in days:
                for r in self._snap[d]["routes"]:
                    error.append(abs(float(r["minutes"]) - float(r.get("planned_minutes", r["minutes"]))))
            for _, _, s, hint in self._stops(days):
                o, f = int(s[F["ok"]]), int(s[F["fail"]])
                ok += o; fail += f
                if s[F["unfamiliar"]]:
                    offline += o + f; ufail += f
                if hint:
                    hn += o + f; hfail += f
            return {"first_attempt": ok / max(ok + fail, 1), "unfamiliar_fail": ufail / max(offline, 1),
                    "hinted_fail": hfail / max(hn, 1), "duration_error_min": float(np.mean(error)) if error else 0.0}

        s, o = measure(self.last), measure(self.previous)
        good_dir = {"first_attempt": 1, "unfamiliar_fail": -1, "hinted_fail": -1, "duration_error_min": -1}
        out = []
        for k, v in s.items():
            d = v - o[k]
            threshold = 2.0 if k == "duration_error_min" else 0.003
            direction = "stable" if abs(d) < threshold else ("good" if d * good_dir[k] > 0 else "bad")
            out.append({"measure": k, "last": round(v, 4), "previous": round(o[k], 4), "diff": round(d, 4), "direction": direction})
        return {"last_days": self.last, "previous_days": self.previous, "measures": out}

    def hint_outcomes(self, _: dict | None = None) -> dict:
        F = self.F
        say: dict[int, dict] = defaultdict(lambda: {"attempt": 0, "fails": 0, "reasons": defaultdict(int), "days": set()})
        for d, r, s, hint in self._stops(self.last):
            if not hint:
                continue
            a = int(s[F["address"]])
            x = say[a]
            x["attempt"] += int(s[F["ok"]]) + int(s[F["fail"]])
            if s[F["fail"]] and s[F["reason"]] in INFO_REASONS:
                x["fails"] += int(s[F["fail"]])
                x["reasons"][s[F["reason"]]] += 1
                x["days"].add(d)
        records = []
        for a, x in say.items():
            for e in self.book.for_address(a, self.day):
                contra = CONTRADICTS.get(e["kind"], DEFAULT_CONTRADICTS)
                n_contra = sum(v for k, v in x["reasons"].items() if k in contra)
                if n_contra >= 1:                                # tek çelişki: teyide alınır; düşürme yalnız tek kaynak + ≥2 çelişki
                    row = {"record_id": e["id"], "address": a, "label": self.run.addr_label[a], "type": e["kind"], "text": e["text"],
                           "source_count": int(e.get("sources", 1)), "hinted_attempts": x["attempt"], "contradictions": n_contra,
                           "reasons": dict(x["reasons"]), "days": sorted(x["days"])}
                    self.suspect[e["id"]] = row
                    records.append(row)
        records.sort(key=lambda r: (-r["contradictions"], r["source_count"]))
        return {"hinted_addresses": len(say), "suspect": records[:25], "total_suspect": len(records)}

    def recurring_problems(self, _: dict | None = None) -> dict:
        F = self.F
        say: dict[int, dict] = defaultdict(lambda: {"n": 0, "reasons": defaultdict(int), "days": set(), "courier": None})
        for d, r, s, _h in self._stops(self.last):
            if s[F["fail"]] and s[F["reason"]] in INFO_REASONS:
                a = int(s[F["address"]])
                x = say[a]
                x["n"] += 1
                x["reasons"][s[F["reason"]]] += 1
                x["days"].add(d)
                x["courier"] = r["courier_name"]
        out = [{"address": a, "label": self.run.addr_label[a], "fails": x["n"], "reasons": dict(x["reasons"]),
                "days": sorted(x["days"]), "last_courier": x["courier"]}
               for a, x in say.items() if len(x["days"]) >= 2 and not self.book.for_address(a, self.day)]
        out.sort(key=lambda r: -r["fails"])
        return {"address": out[:20], "total": len(out)}

    def duration_estimate(self, _: dict | None = None) -> dict:
        F = self.F
        rows = []
        for d in self.last:
            for r in self._snap[d]["routes"]:
                y = float(r["minutes"]) - float(r.get("planned_minutes", r["minutes"]))
                rows.append((d, sum(1 for s in r["stops"] if s[F["unfamiliar"]]), y, float(r.get("planned_minutes", r["minutes"])), float(r["minutes"])))
        if len(self.last) < 2 or len(rows) < 10:
            return {"enough_data": False}
        test = self.last[-1]
        tr = np.array([(x, y) for d, x, y, _, _ in rows if d != test])
        A = np.column_stack([np.ones(len(tr)), tr[:, 0]])
        (a, b), *_ = np.linalg.lstsq(A, tr[:, 1], rcond=None)
        a = float(np.clip(a, *PARAM_LIMITS["general_bias_min"]))
        b = float(np.clip(b, *PARAM_LIMITS["unfamiliar_stop_extra_min"]))
        p = self.store.params
        te = [(x, plan, act) for d, x, _, plan, act in rows if d == test]
        before = float(np.mean([abs(act - (plan + p["general_bias_min"] + p["unfamiliar_stop_extra_min"] * x)) for x, plan, act in te]))
        after = float(np.mean([abs(act - (plan + a + b * x)) for x, plan, act in te]))
        return {"enough_data": True, "current": dict(p), "proposed": {"general_bias_min": round(a, 2), "unfamiliar_stop_extra_min": round(b, 2)},
                "test_day": test, "error_before_min": round(before, 1), "error_after_min": round(after, 1), "route": len(rows)}

    def assignment_check(self, _: dict | None = None) -> dict:
        F = self.F
        courier: dict[str, list] = defaultdict(list)
        for d in self.last:
            for r in self._snap[d]["routes"]:
                st = r["stops"]
                if not st:
                    continue
                unf = [s for s in st if s[F["unfamiliar"]]]
                hint = r.get("hints") or {}
                courier[(r["courier"], r["courier_name"], r["courier_kind"])].append(
                    {"day": d, "unfamiliar_share": round(len(unf) / len(st), 3),
                     "with_memory_share": round(sum(1 for s in unf if str(int(s[F["address"]])) in hint) / max(len(unf), 1), 3)})
        out = []
        for (cid, name, kind), g in courier.items():
            high = [x for x in g if x["unfamiliar_share"] > ASSIGNMENT_THRESHOLD]
            if len(high) >= 2:
                out.append({"courier": cid, "name": name, "type": kind, "day": len(g), "high_days": len(high),
                            "mean_unfamiliar_share": round(float(np.mean([x["unfamiliar_share"] for x in g])), 3),
                            "mean_with_memory_share": round(float(np.mean([x["with_memory_share"] for x in high])), 3)})
        out.sort(key=lambda r: -r["mean_unfamiliar_share"])
        return {"courier": out[:10], "total": len(out)}

    def _position(self, a: int) -> list[float]:
        return [round(float(self.run.addr_ll[a, 0]), 5), round(float(self.run.addr_ll[a, 1]), 5)]

    def apply(self, inp: dict) -> dict:
        result = []
        for e in inp.get("actions") or []:
            result.append(self._action(e))
        return {"applied": [s for s in result if s["status"] == "applied"], "awaiting": [s for s in result if s["status"] == "awaiting_approval"],
                "rejected": [s for s in result if s["status"] == "rejected"]}

    def _action(self, e: dict) -> dict:
        kind, target, rationale = e.get("type"), e.get("target"), (e.get("rationale") or "")[:300]
        feed, day = self.store.feed, self.day
        if kind not in ACTION_TYPES:
            return {"type": kind, "target": target, "status": "rejected", "reason": "bilinmeyen eylem"}
        if kind in ("drop_record", "flag_for_confirmation", "open_question", "parameter") and self.auto >= AUTO_MAX:
            kind_o = kind
            o = feed.add(agent="review", kind="proposal", day=day, status="awaiting_approval", summary=f"(günlük otomatik sınır doldu) {kind_o}: {target}",
                        action={"type": kind_o, "target": target}, rationale=rationale)
            return {"type": kind_o, "target": target, "status": "awaiting_approval", "feed": o["n"], "reason": "günlük otomatik eylem sınırı"}
        if kind in ("drop_record", "flag_for_confirmation"):
            row = self.suspect.get(str(target))
            ent = self.book.get(str(target))
            if row is None or ent is None:
                return {"type": kind, "target": target, "status": "rejected", "reason": "kayıt şüpheli listesinde yok (önce hint_outcomes)"}
            if kind == "drop_record" and not (row["source_count"] == 1 and row["contradictions"] >= 2):
                kind = "flag_for_confirmation"                                    # korkuluk: çok kaynaklı ya da tek çelişki → yalnız teyide al
            ok = self.book.drop(ent["id"], day, rationale or "ipucuna rağmen tekrarlayan başarısızlık") if kind == "drop_record" \
                else self.book.flag_for_confirmation(ent["id"], day, rationale or "ipucuna rağmen başarısızlık")
            if not ok:
                return {"type": kind, "target": target, "status": "rejected", "reason": "kayıt aktif değil ya da zaten teyitte"}
            self.auto += 1
            summary = (f"{row['label']}: “{ent['text']}” {'düşürüldü' if kind == 'drop_record' else 'teyide alındı'} — "
                    f"son {WINDOW_DAYS} günde ipucuna rağmen {row['contradictions']} başarısız ({', '.join(row['reasons'])})")
            o = feed.add(agent="review", kind="record_dropped" if kind == "drop_record" else "flagged_for_confirmation", day=day, summary=summary,
                        record=ent["id"], address=row["address"], position=self._position(row["address"]), undoable=True, rationale=rationale)
            return {"type": kind, "target": ent["id"], "status": "applied", "feed": o["n"], "summary": summary}
        if kind == "open_question":
            a = int(target)
            self.auto += 1
            question = f"{self.run.addr_label[a]} adresinde son günlerde tekrar tekrar teslim edilemedi. Bu adres hakkında bilmemiz gereken bir şey var mı?"
            self.store.question_queue.append({"address": a, "label": self.run.addr_label[a], "question": question, "day": day})
            o = feed.add(agent="review", kind="question", day=day, summary=f"Kıdemliye soru açıldı: {question}", address=a, position=self._position(a), rationale=rationale)
            return {"type": kind, "target": a, "status": "applied", "feed": o["n"], "summary": question}
        if kind == "parameter":
            name, value = (target or {}).get("name"), (target or {}).get("value")
            if name not in PARAM_LIMITS or value is None:
                return {"type": kind, "target": target, "status": "rejected", "reason": "bilinmeyen parametre"}
            lo, hi = PARAM_LIMITS[name]
            new = float(np.clip(float(value), lo, hi))
            old = self.store.params[name]
            self.store.params[name] = new
            self.auto += 1
            o = feed.add(agent="review", kind="parameter", day=day, summary=f"Süre tahmini: {name} {old:g} → {new:g}", parameter=name, old=old,
                        new=new, undoable=True, rationale=rationale)
            return {"type": kind, "target": name, "status": "applied", "feed": o["n"], "summary": f"{name} {old:g} → {new:g}"}
        o = feed.add(agent="review", kind="proposal", day=day, status="awaiting_approval", summary=str(target)[:300], rationale=rationale)
        return {"type": kind, "target": target, "status": "awaiting_approval", "feed": o["n"]}


SUMMARY = {
    "trend": lambda i, r: ", ".join(f"{x['measure']} {x['direction']}" for x in r["measures"]),
    "hint_outcomes": lambda i, r: f"{r['hinted_addresses']} ipuçlu adres, {r['total_suspect']} şüpheli kayıt",
    "recurring_problems": lambda i, r: f"hafızasız {r['total']} adreste tekrarlayan başarısızlık",
    "duration_estimate": lambda i, r: (f"tahmin hatası {r['error_before_min']} → {r['error_after_min']} dk (gün {r['test_day']} sınaması)"
                                  if r.get("enough_data") else "yeterli veri yok"),
    "assignment_check": lambda i, r: f"{r['total']} kurye art arda yabancı ağırlıklı rotada",
    "apply": lambda i, r: f"{len(r['applied'])} uygulandı, {len(r['awaiting'])} onay bekliyor, {len(r['rejected'])} reddedildi",
}


class ReviewStore:
    def __init__(self, run: RunData, book: MemoryBook, llm: LLM, feed: AgentFeed):
        self.run, self.book, self.llm, self.feed = run, book, llm, feed
        self.params = {"unfamiliar_stop_extra_min": 0.0, "general_bias_min": 0.0}
        self.question_queue: list[dict] = []
        self.last_report: dict | None = None

    def _tools(self, ar: ReviewTools, trace: Trace) -> tuple[list[Tool], dict]:
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

        empty = obj({})
        action = obj({"type": {"type": "string", "enum": ACTION_TYPES}, "target": {"anyOf": [{"type": "string"}, {"type": "integer"},
                     obj({"name": {"type": "string"}, "value": {"type": "number"}})]}, "rationale": {"type": "string"}})
        specs = [
            ("trend", "Son günler ↔ önceki günler: ilk denemede başarı, yabancı ve ipuçlu durakta başarısız oranı, süre tahmini hatası; yön.", empty, ar.trend),
            ("hint_outcomes", "İpucu gösterildiği halde bilgiyle ilgili nedenle başarısız olan duraklar ve bağlı hafıza kayıtları (şüpheli).", empty, ar.hint_outcomes),
            ("recurring_problems", "Hafızası olmayan adreslerde art arda günlerde bilgiyle ilgili başarısızlık (kıdemliye soru adayı).", empty, ar.recurring_problems),
            ("duration_estimate", "Sistem düzeyi süre tahmini: gerçekleşen − planlanan ~ genel sapma + yabancı durak başına ek dk; son günde sınama.", empty, ar.duration_estimate),
            ("assignment_check", "Art arda günlerde rotası büyük ölçüde yabancı bloklarda olan kuryeler (atama sorusu; kurye puanı değil).", empty, ar.assignment_check),
            ("apply", "Eylemleri uygular. drop_record/flag_for_confirmation: hedef kayıt kimliği; open_question: hedef adres; parameter: hedef {name, value}; "
                       "proposal: hedef metin (müdür onayına gider). Korkuluklar araçta.", obj({"actions": {"type": "array", "items": action}}), ar.apply),
        ]
        fns = {n: wrap(n, fn) for n, _, _, fn in specs}
        tools = [Tool(n, d, s, fns[n], lambda i, r, n=n: SUMMARY[n](i, r)) for n, d, s, _ in specs]
        tools.append(Tool(FINISH, "Sabah raporunu bitirir (son adım).", obj({
            "summary": {"type": "string"}, "going_well": {"type": "array", "items": {"type": "string"}},
            "going_badly": {"type": "array", "items": {"type": "string"}}})))
        return tools, fns

    def morning_review(self, day: int, trace: Trace | None = None) -> dict:
        trace = Trace() if trace is None else trace
        self.book.ensure(day)
        ar = ReviewTools(self.run, self.book, day, self)
        trace.source = "llm" if self.llm.uses_llm else "rule"
        trace.emit("start", day=day, mod=self.llm.mode, task="review")
        tools, fns = self._tools(ar, trace)
        degraded, error, report = False, None, None
        if self.llm.uses_llm:
            try:
                run = self.llm.run_agent(agent="review", system=PROMPT, tools=tools, finish_tool=FINISH, effort="medium", max_turns=20,
                                         on_text=lambda t: trace.emit("decision", text=t),
                                         user=f"Gün {day} sabahı. Son {WINDOW_DAYS} günü önceki {WINDOW_DAYS} günle karşılaştır; sistemin kararlarını "
                                              f"değerlendir, gereken düzeltmeleri uygula, müdüre sabah raporunu sun.")
                if not run.final_input:
                    raise AgentError("Ajan raporu bitirmedi")
                report = run.final_input
                trace.emit("tool", tool=FINISH, input=report)
            except Exception as e:
                degraded, error = True, str(e)
                trace.source = "rule"
                trace.emit("fallback", text=f"Canlı ajan tamamlanamadı ({e}); kurallı yedek aynı araçlarla devam ediyor.")
                report = self._rule(ar, trace, fns)
        else:
            report = self._rule(ar, trace, fns)
        self.feed.add(agent="review", kind="report", day=day, status="info", summary=report.get("summary", ""),
                       going_well=report.get("going_well", []), going_badly=report.get("going_badly", []))
        trace.emit("done", status="done")
        out = {"day": day, "mode": self.llm.mode, "degraded": degraded, "report": report, "params": dict(self.params),
               "question_queue": self.question_queue[-20:], "trace": trace.events}
        if error:
            out["error"] = error
        self.last_report = out
        return out

    def _rule(self, ar: ReviewTools, trace: Trace, T: dict) -> dict:
        trace.emit("decision", text=f"Son {WINDOW_DAYS} günü önceki {WINDOW_DAYS} günle karşılaştırıyorum: değişiklikler iyi yönde mi?")
        eg = T["trend"]({})
        LABEL = {"first_attempt": "ilk denemede teslim", "unfamiliar_fail": "yabancı sokakta başarısızlık",
               "hinted_fail": "ipuçlu durakta başarısızlık", "duration_error_min": "süre tahmini hatası"}
        fmt = lambda x: (f"{x['previous']:.1f} → {x['last']:.1f} dk" if x["measure"] == "duration_error_min" else f"%{100 * x['previous']:.1f} → %{100 * x['last']:.1f}")
        good = [f"{LABEL[x['measure']]} {fmt(x)}" for x in eg["measures"] if x["direction"] == "good"]
        bad = [f"{LABEL[x['measure']]} {fmt(x)}" for x in eg["measures"] if x["direction"] == "bad"]
        actions = []
        trace.emit("decision", text="İpucu gösterildiği halde başarısız olan duraklara bakıyorum; hafıza yanlış bilgi veriyor olabilir.")
        ip = T["hint_outcomes"]({})
        for r in ip["suspect"][:8]:
            kind = "drop_record" if r["source_count"] == 1 and r["contradictions"] >= 2 else "flag_for_confirmation"
            actions.append({"type": kind, "target": r["record_id"], "rationale": f"ipucuna rağmen {r['contradictions']} başarısız ({', '.join(r['reasons'])})"})
        if ip["suspect"]:
            trace.emit("decision", text="Kural: tek kaynaklı ve en az iki kez çelişen kayıt düşer; diğerleri teyide alınır (kartta 'teyit edin' görünür).")
        tk = T["recurring_problems"]({})
        for r in tk["address"][:5]:
            actions.append({"type": "open_question", "target": r["address"], "rationale": f"{len(r['days'])} günde {r['fails']} başarısız, hafıza boş"})
        st = T["duration_estimate"]({})
        if st.get("enough_data") and st["error_after_min"] < st["error_before_min"] - 1:
            trace.emit("decision", text=f"Süre tahmini yeni katsayılarla sınama gününde {st['error_before_min']} → {st['error_after_min']} dk hata veriyor; güncelliyorum.")
            for name, v in st["proposed"].items():
                actions.append({"type": "parameter", "target": {"name": name, "value": v}, "rationale": f"sınama hatası {st['error_before_min']} → {st['error_after_min']} dk"})
        at = T["assignment_check"]({})
        for r in at["courier"][:3]:
            actions.append({"type": "proposal", "target": f"{r['name']} ({KIND_TR.get(r['type'], r['type'])}): son {r['day']} günün {r['high_days']} gününde rotadaki durakların "
                                                      f"ortalama %{100 * r['mean_unfamiliar_share']:.0f} kadarı kuryenin tanımadığı bloklardaydı; bunların yalnız %{100 * r['mean_with_memory_share']:.0f} "
                                                      f"kadarında hafıza bilgisi vardı. Atamada tanıdıklık ağırlığını artırmayı ya da bu kuryeyi bildiği kümede tutmayı onaylıyor musunuz?",
                             "rationale": "atama değişikliği müdür kararıdır"})
        u = T["apply"]({"actions": actions})
        if u["applied"]:
            good.append(f"{len(u['applied'])} düzeltme uygulandı")
        if u["awaiting"]:
            bad.append(f"{len(u['awaiting'])} atama önerisi panelde (zinciri beklemez)")
        summary = (f"Son {WINDOW_DAYS} gün: " + ("; ".join(good[:3]) if good else "belirgin iyileşme yok") +
                (". Dikkat: " + "; ".join(bad[:3]) if bad else "") + ".")
        trace.emit("tool", tool=FINISH, input={"summary": summary, "going_well": good, "going_badly": bad})
        return {"summary": summary, "going_well": good, "going_badly": bad}

    def decision(self, n: int, decision: str, day: int) -> dict:
        """Müdür: approve | reject (önerilerde), undo (uygulanmış otomatik eylemde)."""
        o = next((x for x in self.feed.events if x["n"] == n), None)
        if o is None:
            raise KeyError(n)
        if decision == "undo":
            if not o.get("undoable") or o["status"] != "applied":
                raise ValueError("Bu eylem geri alınamaz")
            if o.get("record"):
                self.book.undo(o["record"], day)
            if o.get("parameter"):
                self.params[o["parameter"]] = o["old"]
            self.feed.update(n, status="undone")
        elif decision in ("approve", "reject"):
            if o["status"] != "awaiting_approval":
                raise ValueError("Bu öğe onay beklemiyor")
            self.feed.update(n, status="approved" if decision == "approve" else "rejected")
        else:
            raise ValueError("decision: approve | reject | undo")
        self.feed.add(agent="manager", kind="decision", day=day, status="info", summary=f"#{n} {decision}: {o['summary'][:120]}")
        return next(x for x in self.feed.events if x["n"] == n)

"""Bölge Ajanı: küme ve şube katmanında bölge bilgisini yorumlar, kuryeye ve müdüre anlatır, hafıza boşluğuna soru açar.

İki görev (ikisi de araç kullanan ajan; canlıda karar ve metin LLM'de, mock'ta kurallı yedek aynı araçları aynı sırayla çağırır):
  kume  → kuryenin sabah küme kartı: zorluk, en zor bloklar, kümede bilinen bilgi, hafıza boşluğu (≤ 4 kısa cümle)
  sube  → müdüre bölge raporu: zor bloklar, hafıza boşlukları, öncelik; boşluk bloklarına kıdemliye soru açar (günde ≤ SORU_EN_FAZLA)
Sayılar yalnız araçlardan gelir (BolgeBilgisi: blok zorluk endeksi, kayıt türleri, boşluklar). Sorular ajan akışına ve
Değerlendirme Ajanı'nın soru kuyruğuna (panel "Ayarlar") yazılır; aynı blok aynı gün iki kez sorulmaz.
"""
from __future__ import annotations

from pathlib import Path

from .feed import AgentFeed
from .region import RegionStats, center
from .trace import Trace
from .llm import LLM, AgentError, Tool, obj
from .memorybook import MemoryBook
from .rundata import RunData

PROMPT = (Path(__file__).parent / "prompts" / "region.md").read_text(encoding="utf-8")
QUESTION_MAX = 5
SENTENCE_MAX, SENTENCE_LEN = 4, 220


class RegionTools:
    def __init__(self, b: RegionStats, agent: "RegionAgent", cluster: dict | None = None):
        self.b, self.agent, self.cluster = b, agent, cluster
        self.asked: list[dict] = []

    def branch_summary(self, _: dict | None = None) -> dict:
        hs = [h for h, x in self.b.st.items() if x["attempt"] >= 3]
        o = self.b.summary(hs)
        return {k: o[k] for k in ("block", "high_blocks", "gap", "record", "record_kinds", "branch_mean_fail")} | {"hardest": o["hardest"]}

    def hard_blocks(self, inp: dict) -> dict:
        n = max(1, min(int(inp.get("max_count") or 10), 30))
        bl = [self.b.block(h) for h, x in self.b.st.items() if x["attempt"] >= 3]
        bl = [x for x in bl if x["level"] != "low" and (not inp.get("gaps_only") or x["gap"])]
        asked = self.agent.asked_blocks.get(self.b.day, set())
        bl.sort(key=lambda x: (x["block_id"] in asked, -x["gap"], -x["index"]))
        return {"blocks": [{k: x[k] for k in ("block_id", "center", "index", "level", "main_reason", "record", "gap", "attempt", "fails")}
                            | {"asked_today": x["block_id"] in asked} for x in bl[:n]], "total": len(bl)}

    def cluster_summary(self, _: dict | None = None) -> dict:
        if self.cluster is None:
            raise ValueError("Bu görevde küme yok")
        k = self.cluster
        return {"name": k["name"], "stop": k["stop"], "unfamiliar": k["unfamiliar"], "difficulty": k["cards"]["difficulty"], "index": k["cards"]["index"],
                "high_blocks": k["cards"]["summary"]["high_blocks"], "gap": k["cards"]["summary"]["gap"],
                "record_kinds": k["cards"]["summary"]["record_kinds"], "hardest": k["cards"]["summary"]["hardest"][:3]}

    def open_question(self, inp: dict) -> dict:
        opened, rejected = [], []
        gap = {x["block_id"]: x for x in (self.b.block(h) for h, s in self.b.st.items() if s["attempt"] >= 3) if x["gap"]}
        for block_id in inp.get("block_ids") or []:
            x = gap.get(str(block_id))
            if x is None:
                rejected.append({"block_id": block_id, "reason": "hafıza boşluğu olan zor blok değil"})
                continue
            if block_id in self.agent.asked_blocks.get(self.b.day, set()):
                rejected.append({"block_id": block_id, "reason": "bugün zaten soruldu"})
                continue
            if len(self.agent.asked_blocks.get(self.b.day, set())) >= QUESTION_MAX:
                rejected.append({"block_id": block_id, "reason": f"günlük soru sınırı ({QUESTION_MAX})"})
                continue
            a = x["worst_address"]
            label = self.b.run.addr_label[a] if a is not None else f"blok {block_id}"
            question = (f"{label} çevresinde son günlerde teslim zorlaşıyor ({x['main_reason'] or 'neden belirsiz'}; "
                    f"{x['fails']}/{x['attempt']} deneme). Bu sokak/bina hakkında bilmemiz gereken bir şey var mı?")
            self.agent.asked_blocks.setdefault(self.b.day, set()).add(block_id)
            self.agent.question_queue.append({"address": a, "label": label, "question": question, "day": self.b.day, "source": "region"})
            o = self.agent.feed.add(agent="region", kind="question", day=self.b.day, summary=f"Kıdemliye soru açıldı: {question}", address=a,
                                    position=x["center"], rationale=(inp.get("rationale") or "")[:300])
            opened.append({"block_id": block_id, "address": a, "question": question, "feed": o["n"]})
            self.asked.append(opened[-1])
        return {"opened": opened, "rejected": rejected}


SUMMARY = {
    "branch_summary": lambda i, r: f"{r['block']} blok, {r['high_blocks']} zor, {r['gap']} hafıza boşluğu",
    "hard_blocks": lambda i, r: f"{len(r['blocks'])}/{r['total']} zor blok",
    "cluster_summary": lambda i, r: f"{r['name']}: {r['stop']} durak, {r['unfamiliar']} yabancı, zorluk {r['difficulty']} ({r['index']}×)",
    "open_question": lambda i, r: f"{len(r['opened'])} soru açıldı, {len(r['rejected'])} reddedildi",
}


def _sentences(xs, max_count=SENTENCE_MAX) -> list[str]:
    out = []
    for c in (xs or [])[:max_count]:
        c = " ".join(str(c).split())
        out.append(c if len(c) <= SENTENCE_LEN else c[:SENTENCE_LEN].rsplit(" ", 1)[0] + "…")
    return [c for c in out if c]


class RegionAgent:
    def __init__(self, run: RunData, book: MemoryBook, llm: LLM, feed: AgentFeed, question_queue: list):
        self.run, self.book, self.llm, self.feed, self.question_queue = run, book, llm, feed, question_queue
        self.asked_blocks: dict[int, set] = {}
        self.last_branch: dict | None = None

    def _tools(self, ar: RegionTools, trace: Trace, task: str) -> list[Tool]:
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
        specs = [("branch_summary", "Şubenin blok zorluk özeti: zor blok, hafıza boşluğu, kayıt türleri, en zor 5 blok.", empty, ar.branch_summary),
                 ("hard_blocks", "Zor bloklar (endeks ≥ 1,1), önce hafıza boşlukları. gaps_only: yalnız hafızası boş zor bloklar.",
                  obj({"max_count": {"type": "integer"}, "gaps_only": {"type": "boolean"}}), ar.hard_blocks)]
        if task == "cluster":
            specs.append(("cluster_summary", "Kuryenin bugünkü kümesi: durak, yabancı durak, zorluk, kümede bilinen bilgi türleri, boşluklar.", empty, ar.cluster_summary))
            fin = Tool("present_cluster_card", "Kuryeye sabah küme kartı (son adım): en çok 4 kısa, eyleme dönük cümle.",
                       obj({"sentences": {"type": "array", "items": {"type": "string"}}, "difficulty_note": {"type": "string"}}))
        else:
            specs.append(("open_question", "Hafıza boşluğu olan zor bloklar için oraya en son giden kıdemliye soru açar (günde en çok 5).",
                          obj({"block_ids": {"type": "array", "items": {"type": "string"}}, "rationale": {"type": "string"}}), ar.open_question))
            fin = Tool("present_branch_report", "Müdüre bölge raporu (son adım): en çok 4 cümle ve öncelikli blok kimlikleri.",
                       obj({"summary": {"type": "array", "items": {"type": "string"}}, "priority_blocks": {"type": "array", "items": {"type": "string"}}}))
        return [Tool(n, d, sc, wrap(n, fn), lambda i, r, n=n: SUMMARY[n](i, r)) for n, d, sc, fn in specs] + [fin]

    def _run(self, task: str, ar: RegionTools, trace: Trace, user: str, rule) -> tuple[dict, bool, str | None]:
        trace.source = "llm" if self.llm.uses_llm else "rule"
        trace.emit("start", day=ar.b.day, mod=self.llm.mode, task=f"region_{task}")
        tools = self._tools(ar, trace, task)
        fns = {t.name: t.fn for t in tools if t.fn}
        if self.llm.uses_llm:
            try:
                fin = tools[-1].name
                run = self.llm.run_agent(agent="region", system=PROMPT, tools=tools, finish_tool=fin, effort="low", max_turns=12,
                                         on_text=lambda t: trace.emit("decision", text=t), user=user)
                if not run.final_input:
                    raise AgentError("Ajan raporu bitirmedi")
                trace.emit("tool", tool=fin, input=run.final_input)
                return run.final_input, False, None
            except Exception as e:
                trace.source = "rule"
                trace.emit("fallback", text=f"Canlı ajan tamamlanamadı ({e}); kurallı yedek aynı araçlarla devam ediyor.")
                return rule(fns), True, str(e)
        return rule(fns), False, None

    # ------------------------------------------------------------------ küme kartı
    def cluster_card(self, day: int, stops: list[tuple[float, float]], unfamiliar: list[bool], name: str,
                   card_kinds: list[list[str]] | None = None) -> dict:
        b = RegionStats(self.run, self.book, day)
        cards = b.cluster_card(stops, unfamiliar, name, card_kinds)
        ar = RegionTools(b, self, {"name": name, "stop": len(stops), "unfamiliar": sum(unfamiliar), "cards": cards})
        trace = Trace()

        def rule(T):
            trace.emit("decision", text="Kuryenin bugünkü kümesine bakıyorum: zorluk, bilinen bilgi, boşluk.")
            T["cluster_summary"]({})
            out = {"sentences": cards["courier_card"], "difficulty_note": f"zorluk {cards['difficulty']} ({cards['index']}×)"}
            trace.emit("tool", tool="present_cluster_card", input=out)
            return out

        fi, degraded, error = self._run("cluster", ar, trace, f"Gün {day}: {name} adlı kuryenin bugünkü kümesi için sabah küme kartını hazırla.", rule)
        trace.emit("done", status="done")
        out = dict(cards, courier_card=_sentences(fi.get("sentences")) or cards["courier_card"], difficulty_note=fi.get("difficulty_note"),
                   mode=self.llm.mode, degraded=degraded, trace=trace.events)
        if error:
            out["error"] = error
        return out

    # ------------------------------------------------------------------ şube raporu
    def branch(self, day: int) -> dict:
        b = RegionStats(self.run, self.book, day)
        layer = b.branch_layer()
        ar = RegionTools(b, self)
        trace = Trace()

        def rule(T):
            trace.emit("decision", text="Şubenin bölge zorluğuna bakıyorum; hafızası boş zor bloklar önce.")
            T["branch_summary"]({})
            z = T["hard_blocks"]({"max_count": 10, "gaps_only": True})
            ids = [x["block_id"] for x in z["blocks"] if not x["asked_today"]][:3]
            if ids:
                trace.emit("decision", text=f"{len(z['blocks'])} hafıza boşluğu var; en zor {len(ids)} blok için kıdemliye soru açıyorum.")
                T["open_question"]({"block_ids": ids, "rationale": "hafızası boş zor blok"})
            out = {"summary": layer["manager_summary"], "priority_blocks": ids}
            trace.emit("tool", tool="present_branch_report", input=out)
            return out

        fi, degraded, error = self._run("branch", ar, trace, f"Gün {day} sabahı: şubenin bölge zorluğunu yorumla, hafızası boş zor bloklar için "
                                                            f"gerekirse kıdemliye soru aç, müdüre kısa rapor sun.", rule)
        summary = _sentences(fi.get("summary")) or layer["manager_summary"]
        self.feed.add(agent="region", kind="report", day=day, status="info", summary=" ".join(summary))
        trace.emit("done", status="done")
        block_id = {x["block_id"]: x for x in layer["blocks"]}
        out = dict(layer, manager_summary=summary, priority=[block_id[i] for i in fi.get("priority_blocks") or [] if i in block_id],
                   questions=ar.asked, mode=self.llm.mode, degraded=degraded, trace=trace.events)
        if error:
            out["error"] = error
        self.last_branch = out
        return out

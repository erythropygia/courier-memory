"""AgentCore zinciri (sunum): altı istek dağıtılmış AgentCore Supervisor'dan geçer; her atlama canlı akışa yayınlanır.

Supervisor → uzman (Planlama · Kurye · Hafıza · Analiz) → alan aracı → sonuç. İç alan ajanları kurallı kalır; burada
yalnız Supervisor'a gerçek istek gider (api/agentcore_client.py). Yayın api/live.py'nin `Live`'ıdır:
`LIVE.start(target=LIVE.runner(Chain), kind="agentcore")`; aynı SSE, Last-Event-ID, keep-alive ve koşu sürerken 409.

Akıştaki `cm_trace` öğeleri (runtime yazar) §5 ajan izi olayına çevrilir ve `agent`, `parent` alanlarını taşır.
`cm_trace` gelmezse (eski dağıtım) Supervisor'ın araç çağrıları model olaylarından (`contentBlockStart.toolUse`)
ve son metin gösterilir. CM_AGENTCORE_CHAIN=0 zinciri kapatır (501). Olay biçimi docs/sozlesmeler.md §4.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

from api import agentcore_client as ACC
from api.agentcore_client import AgentCoreError, scrub
from api.live import trim

ENABLE_ENV = "CM_AGENTCORE_CHAIN"
STEP_GAP = 1.2                 # sn: adımlar arası, izleyici sonucu görsün
ANSWER_LIMIT = 1500
AGENTS = ("supervisor", "planner", "courier", "memory_keeper", "analyst")
TOOL_AGENT = {"ask_planner": "planner", "ask_courier_agent": "courier", "ask_memory_keeper": "memory_keeper",
              "ask_analyst": "analyst"}
TRACE_TYPES = {"tool_call": "tool", "tool_result": "result", "delegate_start": "delegate",
               "delegate_end": "delegate_end", "denied": "denied", "error": "error"}


@dataclass(frozen=True)
class Step:
    actor: str
    prompt: str
    agent: str          # beklenen uzman
    tool: str           # beklenen alan aracı ("" = araç yok, ret beklenir)
    expect: str         # "ok" | "denied"


STEPS: tuple[Step, ...] = (
    Step("MUDUR-01", "Bugünün planını gerekçesiyle iki maddede özetle.", "planner", "plan_day", "ok"),
    Step("O02", "Sabah brifingimi ver.", "courier", "courier_briefing", "ok"),
    Step("O02", "1. durağa not bırak: sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakın. "
                "Konum 39.0120, 34.9783.", "memory_keeper", "leave_note", "ok"),
    Step("MUDUR-01", "Hafızası boş adresler için kıdemli kuryelere hangi soruları soralım?", "memory_keeper",
         "harvest_questions", "ok"),
    Step("MUDUR-01", "Mevcut yapı (A) ile hafızalı yapı (D) arasında günlük başarısız teslim farkı ne?", "analyst",
         "query_history", "ok"),
    # Uzmana gerçekten gidilmeye çalışılsın: kimlik sınırı (scope) reddi akışta "denied" satırı olarak görünür.
    Step("O02", "Planlama Ajanına sor: bugünün şube planını ve kurye atamalarını getir.", "planner", "", "denied"),
)


def enabled() -> bool:
    return os.environ.get(ENABLE_ENV, "1").strip().lower() not in ("0", "false", "no", "off", "")


def _agent(v: object) -> str:
    s = re.sub(r"[^a-z_]", "", str(v or "").lower())[:24]
    return s or "supervisor"


def _num(v: object) -> int | None:
    try:
        return round(float(v))
    except (TypeError, ValueError):
        return None


def map_trace(t: dict) -> dict:
    """`cm_trace` → canlı akış `ev` olayı (§5 biçimi + agent, parent, seq, ms, ok; source "agentcore")."""
    kind = TRACE_TYPES.get(str(t.get("type") or ""), "info")
    agent = _agent(t.get("agent"))
    tool = re.sub(r"[^A-Za-z0-9_.-]", "", str(t.get("tool") or ""))[:64] or None
    e: dict = {"type": kind, "agent": agent, "parent": _agent(t["parent"]) if t.get("parent") else None,
               "tool": tool, "source": "agentcore"}
    if (seq := _num(t.get("seq"))) is not None:
        e["seq"] = seq
    if (ms := _num(t.get("ms"))) is not None:
        e["ms"] = ms
    if isinstance(t.get("ok"), bool):
        e["ok"] = t["ok"]
    if t.get("input") is not None:
        e["input"] = trim(_scrub_deep(t["input"]))
    if t.get("summary") is not None:
        e["summary"] = scrub(t["summary"] if isinstance(t["summary"], str) else json.dumps(t["summary"], ensure_ascii=False))
    if kind == "error":
        e["text"] = e.get("summary") or "hata"
    if kind in ("delegate", "delegate_end"):
        e["target"] = agent if agent != "supervisor" else TOOL_AGENT.get(tool or "", tool or "")
    elif tool in TOOL_AGENT:                       # Supervisor'ın ask_* aracı: hangi uzmana gidiyor (ya da gidemedi)
        e["target"] = TOOL_AGENT[tool]
    return e


def _scrub_deep(v: object, depth: int = 0) -> object:
    if isinstance(v, str):
        return scrub(v)
    if isinstance(v, dict) and depth < 4:
        return {str(k)[:64]: _scrub_deep(x, depth + 1) for k, x in list(v.items())[:20]}
    if isinstance(v, list) and depth < 4:
        return [_scrub_deep(x, depth + 1) for x in v[:20]]
    return v if isinstance(v, (int, float, bool)) or v is None else scrub(v)


class StreamReader:
    """Bir Supervisor yanıt akışını okur: `cm_trace` olaylarını hemen yayınlar, metni toplar, yedek araç izini tutar."""

    def __init__(self, emit, traced_run: bool):
        self.emit = emit
        self.traced_run = traced_run          # koşuda daha önce cm_trace geldiyse yedek iz hiç tutulmaz
        self.traced = False
        self.messages: list[list[str]] = [[]]
        self.pending: list[dict] = []         # cm_trace gelmezse adım sonunda yayınlanacak Supervisor araç çağrıları
        self.block: dict | None = None
        self.error: str | None = None
        self.hops: list[dict] = []

    def feed(self, item: dict) -> None:
        if isinstance(item.get("cm_trace"), dict):
            self.traced, self.pending = True, []
            e = map_trace(item["cm_trace"])
            if e["type"] in ("tool", "denied", "error", "delegate"):
                self.hops.append({k: e.get(k) for k in ("type", "agent", "parent", "tool", "target")})
            self.emit("ev", e=e)
        elif item.get("error"):
            self.error = scrub(item["error"], 200)
        elif isinstance(item.get("event"), dict):
            self._model_event(item["event"])

    def _model_event(self, ev: dict) -> None:
        if "messageStart" in ev and self.messages[-1]:
            self.messages.append([])
        start = ((ev.get("contentBlockStart") or {}).get("start") or {}).get("toolUse")
        if isinstance(start, dict) and start.get("name") and not (self.traced or self.traced_run):
            self.block = {"tool": str(start["name"])[:64], "input": []}
            self.pending.append(self.block)
        delta = (ev.get("contentBlockDelta") or {}).get("delta") or {}
        if isinstance(delta.get("text"), str):
            self.messages[-1].append(delta["text"])
        tu = delta.get("toolUse")
        if self.block is not None and isinstance(tu, dict) and isinstance(tu.get("input"), str):
            self.block["input"].append(tu["input"])
        if "contentBlockStop" in ev:
            self.block = None

    def text(self) -> str:
        return scrub("\n".join("".join(m).strip() for m in self.messages if "".join(m).strip()), ANSWER_LIMIT)

    def finish(self) -> None:
        """cm_trace hiç gelmediyse Supervisor'ın araç çağrılarını sırayla yayınlar (eski dağıtım yedeği)."""
        if self.traced:
            return
        for b in self.pending:
            raw = "".join(b["input"])
            try:
                inp = json.loads(raw) if raw else {}
            except ValueError:
                inp = {"raw": raw}
            target = TOOL_AGENT.get(b["tool"])
            e = {"type": "tool", "agent": "supervisor", "parent": None, "tool": b["tool"], "input": trim(_scrub_deep(inp)),
                 "source": "agentcore", "fallback": True, **({"target": target} if target else {})}
            self.hops.append({"type": "tool", "agent": "supervisor", "parent": None, "tool": b["tool"], "target": target,
                              "fallback": True})
            self.emit("ev", e=e)
        self.pending = []


class Chain:
    """Altı istek, sırayla: Planlama · Kurye brifingi · Hafıza notu · Hasat soruları · Analiz (Athena) · kimlik reddi."""

    def __init__(self, live, client: ACC.SupervisorClient | None = None, steps: tuple[Step, ...] = STEPS):
        self.L = live
        self.client = client or ACC.default_client()
        self.steps = steps
        self.run_id = getattr(live, "run_id", 0)
        self.sessions: dict[str, str] = {}
        self.traced_run = False
        self.day = self._day()

    @staticmethod
    def _day() -> int | None:
        try:
            from api import main as M

            return int(M.meta()["critical"]["day"])
        except Exception:  # noqa: BLE001 - gün bilinmiyorsa Supervisor kendi varsayılanını kullanır
            return None

    def session_for(self, actor: str) -> str:
        return self.sessions.setdefault(actor, ACC.session_id(f"{self.run_id}-{actor}"))

    def side(self) -> None:
        try:
            from api import main as M

            m = M.memory_summary(self.day) if self.day is not None else {}
            f = M.agent_feed()["events"][-8:]
            self.L.emit("side", memory={"total": m.get("total"), "type_distribution": m.get("type_distribution") or {},
                                        "last": (m.get("last") or [])[:3]},
                        feed=[{k: e.get(k) for k in ("n", "agent", "type", "status", "summary")} for e in f])
        except Exception:  # noqa: BLE001 - yan panel isteğe bağlı
            pass

    # ---------------------------------------------------------------- koşu
    def run(self) -> str:
        self.L.emit("run", kind="agentcore", day=self.day, courier="O02", name="", mode="agentcore",
                    model=None, runtime=ACC.supervisor_name(), steps=len(self.steps), started=time.strftime("%H:%M:%S"),
                    chain=[{"actor": s.actor, "prompt": s.prompt, "agent": s.agent, "tool": s.tool, "expect": s.expect}
                           for s in self.steps])
        self.side()
        for i, st in enumerate(self.steps):
            self.L.emit("step", i=i, actor=st.actor, prompt=st.prompt, agent=st.agent, tool=st.tool, expect=st.expect)
            try:
                self.L.emit("result", i=i, out=self.step(st))
            except AgentCoreError as e:
                self.L.emit("step_error", i=i, text=str(e))
                if e.fatal:
                    self.L.emit("note", text="AgentCore'a ulaşılamadığı için zincir durdu; kalan adımlar çalıştırılmadı.")
                    return "error"
            except Exception as e:  # noqa: BLE001 - beklenmeyen hata adımda kalır, zincir sürer
                self.L.emit("step_error", i=i, text=f"Adım tamamlanamadı ({type(e).__name__}).")
            self.side()
            if i < len(self.steps) - 1:
                time.sleep(STEP_GAP)
        return "done"

    def step(self, st: Step) -> dict:
        payload = {"prompt": st.prompt, "actorId": st.actor, **({"day": self.day} if self.day is not None else {})}
        self.L.emit("http", method="invoke", path=f"InvokeAgentRuntime · {ACC.supervisor_name()}", body=payload)
        reader = StreamReader(self.L.emit, self.traced_run)
        t0 = time.perf_counter()
        ms = lambda: round((time.perf_counter() - t0) * 1000)  # noqa: E731
        try:
            for item in self.client.invoke(payload, self.session_for(st.actor)):
                reader.feed(item)
        except AgentCoreError as e:
            reader.finish()
            self.L.emit("http_done", status=502, ms=ms(), data={"detail": str(e)})
            raise
        reader.finish()
        self.traced_run = self.traced_run or reader.traced
        text = reader.text()
        if reader.error:
            self.L.emit("http_done", status=502, ms=ms(), data={"detail": reader.error})
            raise AgentCoreError(f"Supervisor hata döndürdü: {reader.error}")
        took = ms()
        self.L.emit("http_done", status=200, ms=took, data={"answer": text})
        if text:
            self.L.emit("ev", e={"type": "answer", "agent": "supervisor", "parent": None, "text": text, "source": "agentcore"})
        denied = [h for h in reader.hops if h["type"] == "denied"]
        return {"actor": st.actor, "prompt": st.prompt, "answer": text, "ms": took, "traced": reader.traced,
                "expected": {"agent": st.agent, "tool": st.tool, "expect": st.expect},
                "path": _path(reader.hops), "tools": [h["tool"] for h in reader.hops if h["type"] == "tool" and h["tool"]],
                "denied": bool(denied)}


def _path(hops: list[dict]) -> list[str]:
    """Atlama sırası: Supervisor → ulaşılan uzman(lar), tekrarsız. Reddedilen ask_* uzmana ulaşmadığı için sayılmaz;
    hedef yalnız delegate olayından ya da (cm_trace yoksa) Supervisor'ın araç çağrısından alınır."""
    out = ["supervisor"]
    for h in hops:
        reached = h.get("target") if h.get("type") == "delegate" or h.get("fallback") else None
        for a in (h.get("agent"), reached):
            if a and a in AGENTS and a not in out:
                out.append(a)
    return out

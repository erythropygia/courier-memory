"""Canlı zincir izi (`cm_trace`): runtime'ın kendi araç adımları ve supervisor'ın uzmandan aktardığı adımlar.

Akışa model olaylarının (`{"event": ...}`) yanında `{"cm_trace": {...}}` öğeleri girer (sözleşme: README "cm_trace").
Alanlar: seq, agent, parent, type, tool, input, summary, ms, ok.

İz kuyruğu (`TraceSink`) isteğe aittir: main.py her istekte yenisini kurar ve Strands `invocation_state` ile kancaya
(`TraceHooks`) ve uzman araçlarına (cm/roles.py) verir. Ajan önbellekte olsa da iki istek aynı kuyruğu paylaşmaz.
Araçlar başka iş parçacığında çalışır; kuyruk kilitlidir, sıra numarası ve ekleme aynı kilit altında yapılır.

Gizli bilgi akışa girmez: girdi ve özetteki telefon, hitaplı ad ve şifre/kod rakamları maskelenir (cm/core.py kalıpları).
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry

from .core import HONORIFIC_NAME, PHONE, SECRET

STATE_KEY = "cm_trace"
SUMMARY_MAX = 400
ANSWER_MAX = 300
VALUE_MAX = 60
SUPERVISOR = "supervisor"
AGENTS = frozenset({"supervisor", "planner", "courier", "memory_keeper", "analyst", "all"})
TYPES = frozenset({"tool_call", "tool_result", "delegate_start", "delegate_end", "denied", "error"})
FIELDS = ("seq", "agent", "parent", "type", "tool", "input", "summary", "ms", "ok")
AGENT_LABELS = {"planner": "Planlama Ajanı", "courier": "Kurye Ajanı", "memory_keeper": "Hafıza Ajanı",
                "analyst": "Analiz Ajanı"}
_DIGITS = re.compile(r"\d{3,}")


# ------------------------------------------------------------------ maskeleme ve özet
def redact(text: str) -> str:
    """Telefon ve hitaplı ad maskelenir; şifre/kod geçen metinde 3+ haneli sayılar gizlenir."""
    t = PHONE.sub("[telefon]", text or "")
    t = HONORIFIC_NAME.sub("[ad]", t)
    return _DIGITS.sub("***", t) if SECRET.search(t) else t


def clip(text: str, limit: int = SUMMARY_MAX) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _clean(value: Any) -> Any:
    """Girdinin maskelenmiş kopyası (özgün sözlük değişmez)."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _short(value: Any) -> str:
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return s if len(s) <= VALUE_MAX else s[: VALUE_MAX - 1] + "…"


def _describe(obj: Any) -> str:
    if isinstance(obj, dict):
        if obj.get("error"):
            return f"hata: {obj['error']}"
        parts = []
        for key, val in obj.items():
            if isinstance(val, list):
                parts.append(f"{key}: {len(val)} öğe")
            elif isinstance(val, dict):
                parts.append(f"{key}: {len(val)} alan")
            elif val is not None:
                parts.append(f"{key}={_short(val)}")
        return ", ".join(parts) or "boş sonuç"
    if isinstance(obj, list):
        return f"{len(obj)} öğe"
    return str(obj)


def summarize_result(text: str) -> str:
    """Aracın JSON sonucunun kısa özeti: liste/sözlük alanları sayı olarak, düz alanlar kısaltılmış değerle."""
    try:
        obj = json.loads(text)
    except (TypeError, ValueError):
        return clip(redact(text))
    return clip(redact(_describe(obj)))


def _result_text(result: Any) -> str:
    content = result.get("content") or [] if isinstance(result, dict) else []
    return " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict) and c.get("text"))


# ------------------------------------------------------------------ istek başına kuyruk
class TraceSink:
    """İsteğe ait, iş parçacığı güvenli iz kuyruğu; `seq` istek içinde artar."""

    def __init__(self, agent: str):
        self.agent = agent
        self._items: list[dict] = []
        self._seq = 0
        self._lock = threading.Lock()

    def _put(self, fields: dict) -> dict:
        with self._lock:                       # numara ve ekleme birlikte: kuyruktaki sıra = seq sırası
            self._seq += 1
            item = {**fields, "seq": self._seq}
            self._items.append({STATE_KEY: item})
        return item

    def emit(self, type_: str, *, agent: str | None = None, parent: str | None = None, tool: str | None = None,
             input: dict | None = None, summary: str = "", ms: int | None = None, ok: bool | None = None) -> dict:
        return self._put({"agent": agent or self.agent, "parent": parent, "type": type_, "tool": tool,
                          "input": _clean(input) if isinstance(input, dict) else None,
                          "summary": clip(redact(summary)), "ms": ms, "ok": ok})

    def forward(self, item: Any, parent: str = SUPERVISOR) -> dict | None:
        """Uzmanın iz öğesini supervisor sırasına alır: `parent` atanır, `seq` yeniden numaralanır, `agent` korunur."""
        if not isinstance(item, dict) or item.get("type") not in TYPES:
            return None
        agent = item.get("agent") if item.get("agent") in AGENTS else self.agent
        ms, ok = item.get("ms"), item.get("ok")
        return self._put({"agent": agent, "parent": parent, "type": item["type"],
                          "tool": item.get("tool") if isinstance(item.get("tool"), str) else None,
                          "input": _clean(item.get("input")) if isinstance(item.get("input"), dict) else None,
                          "summary": clip(redact(str(item.get("summary") or ""))),
                          "ms": ms if isinstance(ms, (int, float)) and not isinstance(ms, bool) else None,
                          "ok": ok if isinstance(ok, bool) else None})

    def drain(self) -> list[dict]:
        with self._lock:
            items, self._items = self._items, []
        return items


def sink_of(state: Any) -> TraceSink | None:
    sink = state.get(STATE_KEY) if isinstance(state, dict) else None
    return sink if isinstance(sink, TraceSink) else None


# ------------------------------------------------------------------ Strands kancası
class TraceHooks(HookProvider):
    """Her araç çalışmasının önü/sonu: tool_call → tool_result; kimlik sınırı iptal ettiyse yalnız denied.

    CourierScope'tan SONRA kaydedilmeli: BeforeToolCallEvent kayıt sırasıyla çağrılır, ret kararı (`cancel_tool`) görülür.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before)
        registry.add_callback(AfterToolCallEvent, self.after)

    def before(self, event: BeforeToolCallEvent) -> None:
        sink = sink_of(event.invocation_state)
        if sink is None:
            return
        name = event.tool_use.get("name") or None
        tool_input = event.tool_use.get("input")
        if event.cancel_tool:
            reason = event.cancel_tool if isinstance(event.cancel_tool, str) else "Araç çağrısı iptal edildi."
            sink.emit("denied", tool=name, input=tool_input, summary=reason)
        else:
            sink.emit("tool_call", tool=name, input=tool_input, summary=f"{name} çağrılıyor")

    def after(self, event: AfterToolCallEvent) -> None:
        sink = sink_of(event.invocation_state)
        if sink is None or event.cancel_message is not None:      # reddedilen çağrının sonucu ayrıca yazılmaz
            return
        ok = isinstance(event.result, dict) and event.result.get("status") == "success"
        text = _result_text(event.result)
        summary = summarize_result(text) if ok else f"hata: {text or type(event.exception).__name__}"
        ms = round(event.duration * 1000) if event.duration is not None else None
        sink.emit("tool_result", tool=event.tool_use.get("name") or None, summary=summary, ms=ms, ok=ok)


# ------------------------------------------------------------------ supervisor → uzman
def traced_delegation(sink: TraceSink | None, role: str, question: str, day: int | None,
                      call: Callable[[Callable[[dict], Any] | None], str]) -> str:
    """Uzman çağrısını delegate_start / (aktarılan uzman izi) / delegate_end ile sarar; hata error olarak yazılır, yükselir.

    `call(on_trace)` uzmanı çağırır; `on_trace` uzman akışındaki her `cm_trace` öğesi için çağrılır.
    """
    if sink is None:
        return call(None)
    label = AGENT_LABELS.get(role, role)
    sink.emit("delegate_start", agent=role, parent=SUPERVISOR, input={"question": question, "day": day},
              summary=f"{label}na soruluyor: {question}")
    started = time.monotonic()
    try:
        answer = call(sink.forward)
    except Exception as e:
        from .delegate import DelegationError

        reason = str(e) if isinstance(e, DelegationError) else f"{label} çağrısı başarısız ({type(e).__name__})."
        sink.emit("error", agent=role, parent=SUPERVISOR, summary=reason)
        sink.emit("delegate_end", agent=role, parent=SUPERVISOR, ms=_ms(started), ok=False, summary=reason)
        raise
    sink.emit("delegate_end", agent=role, parent=SUPERVISOR, ms=_ms(started), ok=True,
              summary=clip(answer, ANSWER_MAX))
    return answer


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)

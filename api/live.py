"""Canlı akış (sunum): sekiz adımlık ajan zinciri sunucuda bir kez koşar, olayları herkese yayınlanır.

Sunum ekranı (hikaye Sahne 3 ya da /flow/?sunum=1) "Günü planla" ile koşuyu başlatır; QR ile gelen izleyiciler
(/flow/) aynı olayları SSE ile canlı izler ve koşu başlatamaz. Adımlar /flow/'un eski adımlarıyla ve ui/demo/build.py ile
aynı uç fonksiyonlarını aynı gövdelerle çağırır (süreç içinde, HTTP'siz). Durum bellek içidir (web tek ECS görevi);
sunucu yeniden başlarsa boşalır. Olay biçimi docs/sozlesmeler.md §4.9.
İkinci zincir "AgentCore zinciri" (api/agentcore_chain.py) aynı `Live` yayınını kullanır: `start(kind="agentcore")`.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

NOTE_TEXT = "sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakıp yürüyün. B blok kapı şifresi 2580"
STEP_COUNT = 8
TEMPO_ORCH = 0.14        # sn/olay: orkestratör izi canlı akar; kurallı modda hepsi bir anda gelir, izlenebilsin diye
TEMPO_REPLAY = 0.10      # sn/olay: izini sonunda döndüren ajanlar (Brifing, Hafıza, Hasat, Değerlendirme, Bölge)
STEP_GAP = 1.4           # sn: adımlar arası, izleyici sonucu görsün


class LiveBusy(Exception):
    pass


def trim(v: Any, depth: int = 0) -> Any:
    """Telefona giden veri kısa kalsın: listeler 8 öğe, derin nesneler özet, uzun metin 400 karakter."""
    if isinstance(v, str) and v[:1] in "{[":
        try:
            v = json.loads(v)
        except ValueError:
            pass
    if isinstance(v, list):
        out = [trim(x, depth + 1) for x in v[:8]]
        return out + [f"… +{len(v) - 8}"] if len(v) > 8 else out
    if isinstance(v, dict):
        return {k: trim(x, depth + 1) for k, x in v.items()} if depth < 3 else "{…}"
    if isinstance(v, str) and len(v) > 400:
        return v[:400] + "…"
    return v


class Live:
    """Tek koşu, çok izleyici. Olaylar koşu numarası (`run`) ve sıra (`n`) taşır; yeni koşu listeyi baştan başlatır."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.run_id = 0
        self.status = "idle"            # idle | running | done | error
        self.kind = "day"               # day (sekiz adım, süreç içi) | agentcore (api/agentcore_chain.py)
        self.events: list[dict] = []

    # ---------------------------------------------------------------- yayın
    def emit(self, t: str, **kw: Any) -> dict:
        with self._lock:
            e = {"run": self.run_id, "n": len(self.events), "t": t, **kw}
            self.events.append(e)
        return e

    def snapshot(self, after: int = 0) -> dict:
        with self._lock:
            return {"run_id": self.run_id, "status": self.status, "kind": self.kind, "total": len(self.events),
                    "events": self.events[after:]}

    def pull(self, run: int | None, n: int) -> tuple[list[dict], int, int, str]:
        """İzleyicinin konumundan sonraki olaylar. Koşu değiştiyse yeni koşunun hepsi (ilk olay `run`: istemci sıfırlar)."""
        with self._lock:
            if run != self.run_id:
                return list(self.events), self.run_id, len(self.events), self.status
            return self.events[n:], run, len(self.events), self.status

    # ---------------------------------------------------------------- koşu
    def start(self, target=None, kind: str = "day") -> dict:
        with self._lock:
            if self.status == "running":
                raise LiveBusy()
            self.run_id += 1
            self.events = []
            self.status = "running"
            self.kind = kind
            run = self.run_id
        threading.Thread(target=target or self._work, args=(run,), daemon=True).start()
        return {"run_id": run, "status": "running", "kind": kind}

    def runner(self, make_chain):
        """Başka bir zincir (ör. AgentCore) aynı yayınla koşsun: `start(target=LIVE.runner(X), kind=...)`."""
        return lambda run: self._work(run, make_chain)

    def _work(self, run: int, make_chain=None) -> None:
        try:
            status = (make_chain or Chain)(self).run() or "done"     # zincir "error" döndürebilir (ör. erişim yok)
        except Exception as e:                       # zincirin dışında bir hata (adım hataları adımda kalır)
            self.emit("step_error", i=-1, text=str(e))
            status = "error"
        with self._lock:
            if self.run_id == run:
                self.status = status
        self.emit("end", status=status)


class Chain:
    """Sekiz adım: Orkestratör → acil durum kapısı → Brifing → Hafıza → durak kartları → Hasat → Değerlendirme → Bölge."""

    def __init__(self, live: Live):
        from api import main as M

        self.L, self.M = live, M
        meta = M.meta()
        self.day, self.courier = meta["critical"]["day"], meta["critical"]["courier"]
        self.name = meta["critical"].get("courier_name", "")
        self.session: str | None = None
        self.status: str | None = None
        self.stop: dict | None = None

    # ---------------------------------------------------------------- yardımcılar
    def call(self, method: str, path: str, fn, body: dict | None = None):
        """Uç fonksiyonunu çağırır; izde HTTP isteği ve yanıtı gibi görünür (aynı yol, aynı gövde)."""
        from fastapi import HTTPException

        self.L.emit("http", method=method, path=path, body=body)
        t0 = time.perf_counter()
        try:
            out = fn()
        except HTTPException as e:
            self.L.emit("http_done", status=e.status_code, ms=round((time.perf_counter() - t0) * 1000), data={"detail": e.detail})
            raise RuntimeError(str(e.detail)) from None
        self.L.emit("http_done", status=200, ms=round((time.perf_counter() - t0) * 1000), data=trim(out))
        return out

    def event(self, e: dict) -> None:
        e = {k: v for k, v in e.items() if k not in ("i",)}
        for k in ("data", "input", "proposal"):
            if k in e:
                e[k] = trim(e[k])
        self.L.emit("ev", e=e)

    def replay(self, events: list[dict], tempo: float = TEMPO_REPLAY) -> None:
        for e in events:
            self.event(e)
            time.sleep(tempo)

    def steps_as_events(self, steps: list[dict], mode: str | None) -> list[dict]:
        """İz taşımayan yanıtların (Brifing, Hafıza) `steps[]` listesi → araç + sonuç olayları."""
        src = "rule" if mode == "mock" else "llm"
        out = []
        for x in steps or []:
            out += [{"type": "tool", "tool": x.get("tool"), "input": x.get("input"), "source": src},
                    {"type": "result", "tool": x.get("tool"), "summary": x.get("summary"), "source": src}]
        return out

    def side(self) -> None:
        m = self.M.memory_summary(self.day)
        f = self.M.agent_feed()["events"][-8:]
        self.L.emit("side", memory={"total": m.get("total"), "type_distribution": m.get("type_distribution") or {},
                                    "last": (m.get("last") or [])[:3]},
                    feed=[{k: e.get(k) for k in ("n", "agent", "type", "status", "summary")} for e in f])

    # ---------------------------------------------------------------- koşu
    def run(self) -> None:
        st = self.M.status()
        self.L.emit("run", day=self.day, courier=self.courier, name=self.name, mode=st.get("mode"), model=st.get("model"),
                    steps=STEP_COUNT, started=time.strftime("%H:%M:%S"))
        self.M.reset_demo(self.M.DayRequest(day=self.day))      # hafıza, ajan akışı, öğrenilen ayarlar baştan: her koşu aynı yerden
        self.side()
        steps = [self.orchestrator, self.gate, self.briefing, self.note, self.approach, self.harvest, self.review, self.region]
        for i, fn in enumerate(steps):
            self.L.emit("step", i=i)
            try:
                out = fn()
                self.L.emit("result", i=i, out=out)
            except Exception as e:  # adım hatası izde kalır, zincir sürer (eski "Hepsini oynat" gibi)
                self.L.emit("step_error", i=i, text=str(e))
            try:
                self.side()
            except Exception:
                pass
            if i < len(steps) - 1:
                time.sleep(STEP_GAP)

    def orchestrator(self) -> dict:
        M = self.M
        k = self.call("POST", "/api/orchestrator/start", lambda: M.start_orch(M.OrchStartRequest(day=self.day)), {"day": self.day})
        self.session = k["session_id"]
        s = M.sv().sessions.get(self.session)
        n = 0
        while True:                                  # iz canlı: olaylar koşu sürerken gelir
            evs = s.trace.since(n)
            for e in evs:
                self.event(e)
                time.sleep(TEMPO_ORCH)
            n += len(evs)
            if s.done.is_set() and n >= len(s.trace):
                break
            if not evs:
                time.sleep(0.2)
        r = s.summary(len(s.trace))
        self.status = r["status"]
        p = r.get("proposal") or {}
        return {"status": r["status"], "escalation": [{"text": x.get("text")} for x in r.get("escalation") or []],
                "proposal": {"courier_count": (p.get("total") or {}).get("courier_count"),
                             "expected_fails": (p.get("total") or {}).get("expected_fails"),
                             "history_blind": (p.get("comparison") or {}).get("history_blind_expected_fails"),
                             "borrowed": [b.get("name") for b in p.get("borrowed") or []],
                             "own_zone_share": p.get("own_zone_share"),
                             "rationale": (p.get("rationale") or [])[:4], "risks": (p.get("risks") or [])[:2]} if p else None}

    def gate(self) -> dict:
        M = self.M
        if not self.session:
            raise RuntimeError("Orkestratör planı çıkmadı")
        if self.status == "finalized":
            self.L.emit("note", text="Acil durum yok: plan temassız kesinleşti; müdüre onay isteği gitmedi.")
            return {"auto": True, "name": self.name}
        self.L.emit("note", text="Acil durum: plan müdüre eskale edildi. Sunum akışında müdür onayı burada verilir.")
        r = self.call("POST", f"/api/orchestrator/session/{self.session}/decision",
                      lambda: M.orch_decision(self.session, M.DecisionRequest(decision="approval")), {"decision": "approval"})
        s = M.sv().sessions.get(self.session)
        self.replay([e for e in s.trace.since(0) if e["type"] in ("human_decision", "done")][-2:])
        return {"auto": False, "status": r.get("status"), "name": self.name}

    def briefing(self) -> dict:
        M = self.M
        b = self.call("GET", f"/api/briefing/{self.day}/{self.courier}", lambda: M.briefing(self.day, self.courier))
        self.replay(self.steps_as_events(b.get("steps"), b.get("mode")))
        return {"courier_name": b.get("courier_name"), "morning_briefing": b.get("morning_briefing"),
                "estimated_return": b.get("estimated_return"), "door_count": len(b.get("door_sentences") or []),
                "warnings": b.get("warnings") or []}

    def note(self) -> dict:
        M = self.M
        cards = self.call("GET", f"/api/cards/{self.day}/{self.courier}?all=true", lambda: M.stop_cards(self.day, self.courier, True))
        self.stop = next((x for x in cards["stops"] if not x["cards"]), cards["stops"][0])
        self.L.emit("note", text=f"Rotanın {self.stop['order']}. durağı ({self.stop.get('label', '')}) hafızada kartsız. Kurye buraya not bırakıyor:")
        body = {"day": self.day, "courier": self.courier, "lat": self.stop["lat"], "lng": self.stop["lng"], "text": NOTE_TEXT}
        r = self.call("POST", "/api/note", lambda: M.process_note(M.NoteRequest(**body)), body)
        self.replay(self.steps_as_events(r.get("steps"), r.get("mode")))
        return {"text": NOTE_TEXT, "type": r.get("type"), "hint": r.get("hint"), "redacted": bool(r.get("personal_data_redacted")),
                "status": r.get("status"), "summary": r.get("summary")}

    def approach(self) -> dict:
        M = self.M
        if not self.stop:
            raise RuntimeError("Önce 4. adım")
        s = self.stop
        base = {"day": self.day, "courier": self.courier, "next_order": s["order"]}

        def ap(lat, label, shown=()):
            body = {**base, "lat": lat, "lng": s["lng"], **({"shown": list(shown)} if shown else {})}
            self.L.emit("note", text=label)
            return self.call("POST", "/api/approach", lambda: M.approach(M.ApproachRequest(**body)), body)

        a = ap(s["lat"] + 0.006, "Kurye durağa ~660 m uzakta:")
        self.L.emit("note", text=f"{(a.get('stop') or {}).get('distance_m')} m → henüz söylenecek kart yok; bekleyen {a.get('pending')}.")
        b = ap(s["lat"] + 0.002, "~220 m kala:")
        self.L.emit("note", text=f"An: {'yaklaşırken' if b.get('moment') == 'approaching' else b.get('moment')} · söylenecek: “{b.get('to_speak') or '—'}”")
        c = ap(s["lat"], "Kapıda (söylenen kart tekrar söylenmez):", [k["id"] for k in b.get("cards") or []])
        dist = lambda x: (x.get("stop") or {}).get("distance_m")
        return {"a": {"distance_m": dist(a)}, "b": {"distance_m": dist(b), "moment": b.get("moment"), "to_speak": b.get("to_speak"),
                                                    "cards": [{k: x.get(k) for k in ("title", "confidence", "affects_route")} for x in b.get("cards") or []]},
                "c": {"distance_m": dist(c), "to_speak": c.get("to_speak")}}

    def harvest(self) -> dict:
        M = self.M
        r = self.call("POST", "/api/harvest/plan", lambda: M.plan_harvest(M.DayRequest(day=self.day)), {"day": self.day})
        self.replay(r.get("trace") or [])
        q = r.get("questions") or []
        return {"count": len(q), "summary": r.get("summary"),
                "questions": [{"courier_name": x.get("courier_name"), "question": x.get("question")} for x in q[:3]]}

    def review(self) -> dict:
        M = self.M
        r = self.call("POST", "/api/review/run", lambda: M.run_review(M.DayRequest(day=self.day)), {"day": self.day})
        self.replay(r.get("trace") or [])
        rep = r.get("report") or {}
        p = r.get("params") or {}
        return {"summary": rep.get("summary"), "going_well": rep.get("going_well") or [], "going_badly": rep.get("going_badly") or [],
                "general_bias_min": p.get("general_bias_min"), "unfamiliar_stop_extra_min": p.get("unfamiliar_stop_extra_min")}

    def region(self) -> dict:
        M = self.M
        r = self.call("POST", "/api/region/run", lambda: M.run_region(M.DayRequest(day=self.day)), {"day": self.day})
        self.replay(r.get("trace") or [])
        q = r.get("questions") or []
        return {"manager_summary": r.get("manager_summary") or [], "count": len(q), "questions": [x.get("question") for x in q[:2]]}


LIVE = Live()

"""Ajan akışı: şubede ajanların yaptığı her işin zaman sıralı kaydı (operasyon paneli okur).

Olay: {"n", "zaman", "gun", "ajan", "tur", "ozet", "durum", "kayit"?, "detay"?}
  ajan: hafiza | degerlendirme | hasat | orkestrator | mudur
  tur:  not | kayit_eklendi | kayit_guclendi | record_dropped | flagged_for_confirmation | soru | parametre | oneri | karar | rapor
  durum: uygulandi | awaiting_approval | onaylandi | reddedildi | undone | bilgi
Kişisel veri yazılmaz: not metninin kendisi değil, Hafıza Ajanı'nın ayıklanmış sonucu kaydedilir.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .rundata import ROOT

MAX_EVENTS = 2000


class AgentFeed:
    def __init__(self, path: str | Path | None = None):
        mem = os.environ.get("CM_MEMORY_FILE")
        self.path = Path(path) if path else (Path(mem).with_name("agent_feed.json") if mem else ROOT / "data" / "agent_feed.json")
        self._lock = threading.Lock()
        self.events: list[dict] = []
        if self.path.exists():
            try:
                self.events = json.loads(self.path.read_text(encoding="utf-8")).get("events", [])
            except (json.JSONDecodeError, OSError):
                self.events = []

    def add(self, *, agent: str, kind: str, summary: str, day: int | None = None, status: str = "applied", **detail) -> dict:
        with self._lock:
            o = {"n": (self.events[-1]["n"] + 1) if self.events else 1, "time": round(time.time(), 1), "day": day, "agent": agent,
                 "type": kind, "summary": summary, "status": status, **detail}
            self.events.append(o)
            self.events = self.events[-MAX_EVENTS:]
            self._save()
            return o

    def update(self, n: int, **fields) -> dict | None:
        with self._lock:
            o = next((x for x in self.events if x["n"] == n), None)
            if o is not None:
                o.update(fields)
                self._save()
            return o

    def items(self, after: int = 0, agent: str | None = None, status: str | None = None) -> list[dict]:
        with self._lock:
            return [o for o in self.events if o["n"] > after and (agent is None or o["agent"] == agent) and (status is None or o["status"] == status)]

    def reset(self) -> None:
        with self._lock:
            self.events = []
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"events": self.events}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

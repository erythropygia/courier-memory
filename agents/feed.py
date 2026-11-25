"""Ajan akışı: şubede ajanların yaptığı her işin zaman sıralı kaydı (operasyon paneli okur).

Olay: {"n", "zaman", "gun", "ajan", "tur", "ozet", "durum", "kayit"?, "detay"?}
  ajan: hafiza | degerlendirme | hasat | orkestrator | mudur
  tur:  not | kayit_eklendi | kayit_guclendi | record_dropped | flagged_for_confirmation | soru | parametre | oneri | karar | rapor
  durum: uygulandi | awaiting_approval | onaylandi | reddedildi | undone | bilgi
Depo: JSON dosyası (CM_STORAGE=file, varsayılan) ya da DynamoDB (CM_STORAGE=dynamodb); bkz. agents/storage.
Kişisel veri yazılmaz: not metninin kendisi değil, Hafıza Ajanı'nın ayıklanmış sonucu kaydedilir.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from .rundata import ROOT
from .storage import feed_repository
from .storage.base import FeedRepository

MAX_EVENTS = 2000


def _max_events() -> int:
    return MAX_EVENTS


class AgentFeed:
    def __init__(self, path: str | Path | None = None, repository: FeedRepository | None = None):
        mem = os.environ.get("CM_MEMORY_FILE")
        self.path = Path(path) if path else (Path(mem).with_name("agent_feed.json") if mem else ROOT / "data" / "agent_feed.json")
        self.repository = repository or feed_repository(self.path, _max_events)

    @property
    def events(self) -> list[dict]:
        return self.repository.events()

    def add(self, *, agent: str, kind: str, summary: str, day: int | None = None, status: str = "applied", **detail) -> dict:
        return self.repository.append(lambda n: {"n": n, "time": round(time.time(), 1), "day": day, "agent": agent,
                                                 "type": kind, "summary": summary, "status": status, **detail})

    def update(self, n: int, **fields) -> dict | None:
        return self.repository.update(n, fields)

    def items(self, after: int = 0, agent: str | None = None, status: str | None = None) -> list[dict]:
        return [o for o in self.repository.events(after)
                if (agent is None or o["agent"] == agent) and (status is None or o["status"] == status)]

    def reset(self) -> None:
        self.repository.reset()

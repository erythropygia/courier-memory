"""İstek gövdesi: {"prompt": "...", "actorId": "O02", "day": 32}.

`actorId` son kullanıcının kimliğidir (kurye kimliği ya da müdür); hafıza ad alanlarını ve araç erişimini belirler.
Gövdede yoksa "default" (konuk) sayılır: yalnız şube düzeyinde, salt okunur araçlar açıktır.
"""
from __future__ import annotations

from dataclasses import dataclass

GUEST = "default"


@dataclass(frozen=True)
class Request:
    prompt: str
    actor_id: str
    day: int | None


def parse_request(payload: dict | None) -> Request:
    p = payload or {}
    prompt = p.get("prompt")
    if prompt is None and isinstance(p.get("messages"), list) and p["messages"]:      # sohbet biçimi: son kullanıcı mesajı
        last = p["messages"][-1]
        c = last.get("content") if isinstance(last, dict) else None
        prompt = c if isinstance(c, str) else " ".join(b.get("text", "") for b in (c or []) if isinstance(b, dict))
    actor = str(p.get("actorId") or p.get("actor_id") or GUEST).strip() or GUEST
    day = p.get("day")
    return Request(prompt=str(prompt or "").strip(), actor_id=actor, day=int(day) if isinstance(day, (int, float)) else None)

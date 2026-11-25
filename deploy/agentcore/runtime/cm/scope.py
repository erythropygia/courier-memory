"""Kimlik sınırı: isteğin `actorId`'si hangi aracı, kimin verisi için çağırabilir.

Strands `BeforeToolCallEvent` kancası araç çalışmadan önce bakar; izin yoksa çağrıyı iptal eder ve modele araç sonucu
olarak "erişim reddedildi" metnini verir. Konuşma kesilmez: kurye kendi verisiyle devam eder (atölye Lab 4 deseni).

  kurye   kendi `courier_id`'siyle kurye araçları + herkese açık araçlar
  müdür   bütün araçlar, bütün kuryeler
  konuk   yalnız herkese açık, salt okunur araçlar
"""
from __future__ import annotations

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from .backend import role_of
from .tools import COURIER_TOOLS, MANAGER_TOOLS

COURIER_TOOL_NAMES = frozenset(t.tool_name for t in COURIER_TOOLS)
MANAGER_TOOL_NAMES = frozenset(t.tool_name for t in MANAGER_TOOLS)


def decide(actor_id: str, role: str, tool_name: str, tool_input: dict | None) -> str | None:
    """İzin varsa None; yoksa modele dönecek ret metni. Saf fonksiyon: testi kolay, kanca yalnız bunu çağırır."""
    inp = tool_input or {}
    if tool_name in MANAGER_TOOL_NAMES and role != "manager":
        return (f"Erişim reddedildi: {tool_name} yalnız şube müdürü içindir. "
                "Bu istekte müdür kimliği yok; şube planı, değerlendirme ve bölge raporu paylaşılmaz.")
    if tool_name in COURIER_TOOL_NAMES:
        if role == "guest":
            return (f"Erişim reddedildi: {tool_name} için kurye ya da müdür kimliği gerekir (istek gövdesinde actorId). "
                    "Kimliksiz çağıran yalnız şube özetini ve gerçek gün kanıtını görebilir.")
        target = str(inp.get("courier_id") or "")
        if role == "courier" and target != actor_id:
            return (f"Erişim reddedildi: {actor_id} yalnız kendi rotasını, kartlarını ve notlarını görebilir; "
                    f"{target or 'başka bir kurye'} için veri paylaşılmaz. Kendi verinizle devam edebilirsiniz.")
    return None


class CourierScope(HookProvider):
    def __init__(self, actor_id: str):
        self.actor_id = actor_id
        self.role = role_of(actor_id)
        self.denied: list[dict] = []          # gözlem ve test için: reddedilen çağrılar

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self.check)

    def check(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use.get("name", "")
        msg = decide(self.actor_id, self.role, name, event.tool_use.get("input"))
        if msg:
            self.denied.append({"tool": name, "input": event.tool_use.get("input"), "actor": self.actor_id})
            event.cancel_tool = msg

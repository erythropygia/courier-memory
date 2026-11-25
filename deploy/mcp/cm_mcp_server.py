"""Courier Memory MCP sunucusu (stdio): şubenin hafızasını ve gerçek gün kanıtını salt okunur araç olarak açar.

Kiro bu sunucuyu `.kiro/settings/mcp.json` ile yükler; spec yazarken ya da hata ayıklarken "O02'nin bugünkü kartları ne?",
"şube hafızasında kaç park kaydı var?" gibi soruları kod okumadan, çalışan veriden yanıtlar. Aynı sunucu, Strands
ajanına `MCPClient` ile ya da AgentCore Gateway'e MCP hedefi olarak da bağlanabilir (spec: agentcore-runtime, esnetme hedefleri).

  python deploy/mcp/cm_mcp_server.py            (repo kökünden; PYTHONPATH=sim:.)

Yazma aracı yoktur: not bırakma ve müdür kararları API ve ajan üzerinden yapılır (kimlik sınırı orada zorlanır).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "sim")):
    if p not in sys.path:
        sys.path.insert(0, p)

try:                                    # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:                     # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

server = _Server("courier-memory")
_sv = None


def _services():
    global _sv
    if _sv is None:
        os.environ.setdefault("CM_LLM_MODE", "mock")
        mem = os.environ.setdefault("CM_MEMORY_FILE", str(Path(tempfile.gettempdir()) / "cm-mcp" / "live_memory.json"))
        from agents import Services

        _sv = Services.create(os.environ.get("CM_RUN_DIR"), mode="mock", memory_file=mem)
        _sv.book.ensure(_sv.run.meta["critical"]["day"])
    return _sv


def _day(day: int | None) -> int:
    s = _services()
    d = int(day) if day else int(s.run.meta["critical"]["day"])
    if d not in s.run.eval_days:
        raise ValueError(f"Gün {d} değerlendirme döneminde değil ({s.run.eval_days[0]}–{s.run.eval_days[-1]})")
    return d


@server.tool()
def branch_memory_summary(day: int | None = None) -> dict:
    """Şube hafızası özeti: aktif adres kaydı sayısı ve tür dağılımı (kişisel veri içermez)."""
    s, d = _services(), _day(day)
    s.book.ensure(d)
    m = s.book.summary(d)
    return {"day": d, "active_records": m["total"], "type_distribution": m["type_distribution"]}


@server.tool()
def address_memory(address_id: int, day: int | None = None) -> dict:
    """Bir adresin hafızadaki geçerli kayıtları (tür, ipucu metni, kaynak sayısı)."""
    s, d = _services(), _day(day)
    s.book.ensure(d)
    a = s.run.address(int(address_id))
    return {"address": a["label"], "records": [{"id": e["id"], "kind": e["kind"], "text": e["text"], "sources": e.get("sources", 1)}
                                               for e in s.book.for_address(int(address_id), d)]}


@server.tool()
def courier_stop_cards(courier_id: str, day: int | None = None) -> dict:
    """Bir kuryenin o günkü rotasında bilgi kartı olan duraklar (yaklaşırken / kapıda)."""
    from agents.cards import StopCards

    s, d = _services(), _day(day)
    if courier_id not in s.run.couriers:
        raise ValueError(f"Bilinmeyen kurye: {courier_id}")
    L = StopCards(s.run, s.book, d, courier_id).items()
    return {"day": d, "courier": courier_id, "stops": L["stop"], "stops_with_cards": L["stops_with_cards"],
            "type_distribution": L["type_distribution"],
            "cards": [{"order": x["order"], "label": x["label"], "cards": [{"title": c["title"], "text": c["text"], "moment": c["moment"]}
                                                                          for c in x["cards"]]} for x in L["stops"]][:15]}


@server.tool()
def real_day_evidence() -> dict:
    """Gerçek Beykoz günü (5 Mayıs): durak ve gönderi sayısı, tanıdık ↔ yabancı sokakta başarısız teslim oranı."""
    from agents.real_day import RealDay

    s = _services()
    g = RealDay(s.run, s.book)
    return {"day": g.G["day"], "summary": g.G["summary"], "rates": g.G["rates"], "expected_fails": g.memory_summary()["expected_fails"]}


@server.tool()
def demo_context() -> dict:
    """Demo bağlamı: kritik gün, ödünç kurye, değerlendirme günleri, kurye kimlikleri."""
    s = _services()
    c = s.run.meta["critical"]
    return {"day": c["day"], "courier": c["courier"], "courier_name": c.get("courier_name"), "eval_days": s.run.eval_days,
            "couriers": sorted(s.run.couriers)}


if __name__ == "__main__":
    server.run()

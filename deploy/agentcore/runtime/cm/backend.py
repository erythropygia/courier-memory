"""Araçların arkasındaki iki uygulama; araç tanımları (tools.py) ikisinde de aynıdır.

  full  `agents.Services`: beş alan ajanı + Değerlendirme ve Bölge ajanları, hafızalı rota, gerçek gün kapsamı. 9 araç.
  core  `cm/core.py`: yalnız veri dosyaları ve standart kütüphane. 6 araç; müdür araçları yoktur.

Seçim `CM_TOOLSET` ile yapılır: `full`, `core` ya da `auto` (varsayılan). `auto` önce tam takımı dener; alan kodu
yüklenemezse (klasör yok, bağımlılık eksik, sürüm uyumsuz) nedenini loglar ve çekirdeğe düşer: ajan çökmez.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path

log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_BACKEND = None
MANAGER_ONLY_MSG = ("Bu dağıtım çekirdek araç takımıyla çalışıyor; plan, sabah değerlendirmesi ve bölge raporu "
                    "alan ajanları kurulunca açılır.")


class CoreBackend:
    name = "core"

    def __init__(self):
        from .core import CoreStore

        self.store = CoreStore()

    def couriers(self):
        return self.store.couriers

    def courier_name(self, cid):
        return self.store.courier_name(cid)

    def default_day(self):
        return self.store.default_day

    def eval_days(self):
        return self.store.eval_days

    def briefing(self, courier, day):
        return self.store.briefing(courier, day)

    def stop_cards(self, courier, day):
        return self.store.stop_cards(courier, day)

    def approach(self, courier, day, lat, lng, next_order, shown):
        return self.store.approach(courier, day, lat, lng, next_order, shown)

    def leave_note(self, courier, day, text, lat, lng):
        return self.store.leave_note(courier, day, text, lat, lng)

    def memory_summary(self, day):
        return self.store.memory_summary(day)

    def real_day_evidence(self):
        return self.store.real_day_evidence()

    def plan_day(self, day):
        raise ValueError(MANAGER_ONLY_MSG)

    morning_review = region_report = plan_day


class FullBackend:
    name = "full"

    def __init__(self):
        os.environ.setdefault("CM_LLM_MODE", "mock")     # alt ajanlar kurallı yolda; kararı Strands ajanı verir
        mem = os.environ.setdefault("CM_MEMORY_FILE", str(Path(tempfile.gettempdir()) / "cm" / "live_memory.json"))
        from agents import Services

        self.sv = Services.create(os.environ.get("CM_RUN_DIR"), mode=os.environ["CM_LLM_MODE"], memory_file=mem)
        self.sv.book.ensure(self.default_day())

    def couriers(self):
        return self.sv.run.couriers

    def courier_name(self, cid):
        return self.sv.run.courier_name(cid)

    def default_day(self):
        return int(self.sv.run.meta["critical"]["day"])

    def eval_days(self):
        return self.sv.run.eval_days

    def _cards(self, courier, day):
        from agents.cards import StopCards

        return StopCards(self.sv.run, self.sv.book, day, courier, self.sv.sessions.plans.get(day))

    def briefing(self, courier, day):
        b = self.sv.briefing.prepare(day, courier)
        return {"day": day, "courier": courier, "name": b["courier_name"], "type": b["courier_type"],
                "morning_briefing": b["morning_briefing"], "estimated_return": b["estimated_return"],
                "expected_min": b["expected_min"], "warnings": b.get("warnings", []),
                "door_sentences": [{"order": k["order"], "sentence": k["sentence"]} for k in b.get("door_sentences", [])][:12],
                "route_changes": [c.get("text") for c in b.get("route_changes", [])], "plan_source": b["plan_source"], "toolset": "full"}

    def stop_cards(self, courier, day):
        L = self._cards(courier, day).items()
        return {"day": day, "courier": courier, "stops": L["stop"], "stops_with_cards": L["stops_with_cards"],
                "type_distribution": L["type_distribution"],
                "cards": [{"order": x["order"], "label": x["label"], "lat": x["lat"], "lng": x["lng"],
                           "cards": [{"id": c["id"], "title": c["title"], "text": c["text"], "moment": c["moment"],
                                      "confidence": c["confidence"]} for c in x["cards"]]} for x in L["stops"]][:20]}

    def approach(self, courier, day, lat, lng, next_order, shown):
        r = self._cards(courier, day).approach(lat, lng, next_order, shown or [])
        return {"moment": r["moment"], "to_speak": r["to_speak"], "pending": r["pending"], "stop": r["stop"],
                "cards": [{"id": c["id"], "title": c["title"], "text": c["text"]} for c in r["cards"]]}

    def leave_note(self, courier, day, text, lat, lng):
        r = self.sv.memory.process(day, courier, text.strip()[:500], lat, lng)
        return {"status": r["status"], "type": r.get("type"), "hint": r.get("hint"), "summary": r.get("summary"),
                "personal_data_redacted": r.get("personal_data_redacted"), "question": r.get("question"),
                "address": (r.get("address") or {}).get("label"), "record": (r.get("record") or {}).get("id")}

    def memory_summary(self, day):
        self.sv.book.ensure(day)
        m = self.sv.book.summary(day)
        return {"day": day, "active_records": m["total"], "type_distribution": m["type_distribution"],
                "latest": [{"kind": e["kind"], "text": e["text"]} for e in m["last"][:5]]}

    def real_day_evidence(self):
        from agents.real_day import RealDay

        g = RealDay(self.sv.run, self.sv.book)
        m = g.memory_summary()
        return {"day": g.G["day"], "stops": g.G["summary"]["stop"], "shipments": g.G["summary"]["shipment"],
                "couriers_fixed": len(g.G["couriers"]), "clusters_dynamic": len(g.G["clusters"]),
                "fail_rate_familiar": g.G["rates"]["fail_familiar"], "fail_rate_unfamiliar": g.G["rates"]["fail_unfamiliar"],
                "unfamiliar_share_history_aware": g.G["summary"]["unfamiliar_share"],
                "unfamiliar_share_history_blind": g.G["summary"]["unfamiliar_share_history_blind"],
                "memory_coverage_unfamiliar": m["coverage_unfamiliar"], "expected_fails": m["expected_fails"],
                "source": g.G["rates"]["source"], "assumption": m["assumption"]}

    def plan_day(self, day):
        k = self.sv.sessions.start(day, background=False).summary()
        p = k.get("proposal") or {}
        return {"day": day, "session_id": k["session_id"], "status": k["status"],
                "borrowed": [b["name"] for b in p.get("borrowed", [])], "courier_count": (p.get("total") or {}).get("courier_count"),
                "expected_fails": (p.get("total") or {}).get("expected_fails"), "own_zone_share": p.get("own_zone_share"),
                "history_blind_expected_fails": (p.get("comparison") or {}).get("history_blind_expected_fails"),
                "rationale": p.get("rationale", [])[:5], "risks": p.get("risks", [])[:3],
                "steps": [e["tool"] for e in k["events"] if e["type"] == "tool"],
                "note": "Plan öneridir; müdür onaylamadan uygulanmaz."}

    def morning_review(self, day):
        r = self.sv.review.morning_review(day)
        ev = self.sv.feed.items(agent="review")
        return {"day": day, "report": r["report"], "params": r["params"],
                "applied": [e["summary"] for e in ev if e["status"] == "applied" and e["type"] != "report"][-6:],
                "awaiting_approval": [e["summary"] for e in ev if e["status"] == "awaiting_approval"][-4:]}

    def region_report(self, day):
        r = self.sv.region.branch(day)
        return {"day": day, "manager_summary": r["manager_summary"], "questions": [q["question"] for q in r["questions"]],
                "blocks": r["summary"]["block"], "high_blocks": r["summary"]["high_blocks"], "memory_gaps": r["summary"]["gap"]}


def backend():
    """Tembel kurulur: süreç 30 sn içinde hazır olmalı (soğuk başlangıç)."""
    global _BACKEND
    with _LOCK:
        if _BACKEND is None:
            want = os.environ.get("CM_TOOLSET", "auto").lower()
            if want not in ("auto", "full", "core"):
                raise ValueError(f"CM_TOOLSET geçersiz: {want} (auto | full | core)")
            if want == "core":
                _BACKEND = CoreBackend()
            else:
                try:
                    _BACKEND = FullBackend()
                except Exception as e:  # noqa: BLE001 - alan kodu yüklenemedi: nedenini yaz, çekirdekle devam et
                    if want == "full":
                        raise
                    log.warning("Tam araç takımı kurulamadı (%s: %s); çekirdek araç takımıyla devam ediliyor.", type(e).__name__, e)
                    _BACKEND = CoreBackend()
        return _BACKEND


def reset_backend() -> None:
    global _BACKEND
    with _LOCK:
        _BACKEND = None


def role_of(actor_id: str) -> str:
    """courier: şubenin kuryesi · manager: şube müdürü · guest: kimliği belirsiz çağıran."""
    a = (actor_id or "").strip()
    if a in backend().couriers():
        return "courier"
    if a.upper().startswith(("MUDUR", "MGR", "MANAGER")):
        return "manager"
    return "guest"

"""Durak bilgi kartları ve yaklaşma tetiği (docs/sozlesmeler.md §11).

Hafızadaki her geçerli kayıt, kuryenin bugünkü rotasındaki durağa yapılı bir kart olarak çıkar. Kartın **anı** vardır:
`approaching` (park, adres tarifi, konum hatası, yol çalışması, arka giriş: araç durmadan önce lazım) ya da `at_door`
(zil, güvenlik, resepsiyon, bina erişimi…). Yaklaşma tetiği durumsuzdur: istemci konumu, sıradaki durağı ve daha önce
söylenen kart kimliklerini gönderir; sunucu o an söylenecek kartları döndürür. LLM yok, hesap deterministik.
"""
from __future__ import annotations

from cm_sim.routing_memory import CLOSED_ALWAYS_KINDS, CLOSED_DAY_KINDS, WINDOW_KINDS

from .briefing import BriefingTools, hint_today_valid
from .memorybook import MemoryBook
from .route import _routing_cfg
from .rundata import INFO_KINDS, RunData

APPROACH_M = 400        # bu mesafede "yaklaşırken" kartları söylenir (araç durağa varmadan, park yeri aranırken)
DOOR_M = 60             # bu mesafede "kapıda" kartları söylenir; söylenmemiş "yaklaşırken" kartları da eklenir
SPEAK_MAX = 2      # bir tetikte sesli okunacak en çok kart (sürüş güvenliği)

APPROACH_KINDS = ("park", "directions", "position_wrong", "roadwork", "back_entry")
TITLE = {
    "back_entry": "Arka giriş", "saturday_closed": "Cumartesi kapalı", "lunch_break": "Öğle arası", "safety": "Güvenlik",
    "bell": "Zil", "position_wrong": "Konum hatalı", "reception": "Resepsiyon", "temporary_closed": "Geçici kapalı",
    "roadwork": "Yol çalışması", "park": "Park", "building_access": "Bina erişimi", "directions": "Adres tarifi",
    "animal": "Hayvan", "other_info": "Not",
}
MOMENT_ORDER = {"approaching": 0, "at_door": 1}


def moment_of(kind: str) -> str:
    return "approaching" if kind in APPROACH_KINDS else "at_door"


def affects_route(kind: str, extra: dict) -> bool:
    """Bu tür plan/rota hesabına girer mi (kapanış, kapalı pencere ya da ek servis süresi)? Bilgi türleri hiçbir zaman."""
    if kind in INFO_KINDS:
        return False
    return kind in CLOSED_DAY_KINDS or kind in CLOSED_ALWAYS_KINDS or kind in WINDOW_KINDS or bool(extra.get(kind))


def card_of(e: dict, extra: dict) -> dict:
    n = int(e.get("sources", 1))
    return {"id": e["id"], "type": e["kind"], "title": TITLE.get(e["kind"], e["kind"]), "text": e["text"], "moment": moment_of(e["kind"]),
            "info_kind": e["kind"] in INFO_KINDS, "affects_route": affects_route(e["kind"], extra), "source_count": n,
            "confidence": "needs_confirmation" if e.get("needs_confirmation") else ("confirmed" if n >= 2 or e.get("confirmed_day") is not None else "single_source"),
            "confirmation_reason": e.get("confirmation_reason"),
            "first_day": e.get("first_day"), "last_day": e.get("last_day"), "confirmed_day": e.get("confirmed_day"),
            "temporary": bool(e.get("temporary")), "valid_until": e.get("ttl_until"), "window": e.get("window"),
            "source_list": e.get("source_list") or [e.get("source")]}


def _sort_cards(cards: list[dict]) -> list[dict]:
    """Önce yaklaşırken, sonra rotayı etkileyen, sonra çok kaynaklı."""
    return sorted(cards, key=lambda k: (MOMENT_ORDER[k["moment"]], not k["affects_route"], -k["source_count"], k["id"]))


class StopCards:
    """Kuryenin bugünkü (onaylı plan ya da simülasyon planı) rotası, hafızalı sırayla; her durağın geçerli kartları."""

    def __init__(self, run: RunData, book: MemoryBook, day: int, courier: str, plan: dict | None = None):
        book.ensure(day)
        self.run, self.book, self.day, self.courier = run, book, day, courier
        self.ar = BriefingTools(run, book, day, courier, plan)      # ValueError: kurye bugün planda/çalışmıyor
        self.extra = _routing_cfg(run)["extra"]
        self.stops = self._build()

    def _build(self) -> list[dict]:
        F, wd = self.ar.F, self.day % 6
        by_addr = {int(s[F["address"]]): s for s in self.ar.route["stops"]}
        hz = ((self.ar.route_result or {}).get("comparison") or {}).get("memory", {})
        order = [a for a in (hz.get("order") or list(by_addr)) if a in by_addr]
        eta = dict(zip(hz.get("order") or [], hz.get("expected_arrival") or []))
        out = []
        for i, a in enumerate(order):
            s = by_addr[a]
            t = float(eta.get(a, s[F["eta"]]))
            ok = [e for e in self.book.for_address(a, self.day) if hint_today_valid(e["kind"], wd, t, e.get("window"))]
            name = self.run.address(a)
            out.append({"order": i + 1, "address": a, "label": name["label"], "lat": name["lat"], "lng": name["lng"],
                        "expected_arrival": round(t, 1), "unfamiliar": bool(s[F["unfamiliar"]]), "shipment": int(s[F["n"]]),
                        "cards": _sort_cards([card_of(e, self.extra) for e in ok])})
        return out

    def items(self, include_all: bool = False) -> dict:
        with_cards = [d for d in self.stops if d["cards"]]
        dist_by_kind: dict[str, int] = {}
        for d in with_cards:
            for k in d["cards"]:
                dist_by_kind[k["type"]] = dist_by_kind.get(k["type"], 0) + 1
        return {"day": self.day, "weekday": self.run.weekday_name(self.day), "courier": self.courier,
                "name": self.run.courier_name(self.courier), "plan_source": self.ar.plan_source, "stop": len(self.stops),
                "stops_with_cards": len(with_cards), "cards": sum(len(d["cards"]) for d in with_cards), "type_distribution": dist_by_kind,
                "approach_m": APPROACH_M, "door_m": DOOR_M, "stops": self.stops if include_all else with_cards}

    def approach(self, lat: float, lng: float, next_order: int | None = None, shown: list[str] | None = None) -> dict:
        """Konuma göre şimdi söylenecek kartlar. `next_order` verilirse yalnız o durak (kurye uygulaması sıradaki durağı bilir);
        verilmezse yarıçap içindeki en yakın kartlı durak. `shown`: daha önce söylenmiş kart kimlikleri (tekrar söylenmez)."""
        seen = set(shown or [])
        dist = self.run.distances_m(lat, lng)
        if next_order is not None:
            if not (1 <= next_order <= len(self.stops)):
                raise ValueError(f"next_order 1–{len(self.stops)} arasında olmalı")
            candidate = [self.stops[next_order - 1]]
        else:
            candidate = [d for d in self.stops if d["cards"] and dist[d["address"]] <= APPROACH_M]
        candidate.sort(key=lambda d: dist[d["address"]])
        empty = {"day": self.day, "courier": self.courier, "stop": None, "moment": None, "cards": [], "to_speak": None, "pending": 0}
        if not candidate:
            return empty
        d = candidate[0]
        m = float(dist[d["address"]])
        stop = {k: d[k] for k in ("order", "address", "label", "lat", "lng", "expected_arrival", "unfamiliar")} | {"distance_m": round(m)}
        if m > APPROACH_M:
            return empty | {"stop": stop, "pending": sum(1 for k in d["cards"] if k["id"] not in seen)}
        moment = "at_door" if m <= DOOR_M else "approaching"
        eligible = [k for k in d["cards"] if k["id"] not in seen and (moment == "at_door" or k["moment"] == "approaching")]
        say = eligible[:SPEAK_MAX]
        return {"day": self.day, "courier": self.courier, "stop": stop, "moment": moment, "cards": say,
                "to_speak": " ".join(k["text"] for k in say) or None,
                "pending": sum(1 for k in d["cards"] if k["id"] not in seen) - len(say)}

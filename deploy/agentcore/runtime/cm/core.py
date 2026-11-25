"""Çekirdek araç takımı: alan kodu (`agents/`, `cm_sim/`) olmadan, yalnız veri dosyalarıyla çalışır.
Yalnız standart kütüphane kullanır. Tam takımdan farkı: rota hafızalı sıraya çevrilmez (simülasyon planının sırası),
brifing kısa şablondur, müdür araçları (plan, değerlendirme, bölge) yoktur. Kurallar aynıdır: kişisel veri ve kapı
şifresi kaydedilmez, bilgi türleri rotaya girmez, bir tetikte en çok iki kart.

Okunan dosyalar (`data/demo_run`): meta.json, couriers.json, addresses.json, memory/<gün>.json, snapshots/D/<gün>.json.
Oturumda bırakılan notlar geçici klasörde tutulur (CM_MEMORY_FILE).
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import threading
from pathlib import Path

APPROACH_M, DOOR_M, SPEAK_MAX, NOTE_RADIUS_M = 400, 60, 2, 80
LUNCH, LUNCH_HINT_BEFORE, SATURDAY = (720, 810), 60, 5       # öğle penceresi (dk), uyarı payı, haftagünü (0 = Pzt … 5 = Cmt)

QUIRK_KINDS = ("back_entry", "saturday_closed", "lunch_break", "safety", "bell", "position_wrong", "reception",
               "temporary_closed", "roadwork")
INFO_KINDS = ("park", "building_access", "directions", "animal", "other_info")
APPROACH_KINDS = ("park", "directions", "position_wrong", "roadwork", "back_entry")
TITLE = {"back_entry": "Arka giriş", "saturday_closed": "Cumartesi kapalı", "lunch_break": "Öğle arası", "safety": "Güvenlik",
         "bell": "Zil", "position_wrong": "Konum hatalı", "reception": "Resepsiyon", "temporary_closed": "Geçici kapalı",
         "roadwork": "Yol çalışması", "park": "Park", "building_access": "Bina erişimi", "directions": "Adres tarifi",
         "animal": "Hayvan", "other_info": "Not"}
CANON = {"back_entry": "Giriş arka sokaktan; ön kapı kullanılmıyor.", "saturday_closed": "Cumartesi kapalı.",
         "lunch_break": "12:00–13:30 arası öğle arası; kapı açılmıyor.",
         "safety": "Site güvenliğinde kimlik/kart işlemi var; birkaç dakika sürüyor.",
         "bell": "Zil çalışmıyor; alıcıyı telefonla arayın.", "position_wrong": "Haritadaki konum hatalı; bina yakın sokakta.",
         "reception": "Gönderiler resepsiyona teslim ediliyor.", "temporary_closed": "Geçici olarak kapalı (tadilat).",
         "roadwork": "Sokakta yol çalışması var; yakına park edip yürüyün."}
KEYWORDS = {"roadwork": ["yol çalışması", "yol calismasi", "kazı", "yol kapalı", "sokak kapalı", "sokağa girilmiyo"],
            "temporary_closed": ["tadilat", "geçici", "bu hafta kapalı"], "saturday_closed": ["cumartesi", "cmt", "hafta sonu"],
            "lunch_break": ["öğle", "öğlen", "12 ile", "12den", "1.5"], "safety": ["güvenlik", "kart istiyo", "kimlik", "kayıt yaptır"],
            "bell": ["zil"], "position_wrong": ["konum", "harita", "navigasyon", "yanlış yere", "ileride", "sonraki sokakta"],
            "reception": ["resepsiyon", "danışma"], "back_entry": ["arka", "ön kapı", "önden"]}
INFO_KEYWORDS = {"park": ["park et", "park ed", "park yeri", "park yok", "park alan", "otopark", "arabayı", "arabayi", "araç girm",
                          "arac girm", "araçla gir", "aracla gir"],
                 "building_access": ["asansör", "asansor", "merdiven", "rampa", "basamak", "katta", "kata çık", "kata cik", "bodrum"],
                 "directions": ["eczane", "tabela", "numara yok", "numarası yok", "kapı numarası", "boyalı bina", "renkli bina"],
                 "animal": ["köpek", "kopek", "kedi"]}

PHONE = re.compile(r"(\+?90[\s-]?)?0?\s?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
HONORIFIC_NAME = re.compile(r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]+)\s+(hanım|hanim|bey|abla|abi|teyze|amca)\b", re.IGNORECASE)
JUDGEMENT = re.compile(r"\b(huysuz|tuhaf|deli|kaba|sinirli|yaşlı|yasli|hasta|engelli|sarhoş|sarhos|garip|cimri|hamile|yatalak)\b",
                       re.IGNORECASE)
SECRET = re.compile(r"(şifre|sifre|parola|kap[ıi] kodu|giri[şs] kodu|alarm kodu|bina kodu|\bpin\b|\bkod(?:u|unu)?\s*[:=]?\s*\d{3,})",
                    re.IGNORECASE)


def find_sensitive(text: str) -> list[str]:
    """Kişisel veri (telefon, hitaplı ad, kişisel yargı) ve güvenlik bilgisi (şifre, kod) parçaları."""
    return [m.group(0).strip() for rx in (PHONE, HONORIFIC_NAME, JUDGEMENT, SECRET) for m in rx.finditer(text or "")]


def clean_text(text: str) -> str:
    """Notu hafızaya yazılabilir tek cümleye indirir: hassas parça geçen bölüm tümden atılır, en çok 140 karakter."""
    t = re.sub(r"(\d)\.(?=\s*\w)", "\\1\u2024", text or "")           # "4. kat": nokta cümle ayırıcı sayılmasın
    t = HONORIFIC_NAME.sub("", PHONE.sub("", t))
    parts = [p.strip() for p in re.split(r"[,.;]", t)]
    keep = [p for p in parts if p and not (JUDGEMENT.search(p) or SECRET.search(p))]
    t = re.sub(r"\s+", " ", ", ".join(keep)).replace("\u2024", ".").strip(" ,.;")
    if len(t) > 138:
        t = t[:138].rsplit(" ", 1)[0].rstrip(" ,;")
    return (t[:1].upper() + t[1:] + ".") if t else ""


def classify(text: str) -> str | None:
    """Rotayı etkileyen tür önceliklidir; bilgi türü yalnız açıkça daha çok eşleşirse seçilir. Eşleşme yoksa None (gürültü)."""
    t = (text or "").lower()

    def best(table):
        scored = [(sum(1 for k in kws if k in t), kind) for kind, kws in table.items()]
        s, kind = max(scored, key=lambda x: x[0])
        return (kind, s) if s else (None, 0)

    q, qs = best(KEYWORDS)
    b, bs = best(INFO_KEYWORDS)
    return b if bs > qs else q


def hint_valid_now(kind: str, weekday: int, eta: float, window=None) -> bool:
    """Kart bugün ve bu varış saatinde anlamlı mı: Çarşamba günü "Cumartesi kapalı" söylenmez, öğle uyarısı yalnız öğleye yakınsa."""
    if kind == "saturday_closed":
        return weekday == SATURDAY
    if kind == "lunch_break":
        lo, hi = window or LUNCH
        return lo - LUNCH_HINT_BEFORE <= eta < hi
    return True


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    kx = 111320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lat1 - lat2) * 110574.0, (lng1 - lng2) * kx)


def _find_data_dir() -> Path:
    env = os.environ.get("CM_RUN_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for base in here.parents:                                        # app/agent/data/demo_run ya da repo/data/demo_run
        p = base / "data" / "demo_run"
        if (p / "meta.json").exists():
            return p
    raise FileNotFoundError("data/demo_run bulunamadı; CM_RUN_DIR verin.")


class CoreStore:
    def __init__(self, data_dir: str | Path | None = None, notes_file: str | Path | None = None):
        self.dir = Path(data_dir) if data_dir else _find_data_dir()
        self.meta = self._load("meta.json")
        self.couriers = {c["id"]: c for c in self._load("couriers.json")["couriers"]}
        self.addresses = {int(r[0]): r for r in self._load("addresses.json")["addresses"]}     # [id, lat, lng, kind, block, label]
        self.F = {k: i for i, k in enumerate(self.meta["stop_fields"])}
        self.notes_path = Path(notes_file or os.environ.get("CM_MEMORY_FILE")
                               or Path(tempfile.gettempdir()) / "cm" / "core_notes.json")
        self._lock = threading.Lock()
        self._seed: dict[int, list[dict]] = {}
        self._notes: list[dict] = self._read_notes()

    # ------------------------------------------------------------------ veri
    def _load(self, rel: str):
        return json.loads((self.dir / rel).read_text(encoding="utf-8"))

    def _read_notes(self) -> list[dict]:
        try:
            return json.loads(self.notes_path.read_text(encoding="utf-8")).get("core_notes", [])
        except (OSError, ValueError, AttributeError):
            return []

    def _write_notes(self) -> None:
        self.notes_path.parent.mkdir(parents=True, exist_ok=True)
        self.notes_path.write_text(json.dumps({"core_notes": self._notes}, ensure_ascii=False), encoding="utf-8")

    @property
    def default_day(self) -> int:
        return int(self.meta["critical"]["day"])

    @property
    def eval_days(self) -> list[int]:
        return self.meta["eval_days"]

    def courier_name(self, cid: str) -> str:
        return self.couriers.get(cid, {}).get("name", cid)

    def _entries(self, day: int) -> list[dict]:
        if day not in self._seed:
            p = self.dir / "memory" / f"{day}.json"
            self._seed[day] = json.loads(p.read_text(encoding="utf-8"))["entries"] if p.exists() else []
        return self._seed[day] + [n for n in self._notes if n["day"] <= day]

    def _by_address(self, day: int) -> dict[int, list[dict]]:
        out: dict[int, list[dict]] = {}
        for e in self._entries(day):
            if e.get("ttl_until") is None or day <= e["ttl_until"]:
                out.setdefault(int(e["address"]), []).append(e)
        return out

    def _route(self, courier: str, day: int) -> dict:
        if courier not in self.couriers:
            raise ValueError(f"Bilinmeyen kurye: {courier}")
        snap = self._load(f"snapshots/D/{day}.json")
        r = next((x for x in snap["routes"] if x["courier"] == courier), None)
        if r is None:
            raise ValueError(f"{courier} gün {day} çalışmıyor")
        return r

    @staticmethod
    def _card(e: dict) -> dict:
        n = int(e.get("sources", 1))
        return {"id": e["id"], "type": e["kind"], "title": TITLE.get(e["kind"], e["kind"]), "text": e["text"],
                "moment": "approaching" if e["kind"] in APPROACH_KINDS else "at_door", "info_kind": e["kind"] in INFO_KINDS,
                "source_count": n, "confidence": "confirmed" if n >= 2 else "single_source"}

    def _stops(self, courier: str, day: int) -> list[dict]:
        F, mem = self.F, self._by_address(day)
        out = []
        for i, s in enumerate(self._route(courier, day)["stops"]):
            a = int(s[F["address"]])
            valid = [e for e in mem.get(a, []) if hint_valid_now(e["kind"], day % 6, float(s[F["eta"]]), e.get("window"))]
            cards = sorted((self._card(e) for e in valid), key=lambda c: (c["moment"] != "approaching", -c["source_count"], c["id"]))
            out.append({"order": i + 1, "address": a, "label": self.addresses[a][5], "lat": s[F["lat"]], "lng": s[F["lng"]],
                        "shipment": int(s[F["n"]]), "unfamiliar": bool(s[F["unfamiliar"]]), "cards": cards})
        return out

    # ------------------------------------------------------------------ araçların çağırdığı işlevler
    def briefing(self, courier: str, day: int) -> dict:
        st = self._stops(courier, day)
        unf = [x for x in st if x["unfamiliar"]]
        with_cards = [x for x in unf if x["cards"]]
        name = self.courier_name(courier)
        text = (f"Günaydın {name}. Bugün {len(st)} durak, {sum(x['shipment'] for x in st)} gönderi var. "
                f"{len(unf)} durakta bölgeyi ilk kez görüyorsun; bunların {len(with_cards)} tanesinde hafızada not var, "
                f"kapıya yaklaşınca söyleyeceğim.")
        return {"day": day, "courier": courier, "name": name, "type": self.couriers[courier].get("kind"), "morning_briefing": text,
                "stops": len(st), "unfamiliar_stops": len(unf), "unfamiliar_with_cards": len(with_cards),
                "door_sentences": [{"order": x["order"], "sentence": x["cards"][0]["text"]} for x in st if x["cards"]][:12],
                "plan_source": "simulation_plan", "toolset": "core"}

    def stop_cards(self, courier: str, day: int) -> dict:
        st = self._stops(courier, day)
        with_cards = [x for x in st if x["cards"]]
        dist: dict[str, int] = {}
        for x in with_cards:
            for c in x["cards"]:
                dist[c["type"]] = dist.get(c["type"], 0) + 1
        return {"day": day, "courier": courier, "stops": len(st), "stops_with_cards": len(with_cards), "type_distribution": dist,
                "cards": [{k: x[k] for k in ("order", "label", "lat", "lng", "cards")} for x in with_cards][:20]}

    def approach(self, courier: str, day: int, lat: float, lng: float, next_order: int | None = None,
                 shown: list[str] | None = None) -> dict:
        st, seen = self._stops(courier, day), set(shown or [])
        if next_order is not None:
            if not (1 <= next_order <= len(st)):
                raise ValueError(f"next_order 1–{len(st)} arasında olmalı")
            cand = [st[next_order - 1]]
        else:
            cand = [x for x in st if x["cards"] and distance_m(lat, lng, x["lat"], x["lng"]) <= APPROACH_M]
        cand.sort(key=lambda x: distance_m(lat, lng, x["lat"], x["lng"]))
        empty = {"moment": None, "to_speak": None, "pending": 0, "stop": None, "cards": []}
        if not cand:
            return empty
        x = cand[0]
        m = distance_m(lat, lng, x["lat"], x["lng"])
        stop = {"order": x["order"], "label": x["label"], "distance_m": round(m)}
        left = [c for c in x["cards"] if c["id"] not in seen]
        if m > APPROACH_M:
            return empty | {"stop": stop, "pending": len(left)}
        moment = "at_door" if m <= DOOR_M else "approaching"
        say = [c for c in left if moment == "at_door" or c["moment"] == "approaching"][:SPEAK_MAX]
        return {"moment": moment, "to_speak": " ".join(c["text"] for c in say) or None, "pending": len(left) - len(say), "stop": stop,
                "cards": [{"id": c["id"], "title": c["title"], "text": c["text"]} for c in say]}

    def leave_note(self, courier: str, day: int, text: str, lat: float | None = None, lng: float | None = None) -> dict:
        sensitive = find_sensitive(text)
        kind = classify(text)
        base = {"type": kind, "hint": None, "personal_data_redacted": bool(sensitive), "question": None, "address": None, "record": None}
        if kind is None:
            return base | {"status": "noise", "summary": "Not bir adresin püf noktasını anlatmıyor; hafızaya yazılmadı."}
        st = self._stops(courier, day)
        near = sorted(((distance_m(lat, lng, x["lat"], x["lng"]), x) for x in st), key=lambda t: t[0]) if lat is not None and lng is not None else []
        if not near or near[0][0] > NOTE_RADIUS_M:
            return base | {"status": "uncertain", "summary": "Not hangi adrese ait, emin olamadım; kuryeye soruldu.",
                           "question": "Bu notu hangi teslimat için bıraktınız? Durak sırasını söyler misiniz?"}
        stop = near[0][1]
        hint = clean_text(text) if kind in INFO_KINDS else CANON[kind]
        if not hint or find_sensitive(hint):
            return base | {"status": "rejected", "summary": "Not temizlendikten sonra kaydedilecek bilgi kalmadı."}
        with self._lock:
            old = next((n for n in self._notes if n["address"] == stop["address"] and n["kind"] == kind), None)
            if old:
                old["sources"] = int(old.get("sources", 1)) + 1
                old["last_day"] = day
                rec, status = old, "updated"
            else:
                rec = {"id": f"C{len(self._notes) + 1:05d}", "address": stop["address"], "kind": kind, "text": hint, "sources": 1,
                       "first_day": day, "last_day": day, "day": day, "ttl_until": None, "source": "agent"}
                self._notes.append(rec)
                status = "saved"
            self._write_notes()
        summary = "Not adrese bağlandı" + ("; kişisel bilgi ya da şifre ayıklandı ve kaydedilmedi." if sensitive else ".")
        if kind in INFO_KINDS:
            summary += " Bilgi kartı olarak gösterilir; rotayı değiştirmez."
        return base | {"status": status, "hint": rec["text"], "summary": summary, "address": stop["label"], "record": rec["id"]}

    def memory_summary(self, day: int) -> dict:
        es = [e for v in self._by_address(day).values() for e in v]
        dist: dict[str, int] = {}
        for e in es:
            dist[e["kind"]] = dist.get(e["kind"], 0) + 1
        return {"day": day, "active_records": len(es), "type_distribution": dict(sorted(dist.items(), key=lambda kv: -kv[1])),
                "latest": [{"kind": n["kind"], "text": n["text"]} for n in self._notes[-5:]][::-1]}

    def real_day_evidence(self) -> dict:
        p = self.dir.parent / "real_day" / "2026-05-05.json"
        if not p.exists():
            raise ValueError("Gerçek gün verisi bu dağıtımda yok (data/real_day).")
        g = json.loads(p.read_text(encoding="utf-8"))
        s = g["summary"]
        return {"day": g["day"], "stops": s["stop"], "shipments": s["shipment"], "couriers_fixed": len(g["couriers"]),
                "clusters_dynamic": len(g["clusters"]), "fail_rate_familiar": g["rates"]["fail_familiar"],
                "fail_rate_unfamiliar": g["rates"]["fail_unfamiliar"], "unfamiliar_share_history_aware": s["unfamiliar_share"],
                "unfamiliar_share_history_blind": s["unfamiliar_share_history_blind"], "source": g["rates"]["source"]}

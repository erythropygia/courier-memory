"""Hafıza Ajanı: kurye notunu adrese bağlar, türünü çıkarır, kişisel veriyi ayıklar, hafızayı günceller."""
from __future__ import annotations

import re
from pathlib import Path

from .guardrails import find_pii, find_secret, redact, redact_secret
from .llm import LLM, AgentError, Tool, nullable, obj
from .memorybook import CANON, MemoryBook, MemoryWriteError
from .rundata import INFO_KINDS, MEMORY_KINDS, RunData, parse_waybill
from .tr import hhmm

PROMPT = (Path(__file__).parent / "prompts" / "memory.md").read_text(encoding="utf-8")

KEYWORDS: dict[str, list[str]] = {
    "roadwork": ["yol çalışması", "yol calismasi", "kazı", "yol kapalı", "sokak kapalı", "sokağa girilmiyo"],
    "temporary_closed": ["tadilat", "geçici", "bu hafta kapalı"],
    "saturday_closed": ["cumartesi", "cmt", "hafta sonu"],
    "lunch_break": ["öğle", "öğlen", "12 ile", "12den", "1.5"],
    "safety": ["güvenlik", "kart istiyo", "kimlik", "kayıt yaptır"],
    "bell": ["zil"],
    "position_wrong": ["konum", "harita", "navigasyon", "yanlış yere", "ileride", "sonraki sokakta"],
    "reception": ["resepsiyon", "danışma"],
    "back_entry": ["arka", "ön kapı", "önden"],
}
# yalnız bilgi taşıyan türler (rotaya girmez). Rotayı etkileyen türlerden açıkça daha çok eşleşirse seçilir; böylece
# simülatör notlarının sınıflandırması değişmez ("parkın yanındaki apartman, …" gibi belirsiz önekler park sayılmaz).
INFO_KEYWORDS: dict[str, list[str]] = {
    "park": ["park et", "park ed", "park yeri", "park yok", "park alan", "otopark", "arabayı", "arabayi", "araç girm", "arac girm",
             "araçla gir", "aracla gir", "araç sığmıyo", "arac sigmiyo"],
    "building_access": ["asansör", "asansor", "merdiven", "rampa", "basamak", "katta", "kata çık", "kata cik", "en üst kat", "en ust kat",
                        "çatı katı", "cati kati", "bodrum"],
    "directions": ["eczane", "tabela", "numara yok", "numarası yok", "numarasi yok", "kapı numarası", "kapi numarasi",
                   "boyalı bina", "boyali bina", "renkli bina", "renkli kapı", "renkli kapi"],
    "animal": ["köpek", "kopek", "kedi"],
}
STATES = ("saved", "updated", "noise", "uncertain", "rejected")


_T = r"(\d{1,2})(?:[:.,](\d{1,2}))?"
_WINDOW = re.compile(_T + r"\s*(?:'?(?:den|dan|ten|tan))?\s*(?:ile|-|–|—|ila|ve)\s*" + _T)


def parse_window(text: str) -> list[int] | None:
    """Serbest metinden kapalı penceresi: "12 ile 1.5 arası" → [720, 810], "12:30-14:00" → [750, 840]. Bulamazsa None.
    Öğleden sonra saatleri 1–7 yazılırsa +12 sayılır; "1.5" yarım saat demektir."""
    m = _WINDOW.search(text.lower())
    if not m:
        return None

    def tok(h: str, mm: str | None) -> int:
        hv = int(h)
        if mm is None:
            mv = 0
        elif len(mm) == 1:               # 1.5 → bir buçuk
            mv = int(mm) * 6
        else:
            mv = int(mm)
        if hv < 8:
            hv += 12
        return hv * 60 + mv

    a, b = tok(m.group(1), m.group(2)), tok(m.group(3), m.group(4))
    if not (600 <= a < b <= 1080) or b - a > 240:
        return None
    return [a, b]


def _best(t: str, table: dict[str, list[str]]) -> tuple[str | None, int]:
    best, score = None, 0
    for kind, kws in table.items():
        s = sum(1 for k in kws if k in t)
        if s > score:
            best, score = kind, s
    return best, score


def classify(text: str) -> str | None:
    """Kurallı yedek: rotayı etkileyen türler önceliklidir; bilgi türü yalnız açıkça daha çok eşleşirse kazanır
    ("arabayı arka sokağa park edin" → park; "kazı var, aşağıya park et" → roadwork)."""
    t = text.lower()
    q, qs = _best(t, KEYWORDS)
    b, bs = _best(t, INFO_KEYWORDS)
    return b if bs > qs else q


def info_text(text: str) -> str:
    """Kurallı yedekte bilgi türünün ipucu metni: notun kendisi, kişisel veri ve şifre ayıklanmış, tek cümle, ≤ 140 karakter.
    Canlı modda bu cümleyi model yazar; yedek yalnız temizler."""
    t = re.sub(r"(\d)\.(?=\s*\w)", "\\1\u2024", text)        # "5. kat" sıra sayısı: temizleyiciler noktadan bölmesin
    t = redact_secret(redact(t)).replace("\u2024", ".")
    t = re.sub(r"\s+", " ", t).strip(" ,.;")
    if len(t) > 138:
        t = t[:138].rsplit(" ", 1)[0].rstrip(" ,;")
    return (t[:1].upper() + t[1:] + ".") if t else ""


class MemoryTools:
    def __init__(self, run: RunData, book: MemoryBook, day: int, courier: str):
        self.run, self.book, self.day, self.courier = run, book, day, courier
        r = run.route_of(day, courier)
        self.route_stops = {int(s[0]): (i, s[4]) for i, s in enumerate(r["stops"])} if r else {}
        self.note_id: str | None = None
        self.source = "agent"

    def query_barcode(self, inp: dict) -> dict:
        p = parse_waybill(inp["barcode"])
        if not p:
            raise ValueError("Barkod biçimi geçersiz (beklenen: SN + 9 hane)")
        _, a, _ = p
        if not (0 <= a < len(self.run.addr_kind)):
            raise ValueError("Barkoddaki adres bulunamadı")
        return {**self.run.address(a), "today_courier_stop": a in self.route_stops}

    def near_addresses(self, inp: dict) -> dict:
        rad = float(inp.get("radius_m") or 80)
        out = []
        for a, d in self.run.nearest(float(inp["lat"]), float(inp["lng"]), radius_m=min(rad, 300), limit=10):
            on_route = a in self.route_stops
            out.append({**self.run.address(a), "distance_m": round(d), "today_courier_stop": on_route,
                        "arrival": hhmm(self.route_stops[a][1]) if on_route else None})
        out.sort(key=lambda x: (not x["today_courier_stop"], x["distance_m"]))
        return {"addresses": out[:6]}

    def address_memory(self, inp: dict) -> dict:
        a = int(inp["address_id"])
        return {"address": self.run.address(a), "records": [
            {"id": e["id"], "type": e["kind"], "text": e["text"], "source_count": e["sources"], "last_day": e["last_day"]}
            for e in self.book.for_address(a, self.day)]}

    def write_memory(self, inp: dict) -> dict:
        e, new = self.book.upsert(address=int(inp["address_id"]), kind=inp["type"], text=inp["hint"], day=self.day,
                                  note_id=self.note_id, source=self.source, window=inp.get("window"))
        return {"record": e["id"], "is_new": new, "source_count": e["sources"]}

    def drop_record(self, inp: dict) -> dict:
        ok = self.book.drop(inp["record_id"], self.day, inp.get("rationale") or "")
        if not ok:
            raise ValueError("Kayıt bulunamadı")
        return {"dropped": inp["record_id"]}


class MemoryAgent:
    def __init__(self, run: RunData, book: MemoryBook, llm: LLM):
        self.run, self.book, self.llm = run, book, llm

    def _tools(self, ar: MemoryTools) -> list[Tool]:
        return [
            Tool("query_barcode", "Barkoddan adresi bulur.", obj({"barcode": {"type": "string"}}), ar.query_barcode,
                 lambda i, r: f"{r['label']}"),
            Tool("near_addresses", "GPS'e yakın adresler; kuryenin bugünkü durakları önce gelir.",
                 obj({"lat": {"type": "number"}, "lng": {"type": "number"}, "radius_m": {"type": "number"}}),
                 ar.near_addresses, lambda i, r: f"{len(r['addresses'])} aday adres"),
            Tool("address_memory", "Bir adresin hafızadaki mevcut kayıtları.", obj({"address_id": {"type": "integer"}}),
                 ar.address_memory, lambda i, r: f"{len(r['records'])} kayıt"),
            Tool("write_memory", "Adrese ipucu yazar ya da var olan kaydı güçlendirir. Kişisel veri içeren metni reddeder.",
                 obj({"address_id": {"type": "integer"}, "type": {"type": "string", "enum": list(MEMORY_KINDS)},
                      "hint": {"type": "string"},
                      "window": nullable({"type": "array", "items": {"type": "integer"}})}), ar.write_memory,
                 lambda i, r: f"{r['record']} ({'yeni' if r['is_new'] else 'güçlendi'})"),
            Tool("drop_record", "Çelişen ya da eskimiş bir kaydı hafızadan düşürür.",
                 obj({"record_id": {"type": "string"}, "rationale": {"type": "string"}}), ar.drop_record,
                 lambda i, r: f"{r['dropped']} düşürüldü"),
            Tool("report_result", "Notun işlenme sonucunu bildirir (son adım).",
                 obj({"status": {"type": "string", "enum": list(STATES)},
                      "address_id": nullable({"type": "integer"}), "type": nullable({"type": "string", "enum": list(MEMORY_KINDS)}),
                      "hint": nullable({"type": "string"}), "personal_data_redacted": {"type": "boolean"},
                      "summary": {"type": "string"}, "question": nullable({"type": "string"})})),
        ]

    def process(self, day: int, courier: str, note_text: str, lat: float | None = None, lng: float | None = None,
             barcode: str | None = None, minute: int | None = None, note_id: str | None = None,
             address_id: int | None = None, source: str = "agent") -> dict:
        """address_id: adres önceden belli (hasat sorusunun cevabı); kaynak: kaydın kaynağı (ajan | hasat)."""
        self.book.ensure(day)
        ar = MemoryTools(self.run, self.book, day, courier)
        ar.note_id = note_id
        ar.source = source
        if self.llm.uses_llm:
            try:
                ctx = (f"Bu not bir hasat sorusunun cevabıdır; adres belli: {address_id} ({self.run.addr_label[address_id]}). Adresi arama, "
                       f"bu adresi kullan.\n") if address_id is not None else ""
                user = (f"Yeni kurye notu.\n{ctx}Gün: {day} ({self.run.weekday_name(day)}), saat: {hhmm(minute) if minute else 'bilinmiyor'}\n"
                        f"Kurye: {courier} ({self.run.courier_name(courier)})\nGPS: {lat}, {lng}\nBarkod: {barcode or 'yok'}\n"
                        f"Not metni: \"{note_text}\"")
                run = self.llm.run_agent(agent="memory", system=PROMPT, user=user, tools=self._tools(ar),
                                         finish_tool="report_result", effort="medium")
                fi = run.final_input or {}
                if fi.get("status") not in STATES:
                    raise AgentError("Ajan sonucu bildirmedi")
                return self._result(ar, fi, run.steps, degraded=False)
            except Exception as e:
                res = self._mock(ar, note_text, lat, lng, barcode, address_id)
                res.update(degraded=True, error=str(e))
                return res
        return self._mock(ar, note_text, lat, lng, barcode, address_id)

    def _result(self, ar: MemoryTools, fi: dict, steps: list[dict], degraded: bool) -> dict:
        a = fi.get("address_id")
        record = None
        if a is not None and fi.get("type"):
            es = [e for e in self.book.for_address(int(a), ar.day) if e["kind"] == fi["type"]]
            if es:
                record = {"id": es[0]["id"], "sources": es[0]["sources"]}
        return {"status": fi["status"], "address": self.run.address(int(a)) if a is not None else None, "type": fi.get("type"),
                "hint": fi.get("hint"), "record": record, "personal_data_redacted": bool(fi.get("personal_data_redacted")),
                "summary": fi.get("summary", ""), "question": fi.get("question"), "mode": self.llm.mode, "degraded": degraded, "steps": steps}

    def _mock(self, ar: MemoryTools, note_text: str, lat, lng, barcode, address_id: int | None = None) -> dict:
        steps: list[dict] = []
        pii = find_pii(note_text) + find_secret(note_text)
        kind = classify(note_text)
        if kind is None:
            return self._result(ar, {"status": "noise", "address_id": address_id, "type": None, "hint": None,
                                     "personal_data_redacted": bool(pii),
                                     "summary": "Not bir adresin püf noktasını anlatmıyor; hafızaya yazılmadı."}, steps, False)
        addr = int(address_id) if address_id is not None else None
        if barcode:
            try:
                r = ar.query_barcode({"barcode": barcode})
                addr = r["id"]
                steps.append({"tool": "query_barcode", "input": {"barcode": barcode}, "summary": r["label"]})
            except ValueError as e:
                steps.append({"tool": "query_barcode", "input": {"barcode": barcode}, "summary": f"hata: {e}"})
        ambiguous = bool(re.search(r"\b(şu|bu|oradaki|yanındaki)\b", note_text.lower())) and not barcode
        if addr is None and lat is not None and lng is not None and not barcode:
            r = ar.near_addresses({"lat": lat, "lng": lng, "radius_m": 80})
            steps.append({"tool": "near_addresses", "input": {"lat": lat, "lng": lng, "radius_m": 80}, "summary": f"{len(r['addresses'])} aday"})
            on_route = [x for x in r["addresses"] if x["today_courier_stop"]]
            if on_route and not (ambiguous and len(on_route) > 1 and on_route[1]["distance_m"] - on_route[0]["distance_m"] < 15):
                addr = on_route[0]["id"]
        if addr is None:
            return self._result(ar, {"status": "uncertain", "address_id": None, "type": kind, "hint": None,
                                     "personal_data_redacted": bool(pii),
                                     "summary": "Not hangi adrese ait, emin olamadım; kuryeye soruldu.",
                                     "question": "Bu notu hangi teslimat için bıraktınız? Barkodu okutur musunuz?"}, steps, False)
        text = info_text(note_text) if kind in INFO_KINDS else CANON[kind]
        pen = parse_window(note_text) if kind == "lunch_break" else None
        if pen and pen != [720, 810]:
            text = f"{hhmm(pen[0])}–{hhmm(pen[1])} arası kapalı; kapı açılmıyor."
        try:
            w = ar.write_memory({"address_id": addr, "type": kind, "hint": text, "window": pen})
        except MemoryWriteError as e:
            return self._result(ar, {"status": "rejected", "address_id": addr, "type": kind, "hint": None,
                                     "personal_data_redacted": bool(pii), "summary": str(e)}, steps, False)
        steps.append({"tool": "write_memory", "input": {"address_id": addr, "type": kind, "hint": text, "window": pen},
                      "summary": f"{w['record']} ({'yeni' if w['is_new'] else 'güçlendi'})"})
        summary = "Not adrese bağlandı" + ("; kişisel bilgi ya da şifre ayıklandı ve kaydedilmedi." if pii else ".")
        if kind in INFO_KINDS:
            summary += " Bilgi kartı olarak gösterilir; rotayı değiştirmez."
        return self._result(ar, {"status": "saved" if w["is_new"] else "updated", "address_id": addr, "type": kind,
                                 "hint": text, "personal_data_redacted": bool(pii), "summary": summary}, steps, False)

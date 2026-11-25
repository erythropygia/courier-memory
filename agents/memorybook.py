"""Canlı adres hafızası (demo oturumu). Depo: JSON dosyası (CM_STORAGE=file, varsayılan) ya da DynamoDB
(CM_STORAGE=dynamodb); arayüz aynıdır, depolar agents/storage altındadır.

Bir günün D kolu hafızasından tohumlanır; Hafıza Ajanı yazar, Brifing Ajanı okur, kurye geri bildirimi günceller.
İş kuralları burada saf fonksiyonlardır (durum → değişiklik); depo değişikliği atomik işler (DynamoDB'de
eşzamanlı yazımda kural taze durumla yeniden çalışır).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from .guardrails import find_pii, find_secret
from .rundata import INFO_KINDS, MEMORY_KINDS, ROOT, RunData
from .storage import MemoryState, Mutation, memory_repository
from .storage.base import MemoryRepository

TEMPORARY = ("temporary_closed", "roadwork")
TTL_DAYS = 10
CANON = {
    "back_entry": "Giriş arka sokaktan; ön kapı kullanılmıyor.",
    "saturday_closed": "Cumartesi kapalı.",
    "lunch_break": "12:00–13:30 arası öğle arası; kapı açılmıyor.",
    "safety": "Site güvenliğinde kimlik/kart işlemi var; birkaç dakika sürüyor.",
    "bell": "Zil çalışmıyor; alıcıyı telefonla arayın.",
    "position_wrong": "Haritadaki konum hatalı; bina yakın sokakta.",
    "reception": "Gönderiler resepsiyona teslim ediliyor.",
    "temporary_closed": "Geçici olarak kapalı (tadilat).",
    "roadwork": "Sokakta yol çalışması var; yakına park edip yürüyün.",
}
UNDO_FIELDS = ("dropped_day", "drop_reason", "needs_confirmation", "confirmation_reason")


class MemoryWriteError(ValueError):
    pass


def _active(e: dict) -> bool:
    return e.get("status", "active") == "active"


def _alive(e: dict, day: int) -> bool:
    return _active(e) and (e.get("ttl_until") is None or day <= e["ttl_until"])


def _entry(state: MemoryState, entry_id: str) -> dict | None:
    return state.find(entry_id)


# ------------------------------------------------------------------ doğrulama (yazımdan önce, depoya gitmeden)
def _check_window(kind: str, window: list[int] | None) -> list[int] | None:
    if window is None:
        return None
    if kind != "lunch_break" or len(window) != 2 or not (360 <= int(window[0]) < int(window[1]) <= 1200):
        raise MemoryWriteError("pencere yalnız lunch_break için, [başlangıç, bitiş] dakika (06:00–20:00) olmalı")
    return [int(window[0]), int(window[1])]


def _check_text(kind: str, text: str | None) -> str:
    if kind not in MEMORY_KINDS:
        raise MemoryWriteError(f"Bilinmeyen tür: {kind}. İzinli: {', '.join(MEMORY_KINDS)}")
    text = (text or "").strip()
    if not text:
        if kind in INFO_KINDS:      # bilgi türünün kalıp cümlesi yok: bilginin kendisi metindir
            raise MemoryWriteError(f"{kind} türü için ipucu metni gerekli (ör. nereye park edileceği).")
        text = CANON[kind]
    if len(text) > 140:
        raise MemoryWriteError("İpucu metni 140 karakteri geçmemeli; tek cümle olmalı.")
    pii = find_pii(text)
    if pii:
        raise MemoryWriteError(f"Metin kişisel veri içeriyor ({', '.join(pii)}). Kişiyi değil adresi anlatan nötr bir cümleyle yeniden yaz.")
    if find_secret(text):
        raise MemoryWriteError("Metin kapı/bina şifresi ya da giriş kodu içeriyor; şifre hafızaya yazılmaz. Şifreyi çıkarıp yeniden yaz.")
    return text


# ------------------------------------------------------------------ iş kuralları: durum → değişiklik (saf)
def _strengthen(e: dict, *, text: str, day: int, note_id: str | None, source: str, window: list[int] | None) -> dict:
    new = {**e, "sources": e["sources"] + 1, "last_day": day, "text": text, "updated_at": time.time()}
    if e["kind"] in TEMPORARY:
        new["ttl_until"] = day + TTL_DAYS
    if note_id:
        new["note_ids"] = [*e.get("note_ids", []), note_id]
    if window is not None:
        new["window"] = window
    known = e.get("source_list") or [e.get("source")]
    if source not in known:
        new["source_list"] = [*known, source]
    return new


def _new_entry(state: MemoryState, *, address: int, kind: str, text: str, day: int, note_id: str | None,
               source: str, window: list[int] | None) -> dict:
    n = 1 + max([int(x["id"][1:]) for x in state.entries if x["id"][1:].isdigit()] + [0])
    e = {"id": f"M{n:05d}", "address": address, "kind": kind, "text": text, "sources": 1,
         "first_day": day, "last_day": day, "temporary": kind in TEMPORARY,
         "ttl_until": day + TTL_DAYS if kind in TEMPORARY else None, "status": "active",
         "source": source, "note_ids": [note_id] if note_id else [], "updated_at": time.time()}
    return {**e, "window": window} if window is not None else e


def _upsert(state: MemoryState, **kw) -> Mutation:
    address, kind, day = kw["address"], kw["kind"], kw["day"]
    current = next((e for e in state.entries if e["address"] == address and e["kind"] == kind and _active(e)), None)
    if current is not None:
        e = _strengthen(current, **{k: kw[k] for k in ("text", "day", "note_id", "source", "window")})
        return Mutation(entry=e, log={"operation": "updated", "record": e["id"], "day": day})
    e = _new_entry(state, **kw)
    return Mutation(entry=e, log={"operation": "added", "record": e["id"], "day": day}, created=True)


def _feedback(state: MemoryState, entry_id: str, valid: bool, day: int) -> Mutation | None:
    e = _entry(state, entry_id)
    if e is None:
        return None
    if valid:
        new = {**e, "sources": e["sources"] + 1, "last_day": day, "confirmed_day": day}
    else:
        new = {**e, "status": "dropped", "dropped_day": day}
    return Mutation(entry=new, log={"operation": "confirmation" if valid else "dropped", "record": entry_id, "day": day})


def _flag(state: MemoryState, entry_id: str, day: int, reason: str) -> Mutation | None:
    e = _entry(state, entry_id)
    if e is None or not _active(e) or e.get("needs_confirmation"):
        return None
    new = {**e, "needs_confirmation": True, "confirmation_reason": reason}
    return Mutation(entry=new, log={"operation": "flagged_for_confirmation", "record": entry_id, "day": day, "reason": reason})


def _undo(state: MemoryState, entry_id: str, day: int) -> Mutation | None:
    e = _entry(state, entry_id)
    if e is None:
        return None
    new = {k: v for k, v in {**e, "status": "active"}.items() if k not in UNDO_FIELDS}
    return Mutation(entry=new, log={"operation": "undone", "record": entry_id, "day": day})


def _drop(state: MemoryState, entry_id: str, day: int, reason: str) -> Mutation | None:
    e = _entry(state, entry_id)
    if e is None:
        return None
    new = {**e, "status": "dropped", "dropped_day": day, "drop_reason": reason}
    return Mutation(entry=new, log={"operation": "dropped", "record": entry_id, "day": day, "reason": reason})


class MemoryBook:
    def __init__(self, run: RunData, path: str | Path | None = None, repository: MemoryRepository | None = None):
        self.run = run
        self.path = Path(path or os.environ.get("CM_MEMORY_FILE") or ROOT / "data" / "live_memory.json")
        self.repository = repository or memory_repository(run.run_id, self.path)

    # ------------------------------------------------------------------ durum (her erişim depodan güncel okunur)
    @property
    def entries(self) -> list[dict]:
        return list(self.repository.state().entries)

    @property
    def log(self) -> list[dict]:
        return list(self.repository.state().log)

    @property
    def seed_day(self) -> int | None:
        return self.repository.state().seed_day

    def _snapshot(self, day: int) -> list[dict]:
        return [dict(e, status="active", source="simulation") for e in self.run.memory_snapshot(day)]

    def reset(self, day: int) -> int:
        return self.repository.seed(day, lambda: self._snapshot(day), force=True)

    def ensure(self, day: int) -> None:
        self.repository.seed(day, lambda: self._snapshot(day), force=False)

    # ------------------------------------------------------------------ okuma
    def for_address(self, address: int, day: int) -> list[dict]:
        return [e for e in self.repository.state().entries if e["address"] == address and _alive(e, day)]

    def get(self, entry_id: str) -> dict | None:
        return self.repository.state().find(entry_id)

    def summary(self, day: int) -> dict:
        alive = [e for e in self.repository.state().entries if _alive(e, day)]
        dist: dict[str, int] = {}
        for e in alive:
            dist[e["kind"]] = dist.get(e["kind"], 0) + 1
        last = sorted((e for e in alive if e.get("source") != "simulation"), key=lambda e: e.get("updated_at", 0), reverse=True)[:10]
        return {"total": len(alive), "type_distribution": dist, "last": last}

    # ------------------------------------------------------------------ yazma
    def upsert(self, *, address: int, kind: str, text: str, day: int, note_id: str | None, source: str = "agent",
               window: list[int] | None = None) -> tuple[dict, bool]:
        """pencere: kapalı penceresi [başlangıç, bitiş) gece yarısından dk (ör. "12 ile 1.5 arası" → [720, 810]); rota okur."""
        window = _check_window(kind, window)
        text = _check_text(kind, text)
        if not (0 <= address < len(self.run.addr_kind)):
            raise MemoryWriteError(f"Geçersiz adres: {address}")
        m = self.repository.mutate(lambda st: _upsert(st, address=address, kind=kind, text=text, day=day,
                                                      note_id=note_id, source=source, window=window))
        return m.entry, m.created

    def feedback(self, entry_id: str, valid: bool, day: int) -> dict | None:
        m = self.repository.mutate(lambda st: _feedback(st, entry_id, valid, day))
        return m.entry if m else None

    def flag_for_confirmation(self, entry_id: str, day: int, reason: str) -> bool:
        """Kayıt kalır ama kartta 'teyit gerekli' görünür (Değerlendirme Ajanı: ipucuna rağmen başarısızlık)."""
        return self.repository.mutate(lambda st: _flag(st, entry_id, day, reason)) is not None

    def undo(self, entry_id: str, day: int) -> bool:
        """Değerlendirme Ajanı'nın düşürme ya da teyide alma eylemini geri alır (müdür kararı)."""
        return self.repository.mutate(lambda st: _undo(st, entry_id, day)) is not None

    def drop(self, entry_id: str, day: int, reason: str) -> bool:
        return self.repository.mutate(lambda st: _drop(st, entry_id, day, reason)) is not None

"""Canlı adres hafızası (demo oturumu). P0: JSON dosyası; P1: DynamoDB (aynı arayüz).

Bir günün D kolu hafızasından tohumlanır; Hafıza Ajanı yazar, Brifing Ajanı okur, kurye geri bildirimi günceller.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .guardrails import find_pii, find_secret
from .rundata import INFO_KINDS, MEMORY_KINDS, ROOT, RunData

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


class MemoryWriteError(ValueError):
    pass


class MemoryBook:
    def __init__(self, run: RunData, path: str | Path | None = None):
        self.run = run
        self.path = Path(path or os.environ.get("CM_MEMORY_FILE") or ROOT / "data" / "live_memory.json")
        self._lock = threading.Lock()
        self.entries: list[dict] = []
        self.log: list[dict] = []
        self.seed_day: int | None = None
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                d = {}          # bozuk/yarım dosya: ilk ensure() hafızayı yeniden tohumlar
            if d.get("run_id") == run.run_id:
                self.entries, self.log, self.seed_day = d["entries"], d.get("log", []), d.get("seed_day")

    # ------------------------------------------------------------------ kalıcılık
    def _save(self) -> None:
        """Atomik yazım: geçici dosyaya yaz, sonra yerine taşı (eşzamanlı okuyucu yarım dosya görmez)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"app_data": True, "run_id": self.run.run_id, "seed_day": self.seed_day,
                                   "entries": self.entries, "log": self.log[-500:]}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def reset(self, day: int) -> int:
        with self._lock:
            self.entries = [dict(e, status="active", source="simulation") for e in self.run.memory_snapshot(day)]
            self.log = []
            self.seed_day = day
            self._save()
            return len(self.entries)

    def ensure(self, day: int) -> None:
        if self.seed_day is None:
            with self._lock:
                if self.seed_day is not None:
                    return
            self.reset(day)

    # ------------------------------------------------------------------ okuma
    def for_address(self, address: int, day: int) -> list[dict]:
        return [e for e in self.entries if e["address"] == address and e.get("status", "active") == "active"
                and (e.get("ttl_until") is None or day <= e["ttl_until"])]

    def get(self, entry_id: str) -> dict | None:
        return next((e for e in self.entries if e["id"] == entry_id), None)

    def summary(self, day: int) -> dict:
        alive = [e for e in self.entries if e.get("status", "active") == "active" and (e.get("ttl_until") is None or day <= e["ttl_until"])]
        dist: dict[str, int] = {}
        for e in alive:
            dist[e["kind"]] = dist.get(e["kind"], 0) + 1
        last = sorted((e for e in alive if e.get("source") != "simulation"), key=lambda e: e.get("updated_at", 0), reverse=True)[:10]
        return {"total": len(alive), "type_distribution": dist, "last": last}

    # ------------------------------------------------------------------ yazma
    def upsert(self, *, address: int, kind: str, text: str, day: int, note_id: str | None, source: str = "agent",
               window: list[int] | None = None) -> tuple[dict, bool]:
        """pencere: kapalı penceresi [başlangıç, bitiş) gece yarısından dk (ör. "12 ile 1.5 arası" → [720, 810]); rota okur."""
        if window is not None:
            if kind != "lunch_break" or len(window) != 2 or not (360 <= int(window[0]) < int(window[1]) <= 1200):
                raise MemoryWriteError("pencere yalnız lunch_break için, [başlangıç, bitiş] dakika (06:00–20:00) olmalı")
            window = [int(window[0]), int(window[1])]
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
        if not (0 <= address < len(self.run.addr_kind)):
            raise MemoryWriteError(f"Geçersiz adres: {address}")
        with self._lock:
            for e in self.entries:
                if e["address"] == address and e["kind"] == kind and e.get("status", "active") == "active":
                    e["sources"] += 1
                    e["last_day"] = day
                    e["text"] = text
                    e["updated_at"] = time.time()
                    if kind in TEMPORARY:
                        e["ttl_until"] = day + TTL_DAYS
                    if note_id:
                        e.setdefault("note_ids", []).append(note_id)
                    if window is not None:
                        e["window"] = window
                    if source not in (e.get("source_list") or [e.get("source")]):
                        e.setdefault("source_list", [e.get("source")]).append(source)
                    self.log.append({"operation": "updated", "record": e["id"], "day": day})
                    self._save()
                    return e, False
            n = 1 + max([int(x["id"][1:]) for x in self.entries if x["id"][1:].isdigit()] + [0])
            e = {"id": f"M{n:05d}", "address": address, "kind": kind, "text": text, "sources": 1,
                 "first_day": day, "last_day": day, "temporary": kind in TEMPORARY,
                 "ttl_until": day + TTL_DAYS if kind in TEMPORARY else None, "status": "active",
                 "source": source, "note_ids": [note_id] if note_id else [], "updated_at": time.time()}
            if window is not None:
                e["window"] = window
            self.entries.append(e)
            self.log.append({"operation": "added", "record": e["id"], "day": day})
            self._save()
            return e, True

    def feedback(self, entry_id: str, valid: bool, day: int) -> dict | None:
        with self._lock:
            e = self.get(entry_id)
            if e is None:
                return None
            if valid:
                e["sources"] += 1
                e["last_day"] = day
                e["confirmed_day"] = day
            else:
                e["status"] = "dropped"
                e["dropped_day"] = day
            self.log.append({"operation": "confirmation" if valid else "dropped", "record": entry_id, "day": day})
            self._save()
            return e

    def flag_for_confirmation(self, entry_id: str, day: int, reason: str) -> bool:
        """Kayıt kalır ama kartta 'teyit gerekli' görünür (Değerlendirme Ajanı: ipucuna rağmen başarısızlık)."""
        with self._lock:
            e = self.get(entry_id)
            if e is None or e.get("status", "active") != "active" or e.get("needs_confirmation"):
                return False
            e["needs_confirmation"] = True
            e["confirmation_reason"] = reason
            self.log.append({"operation": "flagged_for_confirmation", "record": entry_id, "day": day, "reason": reason})
            self._save()
            return True

    def undo(self, entry_id: str, day: int) -> bool:
        """Değerlendirme Ajanı'nın düşürme ya da teyide alma eylemini geri alır (müdür kararı)."""
        with self._lock:
            e = self.get(entry_id)
            if e is None:
                return False
            e["status"] = "active"
            for k in ("dropped_day", "drop_reason", "needs_confirmation", "confirmation_reason"):
                e.pop(k, None)
            self.log.append({"operation": "undone", "record": entry_id, "day": day})
            self._save()
            return True

    def drop(self, entry_id: str, day: int, reason: str) -> bool:
        with self._lock:
            e = self.get(entry_id)
            if e is None:
                return False
            e["status"] = "dropped"
            e["dropped_day"] = day
            e["drop_reason"] = reason
            self.log.append({"operation": "dropped", "record": entry_id, "day": day, "reason": reason})
            self._save()
            return True

"""Ajan izi (trace): araç çağrısı → sonuç → karar olaylarının sıralı kaydı.

Canlı (LLM) yol ve kurallı yedek AYNI olay biçimini üretir; arayüz hangisinin çalıştığını yalnız `source`
alanından anlar. İz deterministiktir (saat damgası yok): aynı girdi aynı izi verir. Olay biçimi
`docs/sozlesmeler.md` §5'tedir.

Olay tipleri:
  basla          {gun, mod, gorev}
  karar          {text}                         ajanın (ya da kuralın) bir sonraki adım kararı / gözlemi
  arac           {arac, girdi}                   araç çağrısı
  sonuc          {arac, ozet, veri}              araç sonucu (veri: aracın tam JSON çıktısı)
  hata           {arac?, metin}                  araç hatası (ajana geri verilir)
  yedek          {text}                         canlı yol başarısız → kurallı yedeğe geçiş
  oneri          {proposal}                         müdüre sunulan gerekçeli öneri
  awaiting_approval  {}                              insan onayı noktası
  human_decision   {karar, not, changed_clusters}   müdürün kararı (onay | ret | duzenle)
  yanit          {response}                         senaryo sorusunun cevabı
  bitti          {status}
"""
from __future__ import annotations

import threading
from typing import Any, Callable

SOURCES = ("llm", "rule")


class Trace:
    def __init__(self, on_event: Callable[[dict], None] | None = None):
        self.events: list[dict] = []
        self._listeners: list[Callable[[dict], None]] = [on_event] if on_event else []
        self._lock = threading.Lock()
        self.source = "rule"

    def listen(self, fn: Callable[[dict], None]) -> None:
        self._listeners.append(fn)

    def emit(self, type: str, **kw: Any) -> dict:
        with self._lock:
            ev = {"i": len(self.events), "type": type, "source": kw.pop("source", self.source), **kw}
            self.events.append(ev)
        for fn in self._listeners:
            fn(ev)
        return ev

    def since(self, n: int) -> list[dict]:
        with self._lock:
            return list(self.events[n:])

    def __len__(self) -> int:
        return len(self.events)

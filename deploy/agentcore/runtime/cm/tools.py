"""Strands araçları: ajanın çağırdığı her şey burada, deterministik alan fonksiyonlarına bağlanır.

Üç erişim sınıfı (cm/scope.py bunları zorlar):
  COURIER_TOOLS  `courier_id` alır; kurye yalnız kendi kimliğiyle çağırabilir, müdür herkes için çağırabilir.
  MANAGER_TOOLS  yalnız müdür (şube planı, sabah değerlendirmesi, bölge raporu).
  PUBLIC_TOOLS   herkese açık, salt okunur şube özeti ve gerçek gün kanıtı.

Araçlar JSON metni döndürür; sayılar yalnız buradan gelir, model hesap yapmaz. Hesabı cm/backend.py yapar:
tam takım (agents.Services) ya da alan kodu yokken çekirdek takım (cm/core.py).
"""
from __future__ import annotations

import json

from strands import tool

from .backend import backend


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _day(day: int | None) -> int:
    b = backend()
    d = int(day) if day else b.default_day()
    days = b.eval_days()
    if d not in days:
        raise ValueError(f"Gün {d} değerlendirme döneminde değil ({days[0]}–{days[-1]})")
    return d


def _courier(courier_id: str) -> str:
    if courier_id not in backend().couriers():
        raise ValueError(f"Bilinmeyen kurye: {courier_id}")
    return courier_id


# ------------------------------------------------------------------ kurye araçları
@tool
def courier_briefing(courier_id: str, day: int | None = None) -> str:
    """Kuryenin sabah brifingi: durak ve gönderi sayısı, tahmini dönüş, bölgeye yabancı duraklar, hafızadaki uyarılar.

    Args:
        courier_id: Kurye kimliği (ör. O02).
        day: Simülasyon günü; verilmezse demo günü.
    """
    return _j(backend().briefing(_courier(courier_id), _day(day)))


@tool
def stop_cards(courier_id: str, day: int | None = None) -> str:
    """Kuryenin bugünkü rotasında hafızada bilgi kartı olan duraklar (park, bina erişimi, site güvenliği, zil…).

    Args:
        courier_id: Kurye kimliği.
        day: Simülasyon günü; verilmezse demo günü.
    """
    return _j(backend().stop_cards(_courier(courier_id), _day(day)))


@tool
def approaching_stop(courier_id: str, lat: float, lng: float, next_order: int | None = None,
                     shown: list[str] | None = None, day: int | None = None) -> str:
    """Kuryenin konumuna göre şimdi söylenecek kartlar: durağa 400 m kala park/tarif, kapıda (60 m) zil/kat/güvenlik.

    Args:
        courier_id: Kurye kimliği.
        lat: Kuryenin enlemi.
        lng: Kuryenin boylamı.
        next_order: Sıradaki durağın rota sırası (biliniyorsa).
        shown: Daha önce söylenmiş kart kimlikleri; tekrar söylenmez.
        day: Simülasyon günü; verilmezse demo günü.
    """
    return _j(backend().approach(_courier(courier_id), _day(day), lat, lng, next_order, shown or []))


@tool
def leave_note(courier_id: str, text: str, lat: float | None = None, lng: float | None = None, day: int | None = None) -> str:
    """Kuryenin kapıda bıraktığı serbest notu işler: adrese bağlar, türünü çıkarır, kişisel veriyi ve kapı şifresini ayıklar.

    Args:
        courier_id: Notu bırakan kurye.
        text: Notun metni (ör. "sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakın").
        lat: Notun bırakıldığı enlem (adres eşlemesi için).
        lng: Notun bırakıldığı boylam.
        day: Simülasyon günü; verilmezse demo günü.
    """
    return _j(backend().leave_note(_courier(courier_id), _day(day), text, lat, lng))


# ------------------------------------------------------------------ müdür araçları
@tool
def plan_day(day: int | None = None) -> str:
    """Günün planı (Orkestratör): hacim, kapasite açığı, komşu şubeden kim gelsin, atama ve müdüre gerekçeli öneri.

    Args:
        day: Simülasyon günü; verilmezse demo günü.
    """
    return _j(backend().plan_day(_day(day)))


@tool
def morning_review(day: int | None = None) -> str:
    """Sabah öz-değerlendirme (Değerlendirme Ajanı): son 5 gün ↔ önceki 5 gün, düzeltmeler ve müdür onayı bekleyen öneriler.

    Args:
        day: Simülasyon günü; verilmezse demo günü.
    """
    return _j(backend().morning_review(_day(day)))


@tool
def region_report(day: int | None = None) -> str:
    """Şube bölge raporu (Bölge Ajanı): zor bloklar, hafızası boş bloklar, kıdemliye açılan sorular.

    Args:
        day: Simülasyon günü; verilmezse demo günü.
    """
    return _j(backend().region_report(_day(day)))


@tool
def harvest_questions(day: int | None = None) -> str:
    """Hafıza hasadı (Hasat Ajanı): hafızası boş ya da tekrar tekrar başarısız olan adresler için bölgeyi bilen
    kuryelere sorulacak hedefli sorular. Cevaplar Hafıza Ajanı'ndan geçip hafızaya yazılır.

    Args:
        day: Simülasyon günü; verilmezse demo günü.
    """
    return _j(backend().harvest(_day(day)))


# ------------------------------------------------------------------ herkese açık (salt okunur)
@tool
def branch_memory_summary(day: int | None = None) -> str:
    """Şube hafızasının özeti: aktif adres kaydı sayısı ve tür dağılımı (kişisel veri içermez).

    Args:
        day: Simülasyon günü; verilmezse demo günü.
    """
    return _j(backend().memory_summary(_day(day)))


@tool
def real_day_evidence() -> str:
    """Gerçek Beykoz günü (5 Mayıs) kanıtı: sabit ↔ dinamik bölge, tanıdık ↔ yabancı sokakta başarısız teslim oranı."""
    return _j(backend().real_day_evidence())


COURIER_TOOLS = (courier_briefing, stop_cards, approaching_stop, leave_note)
MANAGER_TOOLS = (plan_day, morning_review, region_report, harvest_questions)
PUBLIC_TOOLS = (branch_memory_summary, real_day_evidence)
ALL_TOOLS = [*COURIER_TOOLS, *MANAGER_TOOLS, *PUBLIC_TOOLS]

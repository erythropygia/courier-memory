"""Seed ve ortak rastgele sayılar (CRN).

Her gün için akış bazında, adres kimliğiyle indekslenen diziler üretilir. Talep politikadan bağımsız
olduğu için aynı (gün, adres) tüm kollarda aynı sayıları alır; kollar arası fark gürültüden değil
politikadan gelir.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Akış kimlikleri: sabit tutulmalı; değişirse tüm sonuçlar değişir.
S_WORLD, S_COURIERS, S_DEMAND, S_QUIRKS = 1, 2, 3, 4
S_PRESENCE = 5                 # adres bulunabilirlik profili (dünya kurulumu; diğer akışları değiştirmez)
S_STOP, S_CAUSE, S_LEARN, S_NOTE, S_COMPLY, S_SHIP, S_PARSE, S_NOTE_TEXT, S_ASSIGN, S_FEEDBACK, S_NOISE, S_HARVEST = range(10, 22)
S_MORNING = 22                   # kurye başına sabah çıkış sapması (gün başına; kollar arası ortak, diğer akışları değiştirmez)
N_QUIRK_SLOTS = 4


def rng(seed: int, *keys: int) -> np.random.Generator:
    return np.random.default_rng([seed, *keys])


@dataclass(frozen=True)
class DayStreams:
    """Bir günün CRN dizileri. Adres düzeyindekiler (n_addresses,), gönderi düzeyi talep sırasında."""
    u_stop: np.ndarray
    u_cause: np.ndarray
    u_learn: np.ndarray       # (n_addresses, N_QUIRK_SLOTS)
    u_note: np.ndarray
    u_comply: np.ndarray      # (n_addresses, N_QUIRK_SLOTS)
    u_ship: np.ndarray        # (toplam gönderi,) adres sırasına göre ofsetli
    ship_offset: np.ndarray   # (n_addresses,) adresin ilk gönderisinin u_ship içindeki indeksi
    u_parse: np.ndarray
    u_feedback: np.ndarray


def day_streams(seed: int, day: int, counts: np.ndarray) -> DayStreams:
    n = counts.shape[0]
    offs = np.zeros(n, dtype=np.int64)
    np.cumsum(counts[:-1], out=offs[1:])
    total = int(counts.sum())
    return DayStreams(
        u_stop=rng(seed, day, S_STOP).random(n),
        u_cause=rng(seed, day, S_CAUSE).random(n),
        u_learn=rng(seed, day, S_LEARN).random((n, N_QUIRK_SLOTS)),
        u_note=rng(seed, day, S_NOTE).random(n),
        u_comply=rng(seed, day, S_COMPLY).random((n, N_QUIRK_SLOTS)),
        u_ship=rng(seed, day, S_SHIP).random(max(total, 1)),
        ship_offset=offs,
        u_parse=rng(seed, day, S_PARSE).random(n),
        u_feedback=rng(seed, day, S_FEEDBACK).random(n),
    )

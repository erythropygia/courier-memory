"""Gözlemlenebilir geçmiş: ziyaretler, tanıdıklık, deneme/başarısızlık sayıları, süreler.

Bu modül gizli gerçek içermez. Politikalar ve ajanlar `HistoryReader` üzerinden salt-okur erişir.
Tanıdıklık ziyaret geçmişinden hesaplanır; dolayısıyla gözlemlenebilirdir. Kuryenin hangi püf
noktasını bildiği ise gizlidir ve burada yoktur.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Familiarity:
    alpha: float
    half_life: float
    state: dict[str, dict[int, tuple[float, int]]] = field(default_factory=lambda: defaultdict(dict))

    def value(self, courier: str, block: int, day: int) -> float:
        s = self.state.get(courier, {}).get(block)
        if s is None:
            return 0.0
        f, last = s
        gap = max(0, day - last - 1)          # ziyaret edilmeyen tam günler
        return f * 2.0 ** (-gap / self.half_life)

    def visit(self, courier: str, block: int, day: int) -> None:
        f = self.value(courier, block, day)
        self.state[courier][block] = (f + self.alpha * (1.0 - f), day)

    def blocks_of(self, courier: str) -> dict[int, tuple[float, int]]:
        return dict(self.state.get(courier, {}))


@dataclass
class History:
    n_blocks: int
    block_att: np.ndarray = field(init=False)
    block_fail: np.ndarray = field(init=False)
    block_rel: np.ndarray = field(init=False)        # kuryeye bağlı başarısızlık (alıcı yok hariç)
    # tanıdık / yabancı ayrımıyla blok bazında (yabancılık çarpanı tahmini için)
    unf_att: np.ndarray = field(init=False)
    unf_fail: np.ndarray = field(init=False)
    fam_att: np.ndarray = field(init=False)
    fam_fail: np.ndarray = field(init=False)
    unf_rel: np.ndarray = field(init=False)
    fam_rel: np.ndarray = field(init=False)
    cb_att: dict[tuple[str, int], int] = field(default_factory=lambda: defaultdict(int))
    cb_unf_att: dict[tuple[str, int], int] = field(default_factory=lambda: defaultdict(int))
    c_att: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    c_fail: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    c_rel: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    c_svc_actual: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    c_svc_base: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    c_days: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    addr_days: dict[int, int] = field(default_factory=lambda: defaultdict(int))   # adresin durak olduğu gün sayısı
    extra_unf: list[float] = field(default_factory=lambda: [0.0, 0])   # [toplam ek dk, durak]
    extra_fam: list[float] = field(default_factory=lambda: [0.0, 0])
    time: object = None        # teslim zamanı kaydı (cm_sim.delivery_time.TimeRecord): adres × gün tipi × dilim, gözlemlenebilir

    def __post_init__(self) -> None:
        z = lambda: np.zeros(self.n_blocks, dtype=np.int64)  # noqa: E731
        self.block_att, self.block_fail, self.block_rel = z(), z(), z()
        self.unf_att, self.unf_fail, self.fam_att, self.fam_fail = z(), z(), z(), z()
        self.unf_rel, self.fam_rel = z(), z()


class HistoryReader:
    """Salt-okur görünüm. Politikalar yalnız bunu görür."""

    def __init__(self, history: History, fam: Familiarity, unfamiliar_below: float,
                 block_kind: list[str] | None = None):
        self._h = history
        self._f = fam
        self.unfamiliar_below = unfamiliar_below
        self.block_kind = list(block_kind) if block_kind is not None else None   # gözlemlenebilir blok türü

    @property
    def n_blocks(self) -> int:
        return self._h.n_blocks

    def familiarity(self, courier: str, block: int, day: int) -> float:
        return self._f.value(courier, block, day)

    def familiarity_vec(self, courier: str, blocks: np.ndarray, day: int) -> np.ndarray:
        return np.array([self._f.value(courier, int(b), day) for b in blocks])

    def familiar_blocks(self, courier: str, day: int, min_f: float) -> tuple[np.ndarray, np.ndarray]:
        """Kuryenin çekirdek blokları ve tanıdıklıkları (ziyaret geçmişinden; gözlemlenebilir)."""
        bs, fs = [], []
        for b in self._f.blocks_of(courier):
            f = self._f.value(courier, b, day)
            if f >= min_f:
                bs.append(b)
                fs.append(f)
        return np.array(bs, dtype=np.int64), np.array(fs, dtype=float)

    def block_counts(self) -> tuple[np.ndarray, np.ndarray]:
        return self._h.block_att.copy(), self._h.block_fail.copy()

    def block_relevant_fails(self) -> np.ndarray:
        """Kuryeye bağlı başarısızlıklar (neden kodu 'alıcı yok' olmayanlar)."""
        return self._h.block_rel.copy()

    def split_counts(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(yabancı deneme, yabancı kuryeye bağlı başarısızlık, tanıdık deneme, tanıdık kuryeye bağlı başarısızlık)"""
        h = self._h
        return h.unf_att.copy(), h.unf_rel.copy(), h.fam_att.copy(), h.fam_rel.copy()

    def courier_block_attempts(self, courier: str) -> dict[int, int]:
        return {b: n for (c, b), n in self._h.cb_att.items() if c == courier}

    def courier_block_unfamiliar_attempts(self, courier: str) -> dict[int, int]:
        return {b: n for (c, b), n in self._h.cb_unf_att.items() if c == courier}

    def courier_counts(self, courier: str) -> tuple[int, int]:
        """(deneme, toplam başarısızlık)"""
        return self._h.c_att.get(courier, 0), self._h.c_fail.get(courier, 0)

    def courier_relevant_fails(self, courier: str) -> int:
        return self._h.c_rel.get(courier, 0)

    def courier_service(self, courier: str) -> tuple[float, float]:
        return self._h.c_svc_actual.get(courier, 0.0), self._h.c_svc_base.get(courier, 0.0)

    def days_in_branch(self, courier: str) -> int:
        return self._h.c_days.get(courier, 0)

    def extra_minutes(self) -> tuple[tuple[float, int], tuple[float, int]]:
        return tuple(self._h.extra_unf), tuple(self._h.extra_fam)  # type: ignore[return-value]

    def couriers_seen(self) -> list[str]:
        return sorted(self._h.c_att.keys())

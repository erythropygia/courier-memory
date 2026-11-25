"""Hafıza-farkında rota (Hedef 3): hafıza kayıtlarını rotanın okuyabileceği kısıtlara çevirir ve uygular.

Üç adım (kol D ve Orkestratör'ün `compute_route` aracı AYNI fonksiyonları kullanır; tech.md: "aynı araçlar
simülatörde de kullanılır"):

1. **Planda erteleme:** bugün kapalı olduğu bilinen durak (cumartesi kapalı + Cumartesi, geçici kapalı) rotadan
   çıkar. Kurye boşuna gitmez; kapasite boşalır. Kol D'de bu, kümelemeden ÖNCE yapılır.
2. **Servis süresi düzeltmesi:** bilinen püf noktasının kalan ek süresi (güvenlik, resepsiyon, arka giriş …) durak
   ağırlığına ve planlanan süreye eklenir; küme dengesi ve ETA gerçeğe yaklaşır.
3. **Pencere onarımı:** kapalı penceresi bilinen (öğle arası) durağın beklenen varışı pencereye düşüyorsa, en az km
   artışıyla pencere dışına taşınır (or-opt: çıkar, en iyi yere yerleştir). Bedel dürüstçe raporlanır (+km).
4. **Zaman onarımı (Faz 2b):** teslim zamanı bulgusu olan durak (kayıtlardan: "öğlen kimse yok, 16 sonrası var") bulunma
   olasılığı yüksek saate kaydırılır. Amaç = sürüş dk + km × km_maliyeti + Σ tahmini bulunamama(varış dilimi) × tekrar ziyaret
   dk. Hamleler: durağı taşı (or-opt) ya da durağı içeren bir parçayı ters çevir (2-opt); bilinen pencere ihlali artmaz.
5. **Sert kısıt (Faz 2c, `RepairLimits`):** pencere ve zaman onarımı, onarım öncesi rotaya (erteleme sonrası, servis
   düzeltmeli) göre beklenen rota süresini (sürüş + servis + bilinen öğle beklemesi) `max_extra_min` dk'dan, km'yi
   `max_extra_km`'den fazla artıramaz; vardiya bandı üstü (`band_max`) aşılamaz, zaten aşılıyorsa süre artamaz; kaydırılan
   bulgu durağı vardiya bitişinden (başlangıç + band_max, beklenen varış) sonraya konamaz. Kısıtı sağlamayan hamle
   reddedilir; beklenen başarısızlığın maliyeti fazla mesaiyi "kazanç" diye satın alamaz. Kısıt yüzünden kaydırılamayan
   bulgu `time_blocked` olarak döner (neden + en az ek dk); `time_alternatives` ona başka kurye (her iki rotada kısıt) ya
   da ertesi gün / akşam-teslim noktası + SMS önerisi üretir (müdür kararı).

Fonksiyonlar saf: yalnız dizi ve sözlük alır (gizli gerçek yok). Girdi: düğüm 0 = depo, 1..n duraklar.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from .delivery_time import SLOT_NAMES, BORDERS, slots

CLOSED_DAY_KINDS = {"saturday_closed": 5}           # tür → kapalı haftagünü (0=Pzt … 5=Cmt)
CLOSED_ALWAYS_KINDS = ("temporary_closed",)             # TTL boyunca kapalı
WINDOW_KINDS = ("lunch_break",)


@dataclass
class StopRule:
    """Bir adresin bugünkü kısıtları (hafızadan)."""
    closed: str | None = None                            # bugün kapatan tür
    windows: list[tuple[float, float]] = field(default_factory=list)   # [başlangıç, bitiş) gece yarısından dk
    extra: float = 0.0                                   # ek servis dk
    sources: list[str] = field(default_factory=list)     # hafıza kaydı kimlikleri
    kinds: list[str] = field(default_factory=list)
    presence: tuple[float, ...] | None = None            # teslim zamanı bulgusu: dilim başına tahmini bulunamama (Faz 2b)


@dataclass(frozen=True)
class RepairLimits:
    """Hafıza onarımlarının sert kısıtı (Faz 2c). Onarım öncesi rotaya göre:
    - beklenen rota süresi (sürüş + servis + bilinen öğle beklemesi, planlanan dk) en çok `max_extra_min` artar;
    - km en çok `max_extra_km` artar;
    - `band_max` (vardiya bandı üstü) aşılamaz; onarım öncesi zaten aşılıyorsa süre hiç artamaz (tolerans da yok);
    - kaydırılan bulgu durağının beklenen varışı vardiya bitişinden (başlangıç + band_max) sonra olamaz (öncesinde zaten
      sonraysa daha geç olamaz).
    """
    max_extra_min: float = 0.0
    max_extra_km: float = 0.5
    band_max: float | None = 528.0
    wait_max: float = 15.0                               # bilinen öğle penceresinde bekleme üst sınırı (quirks.lunch_wait_max)
    blocked_diff: float = 0.3                            # bulgu durağı en iyi dilimden bu kadar kötü dilimde kaldıysa "kaydırılamadı"
    wait_margin: float | None = None                     # bekleme tahmininde pencere payı (dk); None → plan_route margin'i
    shift_end_at: float | None = None                      # Faz 5: vardiya bitişi saat olarak (mesai başı + band_max); rota
                                                         # şubeden geç çıkınca da sabit kalır. None → başlangıç + band_max

    def cap(self, dur0: float) -> float:
        """Onarım sonrası izin verilen en uzun beklenen süre."""
        c = dur0 + self.max_extra_min
        if self.band_max is not None:
            c = min(c, self.band_max) if dur0 <= self.band_max else dur0
        return c

    def allowed(self, dur, km, dur0: float, km0: float):
        return (np.asarray(dur) <= self.cap(dur0) + 1e-9) & (np.asarray(km) <= km0 + self.max_extra_km + 1e-9)

    def shift_end(self, start: float) -> float | None:
        if self.shift_end_at is not None:
            return float(self.shift_end_at)
        return None if self.band_max is None else float(start) + float(self.band_max)


def rule_from_entries(entries, weekday: int, lunch: tuple[float, float], extra_map: dict[str, float],
                      min_sources_closed: int = 1) -> StopRule | None:
    """entries: (tür, kayıt_kimliği, kaynak_sayısı, pencere|None) dizisi.

    Kapanış (bugün kapalı) yalnız `min_sources_closed` bağımsız kaynakla kural olur: tek kaynaklı kapanış notu rotada kalır
    ve kapıda ipucu olarak söylenir (yanlış erteleme bir teslimi kaçırır, doğru erteleme yalnız bir yolu kurtarır).
    Pencere kayıtta yapılı olarak varsa (Hafıza Ajanı "12 ile 1.5 arası" gibi notlardan çıkarır) o kullanılır, yoksa öğle arası.
    """
    r = StopRule()
    for e in entries:
        kind, eid, n_src = e[0], e[1], int(e[2]) if len(e) > 2 else 1
        win = e[3] if len(e) > 3 else None
        r.kinds.append(kind)
        r.sources.append(eid)
        closes = (kind in CLOSED_DAY_KINDS and CLOSED_DAY_KINDS[kind] == weekday) or kind in CLOSED_ALWAYS_KINDS
        if closes and n_src >= min_sources_closed:
            r.closed = r.closed or kind
        elif kind in WINDOW_KINDS:
            r.windows.append((float(win[0]), float(win[1])) if win else (float(lunch[0]), float(lunch[1])))
        r.extra += float(extra_map.get(kind, 0.0))
    return r if r.kinds else None


def route_km(order: np.ndarray, D: np.ndarray) -> float:
    return float(D[order[:-1], order[1:]].sum()) if len(order) > 1 else 0.0


def arrivals(order: np.ndarray, D: np.ndarray, svc: np.ndarray, start: float, mpk: float, scale: float = 1.0) -> np.ndarray:
    """order: depo(0) ile başlayıp biten düğüm dizisi. Her konumdaki beklenen varış (dk, gece yarısından)."""
    legs = D[order[:-1], order[1:]] * mpk
    s = svc[order[:-1]].copy()
    s[0] = 0.0
    cum = np.concatenate([[0.0], np.cumsum(legs + s)])
    return start + scale * cum


def _bad(arr: np.ndarray, order: np.ndarray, windows: dict[int, list[tuple[float, float]]], margin: float) -> int:
    n = 0
    pos = {int(v): i for i, v in enumerate(order)}
    for v, ws in windows.items():
        if v not in pos:
            continue
        t = arr[pos[v]]
        if any(lo - margin <= t < hi + margin for lo, hi in ws):
            n += 1
    return n


def _arr_km(C: np.ndarray, D: np.ndarray, svc: np.ndarray, start: float, mpk: float, scale: float):
    """Aday sıralar (m × L, depo dahil): (beklenen varışlar m × L, km m)."""
    legs = D[C[:, :-1], C[:, 1:]]
    s = svc[C[:, :-1]].copy()
    s[:, 0] = 0.0
    arr = start + scale * np.concatenate([np.zeros((len(C), 1)), np.cumsum(legs * mpk + s, axis=1)], axis=1)
    return arr, legs.sum(1)


def _waits(C: np.ndarray, arr: np.ndarray, windows: dict[int, list[tuple[float, float]]], wait_max: float) -> np.ndarray:
    """Bilinen kapalı pencereye düşen varışlarda beklenen bekleme toplamı: min(pencere sonu − varış, wait_max) (outcome ile aynı)."""
    w = np.zeros(len(C))
    if not windows or wait_max <= 0:
        return w
    rows = np.arange(len(C))
    for v, ws in windows.items():
        hit = C == v
        has = hit.any(1)
        if not has.any():
            continue
        t = arr[rows, np.argmax(hit, axis=1)]
        best = np.zeros(len(C))
        for lo, hi in ws:
            best = np.maximum(best, np.where((lo <= t) & (t < hi), np.minimum(hi - t, wait_max), 0.0))
        w += np.where(has, best, 0.0)
    return w


def _durations(C: np.ndarray, arr: np.ndarray, km: np.ndarray, svc: np.ndarray, windows, mpk: float, wait_max: float) -> np.ndarray:
    """Beklenen rota süresi (planlanan dk): sürüş + servis + bilinen pencere beklemesi. Bant bu süreyle karşılaştırılır."""
    return km * mpk + svc[C[:, 1:-1]].sum(1) + _waits(C, arr, windows, wait_max)


def route_duration(order: np.ndarray, D: np.ndarray, svc: np.ndarray, windows, start: float, mpk: float, scale: float,
                   wait_max: float) -> tuple[float, float]:
    """(beklenen rota süresi dk, km) tek sıra için."""
    C = np.asarray(order, dtype=np.int64)[None, :]
    arr, km = _arr_km(C, D, svc, start, mpk, scale)
    return float(_durations(C, arr, km, svc, windows, mpk, wait_max)[0]), float(km[0])


def repair_windows(order: np.ndarray, D: np.ndarray, svc: np.ndarray, windows: dict[int, list[tuple[float, float]]],
                   start: float, mpk: float, scale: float, margin: float, limits: RepairLimits | None = None,
                   base: tuple[float, float] | None = None, known: dict | None = None) -> tuple[np.ndarray, list[dict]]:
    """Penceresine düşen durakları or-opt ile taşır. Kabul: pencereye düşen toplam durak sayısı azalmalı; eşitlikte en az km.
    limits (Faz 2c): aday ayrıca onarım öncesi rotaya (`base` = (süre, km)) göre sert kısıtı sağlamalı; süre bilinen öğle
    beklemesini içerir (`known`: tüm bilinen pencereler), yani taşıma ancak eklediği sürüş kaçırdığı beklemeden azsa kabul edilir.

    Dönüş: (yeni düğüm dizisi, değişiklikler [{dugum, old_position, new_position, old_arrival, new_arrival, extra_km, extra_min}]).
    """
    order = np.asarray(order, dtype=np.int64).copy()
    changes: list[dict] = []
    if not windows:
        return order, changes
    known = windows if known is None else known
    wmax = limits.wait_max if limits is not None else 0.0
    if limits is not None and base is None:
        base = route_duration(order, D, svc, known, start, mpk, scale, wmax)
    for _ in range(2 * len(windows)):
        arr = arrivals(order, D, svc, start, mpk, scale)
        bad_now = _bad(arr, order, windows, margin)
        if bad_now == 0:
            break
        pos = {int(v): i for i, v in enumerate(order)}
        viol = [v for v, ws in windows.items() if v in pos and any(lo - margin <= arr[pos[v]] < hi + margin for lo, hi in ws)]
        viol.sort(key=lambda v: pos[v])
        moved = False
        dur_now = route_duration(order, D, svc, known, start, mpk, scale, wmax)[0]
        for v in viol:
            i = pos[v]
            rest = np.delete(order, i)
            km0 = route_km(order, D)
            P = np.array([p for p in range(1, len(rest)) if p != i], dtype=np.int64)
            if not len(P):
                continue
            C = np.array([np.insert(rest, p, v) for p in P], dtype=np.int64)
            A2, KM = _arr_km(C, D, svc, start, mpk, scale)
            NB = _window_bad_matrix(C, A2, windows, margin)
            DUR = _durations(C, A2, KM, svc, known, mpk, wmax)
            ok = NB < bad_now
            if limits is not None:
                ok &= limits.allowed(DUR, KM, base[0], base[1])
            idx = np.flatnonzero(ok)
            if not len(idx):
                continue
            # Eşitlikte (km farkı < 10 cm) en küçük konum: ajan koordinatları yayımlanan hassasiyetle (~1 cm) okur, kayan nokta
            # farkı eşit maliyetli iki konum arasında seçimi simülatörden ayırmasın (Faz 5: gün 22'de 407/408).
            j = _first_equal(idx, NB[idx], KM[idx], 1e-4)
            p = int(P[j])
            changes.append({"node": int(v), "old_position": int(i), "new_position": p,
                            "old_arrival": float(arr[i]), "new_arrival": float(A2[j, p]), "extra_km": float(KM[j] - km0),
                            "extra_min": float(DUR[j] - dur_now)})
            order = C[j].copy()
            moved = True
            break
        if not moved:
            break
    return order, changes


def _first_equal(idx: np.ndarray, k0: np.ndarray, k1: np.ndarray, tol1: float, tol0: float = 0.0) -> int:
    """idx içinden k0 en küçük (tol0 toleransla), sonra k1 en küçük (tol1 toleransla), sonra en küçük indeks."""
    m = k0 <= k0.min() + tol0
    m &= k1 <= k1[m].min() + tol1
    return int(idx[m].min())


def _window_bad_matrix(C: np.ndarray, arr: np.ndarray, windows: dict[int, list[tuple[float, float]]], margin: float) -> np.ndarray:
    bad = np.zeros(len(C), dtype=np.int64)
    rows = np.arange(len(C))
    for v, ws in windows.items():
        hit = C == v
        if not hit.any():
            continue
        t = arr[rows, np.argmax(hit, axis=1)]
        bad += np.any([(lo - margin <= t) & (t < hi + margin) for lo, hi in ws], axis=0)
    return bad


def _eval_orders(C: np.ndarray, D: np.ndarray, svc: np.ndarray, pres: dict[int, np.ndarray], start: float, mpk: float,
                 scale: float, km_w: float, revisit: float):
    """Aday sıralar (m × L, depo dahil): (maliyet dk, varışlar, km). Maliyet = sürüş + km × km_w + Σ p(dilim) × revisit."""
    arr, km = _arr_km(C, D, svc, start, mpk, scale)
    cost = km * (mpk + km_w)
    rows = np.arange(len(C))
    for v, tab in pres.items():
        t = arr[rows, np.argmax(C == v, axis=1)]
        cost = cost + revisit * tab[slots(t)]
    return cost, arr, km


def repair_times(order: np.ndarray, D: np.ndarray, svc: np.ndarray, pres: dict[int, np.ndarray],
                 windows: dict[int, list[tuple[float, float]]], start: float, mpk: float, scale: float, margin: float,
                 revisit: float, km_w: float, min_gain: float, limits: RepairLimits | None = None,
                 base: tuple[float, float] | None = None, known: dict | None = None) -> tuple[np.ndarray, list[dict]]:
    """Teslim zamanı bulgusu olan düğümleri (pres: düğüm → dilim başına bulunamama) bulunma olasılığı yüksek saate kaydırır.

    Her turda her bulgu düğümü için tüm or-opt yerleri ve düğümü içeren tüm 2-opt ters çevirmeleri değerlendirilir; en düşük
    maliyetli aday, maliyeti en az `min_gain` dk düşürüyor ve bilinen pencere ihlalini artırmıyorsa uygulanır.
    Faz 5: hamle sahibinin (bulgu düğümü) bulunamama olasılığı düşmeli; düşürmeyen aday (ör. başka bir düğüm ya da yol için
    yapılan ters çevirme sahibini kötü saate itiyorsa) elenir. Aynı hamle o düğümü iyileştiriyorsa onun adıyla zaten adaydır.
    limits (Faz 2c): aday ayrıca sert kısıtı sağlamalı (onarım öncesi `base` süre/km'ye göre; bant; bulgu durağı vardiya
    bitişinden sonraya kaymaz). Kısıtı sağlamayan aday maliyetinden bağımsız elenir: beklenen başarısızlık kazancı süre satın alamaz.
    Dönüş: (yeni düğüm dizisi, değişiklikler [{dugum, hamle, old_position, new_position, old_arrival, new_arrival, extra_km, extra_min,
    old_p, new_p, gain_min}]). Konumlar 1 tabanlı durak sırasıdır (depo 0).
    """
    order = np.asarray(order, dtype=np.int64).copy()
    changes: list[dict] = []
    members = set(order.tolist())
    pres = {int(v): np.asarray(t, dtype=float) for v, t in pres.items() if int(v) in members}
    if not pres or len(order) < 4:
        return order, changes
    known = windows if known is None else known
    wmax = limits.wait_max if limits is not None else 0.0
    if limits is not None and base is None:
        base = route_duration(order, D, svc, known, start, mpk, scale, wmax)
    se = limits.shift_end(start) if limits is not None else None
    a_ref = arrivals(order, D, svc, start, mpk, scale)
    t_ref = {int(v): float(a_ref[i]) for i, v in enumerate(order) if int(v) in pres}
    L = len(order)
    for _ in range(2 * len(pres) + 2):
        c0, a0, k0 = _eval_orders(order[None, :], D, svc, pres, start, mpk, scale, km_w, revisit)
        w0 = int(_window_bad_matrix(order[None, :], a0, windows, margin)[0]) if windows else 0
        d0 = float(_durations(order[None, :], a0, k0, svc, known, mpk, wmax)[0])
        pos = {int(v): i for i, v in enumerate(order)}
        cands, owner, kind = [], [], []
        for v in sorted(pres, key=lambda x: pos[x]):
            i = pos[v]
            rest = np.delete(order, i)
            for p in range(1, len(rest)):
                if p != i:
                    cands.append(np.insert(rest, p, v))
                    owner.append(v)
                    kind.append("move")
            a_ = np.repeat(np.arange(1, i + 1), L - 1 - i)
            b_ = np.tile(np.arange(i, L - 1), i)
            keep = a_ < b_
            a_, b_ = a_[keep], b_[keep]
            if len(a_):
                J = np.broadcast_to(np.arange(L), (len(a_), L))
                J = np.where((J >= a_[:, None]) & (J <= b_[:, None]), a_[:, None] + b_[:, None] - J, J)
                cands.extend(order[J])
                owner.extend([v] * len(a_))
                kind.extend(["reverse"] * len(a_))
        if not cands:
            break
        C = np.array(cands, dtype=np.int64)
        cost, arr, km = _eval_orders(C, D, svc, pres, start, mpk, scale, km_w, revisit)
        dur = _durations(C, arr, km, svc, known, mpk, wmax)
        if windows:
            cost = np.where(_window_bad_matrix(C, arr, windows, margin) > w0, np.inf, cost)
        keys = list(pres)
        Pm = np.stack([pres[v] for v in keys])
        oi = np.array([keys.index(v) for v in owner], dtype=np.int64)
        t_own = arr[np.arange(len(C)), np.argmax(C == np.array(owner, dtype=np.int64)[:, None], axis=1)]
        p_old = Pm[np.arange(len(keys)), slots(np.array([a0[0, pos[v]] for v in keys]))]
        cost = np.where(Pm[oi, slots(t_own)] < p_old[oi] - 1e-12, cost, np.inf)
        if limits is not None:
            ok = limits.allowed(dur, km, base[0], base[1])
            if se is not None:
                rows = np.arange(len(C))
                for v in pres:
                    t = arr[rows, np.argmax(C == v, axis=1)]
                    ok &= t <= max(se, t_ref[v]) + 1e-9
            cost = np.where(ok, cost, np.inf)
        j = int(np.flatnonzero(cost <= cost.min() + 1e-4)[0]) if np.isfinite(cost.min()) else 0   # eşitlikte ilk aday
        if not cost[j] < c0[0] - min_gain:
            break
        v = owner[j]
        i_new = int(np.argmax(C[j] == v))
        t_old, t_new = float(a0[0, pos[v]]), float(arr[j, i_new])
        changes.append({"node": int(v), "move": kind[j], "old_position": int(pos[v]), "new_position": i_new,
                        "old_arrival": t_old, "new_arrival": t_new, "extra_km": float(km[j] - k0[0]), "extra_min": float(dur[j] - d0),
                        "old_p": float(pres[v][slots([t_old])[0]]), "new_p": float(pres[v][slots([t_new])[0]]),
                        "gain_min": float(c0[0] - cost[j])})
        order = C[j].copy()
    return order, changes


def slot_start(d: int) -> int:
    return int(((540,) + BORDERS)[d])


def time_blocked(order: np.ndarray, D: np.ndarray, svc: np.ndarray, pres: dict[int, np.ndarray],
                 windows: dict[int, list[tuple[float, float]]], start: float, mpk: float, scale: float, margin: float,
                 limits: RepairLimits, base: tuple[float, float], known: dict | None = None,
                 t_ref: dict[int, float] | None = None) -> list[dict]:
    """Zaman onarımından sonra hâlâ kötü dilimde kalan bulgu düğümleri ve nedeni (or-opt teşhisi).

    "Kaydırılamadı": varış dilimindeki tahmini bulunamama, bulgunun en iyi diliminden en az `limits.blocked_diff` yüksek.
    neden: no_good_hour (rota bu adrese uygun dilimde uğramıyor) | after_shift (uygun saat vardiya bitişinden sonra) |
    route_duration | bant | km | pencere (uygun yere taşımak bu kısıtı bozardı) | gain_insufficient (km maliyeti beklenen kazancı aşar).
    min_extra_min / min_extra_km: uygun dilime taşımanın en az ek süresi / km'si (mevcut rotaya göre).
    """
    order = np.asarray(order, dtype=np.int64)
    known = windows if known is None else known
    wmax = limits.wait_max
    se = limits.shift_end(start)
    arr = arrivals(order, D, svc, start, mpk, scale)
    w0 = _bad(arr, order, windows, margin) if windows else 0
    dur_now, km_now = route_duration(order, D, svc, known, start, mpk, scale, wmax)
    cap = limits.cap(base[0])
    pos = {int(v): i for i, v in enumerate(order)}
    out = []
    for v in sorted((int(x) for x in pres if int(x) in pos), key=lambda x: pos[x]):
        tab = np.asarray(pres[v], dtype=float)
        i = pos[v]
        t = float(arr[i])
        p_now = float(tab[slots([t])[0]])
        if p_now - float(tab.min()) < limits.blocked_diff - 1e-9:
            continue
        thr = p_now - limits.blocked_diff + 1e-9
        good_slots = [d for d in range(len(tab)) if tab[d] <= thr]
        best_slot = int(min(good_slots, key=lambda d: (tab[d], d)))
        rest = np.delete(order, i)
        P = np.array([p for p in range(1, len(rest)) if p != i], dtype=np.int64)
        row = {"node": v, "arrival": t, "p_now": p_now, "p_best": float(tab[best_slot]), "good": best_slot, "reason": None,
               "min_extra_min": None, "min_extra_km": None}
        if len(P):
            C = np.array([np.insert(rest, p, v) for p in P], dtype=np.int64)
            A2, KM = _arr_km(C, D, svc, start, mpk, scale)
            tv = A2[np.arange(len(C)), P]
            good = tab[slots(tv)] <= thr
        else:
            good = np.zeros(0, dtype=bool)
        lim_t = max(se, (t_ref or {}).get(v, t)) if se is not None else np.inf
        if not good.any():
            row["reason"] = "after_shift" if se is not None and all(slot_start(d) >= se for d in good_slots) else "no_good_hour"
            out.append(row)
            continue
        shift_ok = good & (tv <= lim_t + 1e-9)
        if not shift_ok.any():
            row["reason"] = "after_shift"
            out.append(row)
            continue
        DUR = _durations(C, A2, KM, svc, known, mpk, wmax)
        NB = _window_bad_matrix(C, A2, windows, margin) if windows else np.zeros(len(C), dtype=np.int64)
        idx = np.flatnonzero(shift_ok)
        j = _first_equal(idx, DUR[idx], KM[idx], 1e-4, tol0=1e-3)
        row["min_extra_min"], row["min_extra_km"] = float(DUR[j] - dur_now), float(KM[j] - km_now)
        dur_ok, km_ok, w_ok = DUR <= cap + 1e-9, KM <= base[1] + limits.max_extra_km + 1e-9, NB <= w0
        if (shift_ok & dur_ok & km_ok & w_ok).any():
            row["reason"] = "gain_insufficient"
        elif not (shift_ok & dur_ok).any():
            band_binding = limits.band_max is not None and cap < base[0] + limits.max_extra_min - 1e-9
            row["reason"] = "band" if band_binding else "route_duration"
        elif not (shift_ok & dur_ok & km_ok).any():
            row["reason"] = "km"
        else:
            row["reason"] = "window"
        out.append(row)
    return out


def expected_time_fails(order: np.ndarray, D: np.ndarray, svc: np.ndarray, pres: dict[int, np.ndarray], start: float,
                        mpk: float, scale: float) -> float:
    """Bulgu düğümlerinde beklenen bulunamama (durak) toplamı."""
    if not pres:
        return 0.0
    order = np.asarray(order, dtype=np.int64)
    arr = arrivals(order, D, svc, start, mpk, scale)
    pos = {int(v): i for i, v in enumerate(order)}
    return float(sum(t[slots([arr[pos[v]]])[0]] for v, t in pres.items() if v in pos))


def plan_route(xy: np.ndarray, depot_xy: np.ndarray, plain_addrs: np.ndarray, base_svc: np.ndarray,
               rules: dict[int, StopRule], *, road_factor: float, mpk: float, start: float, scale: float, margin: float,
               defer_closed: bool = True, window_repair: bool = True, service_correction: bool = True,
               time_repair: bool = False, revisit_min: float = 10.0, km_cost_min: float = 0.8, min_gain_min: float = 0.5,
               limits: RepairLimits | None = None) -> dict:
    """Hafızasız (düz) sıradan hafızalı rotayı kurar.

    xy: (n, 2) duraklar plain_addrs sırasında (km); base_svc: (n,) taban servis dk. rules: adres → StopRule.
    time_repair: StopRule.presence taşıyan duraklar için zaman onarımı (Faz 2b; pencere onarımından sonra).
    limits: onarımların sert kısıtı (Faz 2c); None → kısıtsız (Faz 2b davranışı, yalnız testler).
    Dönüş: {"order": hafızalı adres sırası, "deferred": [(adres, tür, kayıt)], "km", "planned", "plain_km",
            "plain_planned", "changes": [...], "extra": {address: dk}, "time_fail": {"once", "sonra", "bulgu"},
            "limits": {before_min, after_min, before_km, after_km, border_min, ...} | None, "time_blocked": [...], "ctx": {...}}.
    `changes[].old_order / new_order` 1 tabanlı durak sırasıdır (o hamleden hemen önceki / sonraki rotada).
    "Onarım öncesi" = erteleme sonrası, servis düzeltmeli, düz sıra (servis düzeltmesi sırayı değiştirmez, yalnız tahmini düzeltir).
    """
    plain_addrs = np.asarray(plain_addrs, dtype=np.int64)
    n = len(plain_addrs)
    pts = np.vstack([np.asarray(depot_xy, dtype=float)[None, :], np.asarray(xy, dtype=float).reshape(n, 2)])
    D = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)) * road_factor
    svc0 = np.concatenate([[0.0], np.asarray(base_svc, dtype=float)])
    extra = np.zeros(n + 1)
    if service_correction:
        for i, a in enumerate(plain_addrs):
            r = rules.get(int(a))
            if r is not None:
                extra[i + 1] = r.extra
    svc = svc0 + extra
    plain_order = np.concatenate([[0], np.arange(1, n + 1), [0]])
    plain_km = route_km(plain_order, D)
    plain_planned = plain_km * mpk + float(svc0.sum())
    deferred, keep = [], []
    for i, a in enumerate(plain_addrs):
        r = rules.get(int(a))
        if defer_closed and r is not None and r.closed:
            k = r.kinds.index(r.closed)
            deferred.append((int(a), r.closed, r.sources[k]))
        else:
            keep.append(i + 1)
    order = np.array([0] + keep + [0], dtype=np.int64)
    changes: list[dict] = []
    known: dict[int, list[tuple[float, float]]] = {}
    for v in keep:
        r = rules.get(int(plain_addrs[v - 1]))
        if r is not None and r.windows:
            known[v] = r.windows
    windows = known if window_repair else {}
    wmax = limits.wait_max if limits is not None else 0.0
    # Beklenen bekleme güvenlik paylı pencereyle: [başlangıç − pay, bitiş + pay) içinde varış → min(bitiş + pay − varış, üst sınır).
    # Neden: beklenen varış belirsizdir (pencere onarımı da aynı payla "pencereye düşüyor" der); paysız bekleme gerçekleşen
    # beklemeyi küçük gösterir ve faydalı taşımaları reddeder.
    wm = margin if limits is None or limits.wait_margin is None else limits.wait_margin
    kwin = {v: [(lo - wm, hi + wm) for lo, hi in ws] for v, ws in known.items()}
    base = route_duration(order, D, svc, kwin, start, mpk, scale, wmax) if limits is not None else None
    if window_repair:
        order, ch = repair_windows(order, D, svc, windows, start, mpk, scale, margin, limits=limits, base=base, known=kwin)
        for c in ch:
            a = int(plain_addrs[c["node"] - 1])
            r = rules[a]
            changes.append({"type": "window", "address": a, "old_order": c["old_position"], "new_order": c["new_position"],
                            "old_arrival": round(c["old_arrival"]), "new_arrival": round(c["new_arrival"]),
                            "extra_km": round(c["extra_km"], 3), "extra_min": round(c["extra_min"], 1), "window": [int(x) for x in r.windows[0]],
                            "record": r.sources[r.kinds.index("lunch_break")] if "lunch_break" in r.kinds else None})
    pres = {}
    for v in keep:
        r = rules.get(int(plain_addrs[v - 1]))
        if r is not None and r.presence is not None:
            pres[v] = np.asarray(r.presence, dtype=float)
    tf0 = expected_time_fails(order, D, svc, pres, start, mpk, scale)
    blocked: list[dict] = []
    if time_repair and pres:
        # Zaman onarımının tabanı = pencere onarımı SONRASI rota: zaman onarımı pencere onarımının kazandırdığı süreyi de
        # harcayamaz (zaman-farkında rota ≤ zamansız rota ≤ onarım öncesi).
        # Zaman hamlesi pencere onarımı sonrası rotayı ne süre ne km olarak uzatabilir (km toleransı 0): zaman onarımı sürüşü
        # yalnız tahmini bekleme kazancıyla "satın alamaz"; km toleransı yalnız öğle beklemesini kısaltan pencere taşımasınındır.
        base_t = route_duration(order, D, svc, kwin, start, mpk, scale, wmax) if limits is not None else None
        lim_t = replace(limits, max_extra_km=0.0) if limits is not None else None
        a_ref = arrivals(order, D, svc, start, mpk, scale)
        t_ref = {int(v): float(a_ref[i]) for i, v in enumerate(order) if int(v) in pres}
        # Zaman onarımı bilinen öğle durağını pencerenin geniş payına (bekleme payı) sokamaz: gerçekleşen varış sapar.
        mt = max(margin, wm) if limits is not None else margin
        order, ch = repair_times(order, D, svc, pres, windows, start, mpk, scale, mt, revisit_min, km_cost_min, min_gain_min,
                                 limits=lim_t, base=base_t, known=kwin)
        for c in ch:
            a = int(plain_addrs[c["node"] - 1])
            changes.append({"type": "time", "address": a, "move": c["move"], "old_order": c["old_position"],
                            "new_order": c["new_position"], "old_arrival": round(c["old_arrival"]), "new_arrival": round(c["new_arrival"]),
                            "extra_km": round(c["extra_km"], 3), "extra_min": round(c["extra_min"], 1), "old_p": round(c["old_p"], 3),
                            "new_p": round(c["new_p"], 3), "gain_min": round(c["gain_min"], 1)})
        if limits is not None:
            for b in time_blocked(order, D, svc, pres, windows, start, mpk, scale, mt, lim_t, base_t, kwin, t_ref):
                v = b.pop("node")
                blocked.append({**b, "address": int(plain_addrs[v - 1]), "arrival": round(b["arrival"]),
                                "p_now": round(b["p_now"], 3), "p_best": round(b["p_best"], 3),
                                "min_extra_min": None if b["min_extra_min"] is None else round(b["min_extra_min"], 1),
                                "min_extra_km": None if b["min_extra_km"] is None else round(b["min_extra_km"], 3)})
    tf1 = expected_time_fails(order, D, svc, pres, start, mpk, scale)
    km = route_km(order, D)
    addrs = plain_addrs[order[1:-1] - 1]
    planned = km * mpk + float(svc[order[1:-1]].sum())
    ex = {int(plain_addrs[i - 1]): float(extra[i]) for i in order[1:-1] if extra[i] > 0}
    lim = None
    if limits is not None:
        d1, _ = route_duration(order, D, svc, kwin, start, mpk, scale, wmax)
        lim = {"before_min": round(base[0], 2), "after_min": round(d1, 2), "before_km": round(base[1], 3), "after_km": round(km, 3),
               "border_min": round(limits.cap(base[0]), 2), "tolerance_min": limits.max_extra_min, "tolerance_km": limits.max_extra_km,
               "band_min": limits.band_max}
    nodes = order[1:-1]
    ctx = {"addrs": [int(a) for a in addrs], "xy": pts[nodes].tolist(), "svc": svc[nodes].tolist(), "depot": pts[0].tolist(),
           "windows": {int(plain_addrs[v - 1]): [list(w) for w in ws] for v, ws in known.items() if v in set(nodes.tolist())},
           "presence": {int(plain_addrs[v - 1]): t.tolist() for v, t in pres.items()}}
    return {"order": addrs, "deferred": deferred, "km": km, "planned": planned, "plain_km": plain_km,
            "plain_planned": plain_planned, "changes": changes, "extra": ex,
            "time_fail": {"before": round(tf0, 3), "after": round(tf1, 3), "finding": len(pres)},
            "limits": lim, "time_blocked": blocked, "ctx": ctx}


# ---------------------------------------------------------------------------------------------- kaydırılamayan bulgu (Faz 2c)
def _ctx_eval(ctx: dict, road_factor: float, mpk: float, start: float, scale: float, margin: float, wait_max: float,
              extra: tuple[list, list, float] | None = None, wait_margin: float | None = None):
    """Bir rota bağlamının (ctx) mevcut hâli ve isteğe bağlı bir durağın her konuma eklenmiş adayları.

    extra = (xy, presence tablosu | None, servis dk): eklenecek durak. Dönüş: (km, dur, window_bad, pres_fail, tv, P);
    dizilerin 0. elemanı mevcut sıra, 1.. elemanları ekleme adayları (P: ekleme konumu, tv: eklenen durağın beklenen varışı).
    Düğüm 0 depo, 1..n mevcut duraklar, n+1 eklenen.
    """
    addrs = list(ctx["addrs"])
    n = len(addrs)
    pts = [ctx["depot"]] + list(ctx["xy"])
    svc = [0.0] + list(ctx["svc"])
    win = {i + 1: [tuple(w) for w in ctx["windows"][a]] for i, a in enumerate(addrs) if a in ctx["windows"]}
    wm = margin if wait_margin is None else wait_margin
    wwin = {k: [(lo - wm, hi + wm) for lo, hi in ws] for k, ws in win.items()}     # bekleme: plan_route ile aynı pay
    pres = {i + 1: np.asarray(ctx["presence"][a], dtype=float) for i, a in enumerate(addrs) if a in ctx["presence"]}
    if extra is not None:
        pts.append(list(extra[0]))
        svc.append(float(extra[2]))
        if extra[1] is not None:
            pres[n + 1] = np.asarray(extra[1], dtype=float)
    P = np.asarray(pts, dtype=float)
    D = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1)) * road_factor
    svc = np.asarray(svc, dtype=float)
    base = np.array([0] + list(range(1, n + 1)) + [0], dtype=np.int64)
    pos = np.arange(1, n + 2, dtype=np.int64) if extra is not None else np.zeros(0, dtype=np.int64)

    def ev(C):
        arr, km = _arr_km(C, D, svc, start, mpk, scale)
        dur = _durations(C, arr, km, svc, wwin, mpk, wait_max)
        wb = _window_bad_matrix(C, arr, win, max(margin, wm)) if win else np.zeros(len(C), dtype=np.int64)
        pf = np.zeros(len(C))
        r_ = np.arange(len(C))
        for v, tab in pres.items():
            hit = C == v
            t = arr[r_, np.argmax(hit, axis=1)]
            pf += np.where(hit.any(1), tab[slots(t)], 0.0)
        return arr, km, dur, wb, pf

    _, km, dur, wb, pf = ev(base[None, :])
    tv = np.zeros(0)
    if len(pos):
        C1 = np.array([np.insert(base, p, n + 1) for p in pos], dtype=np.int64)
        a1, k1, d1, w1, f1 = ev(C1)
        km, dur, wb, pf = (np.concatenate([x, y]) for x, y in ((km, k1), (dur, d1), (wb, w1), (pf, f1)))
        tv = a1[np.arange(len(C1)), pos]
    return km, dur, wb, pf, tv, pos


def _ctx_without(ctx: dict, a: int) -> dict:
    i = ctx["addrs"].index(a)
    return {**ctx, "addrs": ctx["addrs"][:i] + ctx["addrs"][i + 1:], "xy": ctx["xy"][:i] + ctx["xy"][i + 1:],
            "svc": ctx["svc"][:i] + ctx["svc"][i + 1:], "windows": {k: v for k, v in ctx["windows"].items() if k != a},
            "presence": {k: v for k, v in ctx["presence"].items() if k != a}}


def _ctx_with(ctx: dict, p: int, a: int, xy, svc: float, tab, win) -> dict:
    i = p - 1
    out = {**ctx, "addrs": ctx["addrs"][:i] + [a] + ctx["addrs"][i:], "xy": ctx["xy"][:i] + [list(xy)] + ctx["xy"][i:],
           "svc": ctx["svc"][:i] + [float(svc)] + ctx["svc"][i:], "windows": dict(ctx["windows"]),
           "presence": dict(ctx["presence"])}
    if tab is not None:
        out["presence"][a] = list(tab)
    if win:
        out["windows"][a] = win
    return out


def time_alternatives(routes: dict, *, road_factor: float, mpk: float, start: float, scale: float, margin: float,
                         limits: RepairLimits, min_gain: float = 0.05) -> list[dict]:
    """Kısıt yüzünden kaydırılamayan bulgular için sırayla alternatif (simülatör ve ajan AYNI fonksiyonu çağırır).

    routes: rota anahtarı → plan_route çıktısı (ctx + time_blocked). Her kaydırılamayan bulgu için (anahtar ve rota sırasıyla):
    (i) aynı rota içinde kısıt dahilinde yer zaten denendi (`time_blocked.reason` neden olmadığını söyler);
    (ii) aktarma: o saatte bölgeden geçen başka bir rotaya ekleme. Kısıt iki rotada birlikte: toplam beklenen süre ve km onarım
         öncesinden fazla artmaz, hedef rota bandı aşmaz (zaten aşıyorsa aktarma yok), durak hedefte vardiya bitişinden önce,
         iki rotada pencere ihlali artmaz, toplam beklenen bulunamama en az `min_gain` durak düşer. Kabul edilen aktarma sonraki
         aramalarda hesaba katılır (öneriler birlikte uygulanabilir);
    (iii) aktarma yoksa: uygun saat vardiya içindeyse ertesi gün o dilimde planlama, değilse akşam teslimi / teslim noktası
         önerisi. Hepsinde alıcıya önceden SMS önerilir; karar müdürdedir (simülasyonda uygulanmaz, ölçülen etkide yoktur).
    """
    ctxs = {k: routes[k]["ctx"] for k in routes}
    se = limits.shift_end(start)
    ev = dict(road_factor=road_factor, mpk=mpk, start=start, scale=scale, margin=margin, wait_max=limits.wait_max,
              wait_margin=limits.wait_margin)
    out = []
    for ka in sorted(routes):
        for b in routes[ka].get("time_blocked") or []:
            a = int(b["address"])
            A = ctxs[ka]
            if a not in A["addrs"]:
                continue
            i = A["addrs"].index(a)
            xy, svc_a = A["xy"][i], float(A["svc"][i])
            tab = np.asarray(A["presence"][a], dtype=float)
            win = A["windows"].get(a)
            kmA, durA, wbA, pfA, _, _ = _ctx_eval(A, **ev)
            A2 = _ctx_without(A, a)
            kmA2, durA2, wbA2, pfA2, _, _ = _ctx_eval(A2, **ev)
            best = None
            if wbA2[0] <= wbA[0]:
                thr = float(b["p_now"]) - limits.blocked_diff + 1e-9
                for kb in sorted(ctxs):
                    if kb == ka:
                        continue
                    Bc = ctxs[kb]
                    if not Bc["addrs"]:
                        continue
                    if min(float(np.hypot(x - xy[0], y - xy[1])) for x, y in Bc["xy"]) * road_factor > 3.0:
                        continue
                    km, dur, wb, pf, tv, P = _ctx_eval(Bc, extra=(xy, tab, svc_a), **ev)
                    if limits.band_max is not None and dur[0] > limits.band_max:
                        continue
                    pv = tab[slots(tv)]
                    d_dur = (dur[1:] + durA2[0]) - (dur[0] + durA[0])
                    d_km = (km[1:] + kmA2[0]) - (km[0] + kmA[0])
                    gain = (pf[0] + pfA[0]) - (pf[1:] + pfA2[0])
                    ok = (pv <= thr) & (d_dur <= limits.max_extra_min + 1e-9) & (d_km <= 1e-9)     # zaman hamlesi: km de artmaz
                    ok &= wb[1:] <= wb[0]
                    ok &= gain >= min_gain - 1e-9
                    if limits.band_max is not None:
                        ok &= dur[1:] <= limits.band_max + 1e-9
                    if se is not None:
                        ok &= tv <= se + 1e-9
                    if win:
                        ok &= ~np.any([(lo - margin <= tv) & (tv < hi + margin) for lo, hi in win], axis=0)
                    for j in np.flatnonzero(ok):
                        key = (-round(float(gain[j]), 6), round(float(d_km[j]), 6))
                        if best is None or key < best[0]:
                            best = (key, kb, int(P[j]), float(tv[j]), float(pv[j]), float(d_dur[j]), float(d_km[j]),
                                    float(dur[1 + j]), float(durA2[0]), float(gain[j]))
            row = {"address": a, "source": ka, "reason": b["reason"], "arrival": b["arrival"], "p_now": b["p_now"],
                   "good": int(b["good"]), "good_slot": SLOT_NAMES[int(b["good"])], "min_extra_min": b.get("min_extra_min"),
                   "sms": True, "decision": "manager"}
            if best is not None:
                _, kb, p, tv, pv, ddur, dkm, durB2, durA2V, g = best
                row.update(option="transfer", target=kb, target_order=p, target_arrival=round(tv), target_p=round(pv, 3),
                           extra_min_total=round(ddur, 1), extra_km_total=round(dkm, 3), target_duration_after=round(durB2, 1),
                           source_duration_after=round(durA2V, 1), gain_stop=round(g, 3))
                ctxs[ka] = A2
                ctxs[kb] = _ctx_with(ctxs[kb], p, a, xy, svc_a, tab, win)
            else:
                ok_shift = se is None or slot_start(int(b["good"])) < se
                row.update(option="next_day" if ok_shift else "evening_delivery_point", target=None)
            out.append(row)
    return out

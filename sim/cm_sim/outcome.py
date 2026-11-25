"""Sonuç modeli: bir rotanın gün içinde yürütülmesi.

Durak = adres. Bilgiye bağlı başarısızlık durağın tamamını etkiler (giriş bulunamazsa hiçbir gönderi
teslim edilemez). Alıcı yokluğu (Faz 2b) durak düzeyindedir ve VARIŞ SAATİNE bağlıdır: adresin gizli bulunabilirlik
profili (`world.p_absent`) o saatte kapıda kimse olmama olasılığını verir; kimse yoksa duraktaki tüm gönderiler "alıcı yok"
olur. Bilgi (not/ipucu) bunu önlemez; doğru saatte gitmek önler (teslim zamanı analizi, `cm_sim.delivery_time`).
`presence.enabled=false` iken eski model: gönderi düzeyinde, saatten bağımsız `outcome.p0`.

Kapalı türler (saturday_closed, temporary_closed) kapıda bilindiğinde durak "planlı erteleme" olur; deneme
sayılmaz ama yol harcanmıştır (boşuna gidiş). Bilinmediğinde boşuna deneme yapılır ve başarısız olur. Hafıza-
farkında plan (kol D) bu durakları plandan çıkarır: yola hiç çıkılmaz (`plan_deferred_result`). Hafıza yanılıyorsa
(durak aslında açık) gönderi o gün teslim edilmez: başarısız sayılır (`wrong_deferral`).

Öğle arası: bilinse bile kurye pencerenin İÇİNDE gelirse kapı açılmaz. Bilen kurye bekler ya da sonra döner
(ek dakika, `lunch_wait_max` üst sınırı); bilmeyen başarısız olur. Bilgi ancak rota/zamanlama pencereyi önlerse
bedavadır. (Faz 1'de bilinen öğle arası pencere içinde de sorunsuz teslim sayılıyordu; düzeltildi.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import Config
from .couriers import Courier
from .history import Familiarity
from .planning import Route
from .policies.base import HintView
from .rng import N_QUIRK_SLOTS, DayStreams
from .world import Quirk, World, p_absent

CLOSED_KINDS = ("saturday_closed", "temporary_closed")
REASON_OF_KIND = {
    "back_entry": "entry_failed", "safety": "entry_failed",
    "saturday_closed": "closed", "lunch_break": "closed", "temporary_closed": "closed",
    "bell": "recipient_unreachable", "reception": "recipient_unreachable",
    "position_wrong": "address_not_found", "roadwork": "address_not_found",
}
REASONS = ("recipient_absent", "address_not_found", "closed", "entry_failed", "recipient_unreachable", "wrong_deferral", "other")
PREVENTABLE = ("address_not_found", "closed", "entry_failed", "recipient_unreachable", "wrong_deferral")


@dataclass
class StopResult:
    address: int
    block: int
    n: int
    arrival: float
    service: float
    ok: int = 0
    fail: int = 0
    deferred: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    preventable_fail: int = 0
    unfamiliar: bool = False
    familiarity: float = 0.0
    hinted: bool = False            # en az bir ipucu verildi
    hint_helped: bool = False       # geçerli ipucu cezayı kaldırdı
    wrong_hint: bool = False        # yanlış/bayat ipucu ya da bayat kişisel bilgi
    encountered: list[tuple[int, Quirk]] = field(default_factory=list)   # (slot, quirk)
    hint_texts: list[str] = field(default_factory=list)
    window_hit: bool = False        # öğle arası olan adrese pencere içinde varıldı
    window_wait: float = 0.0        # bilinen öğle arası yüzünden bekleme/geri dönüş dakikası
    wasted: bool = False            # kapalı kapıya gidildi (kapıda erteleme ya da "kapalı" başarısızlığı)
    plan_deferred: bool = False     # hafıza-farkında plan durağı plandan çıkardı (yola çıkılmadı)


@dataclass
class RouteResult:
    route_id: int
    courier: str
    stops: list[StopResult]
    km: float
    minutes: float                  # gerçekleşen toplam süre (yol + kapı)
    end_minute: float
    plan_deferred: list[StopResult] = field(default_factory=list)   # planda ertelenen duraklar (rota dışı)
    start_minute: float = 540.0     # Faz 5: şubeden çıkış (gece yarısından dk); minutes = end_minute − start_minute


def _in_window(cfg: Config, q: Quirk, weekday: int, arrival: float) -> bool:
    w = cfg.quirks.effects[q.kind].window
    if w == "saturday":
        return weekday == 5
    if w == "lunch":
        lo, hi = cfg.quirks.lunch_window
        return lo <= arrival < hi
    return True


def execute_route(cfg: Config, world: World, route: Route, courier: Courier, day: int, weekday: int,
                  counts: np.ndarray, st: DayStreams, fam: Familiarity,
                  known: dict[tuple[int, int], int], hints: dict[int, list[HintView]] | None,
                  start: float | None = None) -> RouteResult:
    """start: şubeden çıkış dakikası (Faz 5 sabah modeli); verilmezse planning.start_minute."""
    oc = cfg.outcome
    pos = world.depot_xy
    t0 = float(cfg.planning.start_minute) if start is None else float(start)
    t = t0
    km_total = 0.0
    results: list[StopResult] = []
    mpk = cfg.planning.minutes_per_km
    rf = cfg.planning.road_factor
    for a in route.stops:
        a = int(a)
        xy = world.addr_xy[a]
        leg = float(np.sqrt(((xy - pos) ** 2).sum())) * rf
        km_total += leg
        t += leg * mpk
        pos = xy
        b = int(world.addr_block[a])
        n = int(counts[a])
        f = fam.value(courier.id, b, day)
        res = StopResult(address=a, block=b, n=n, arrival=t, service=0.0, familiarity=f,
                         unfamiliar=f < cfg.familiarity.unfamiliar_below)
        h_list = (hints or {}).get(a, [])
        res.hinted = bool(h_list)
        res.hint_texts = [h.text for h in h_list]

        comp: list[tuple[str, float]] = []          # (neden, olasılık katkısı)
        base = float(world.block_difficulty[b])
        comp.append(("other", base))
        comp.append(("address_not_found", base * oc.eta_nav * (1.0 - f)))
        extra_min = oc.nav_min * (1.0 - f)
        deferred = False
        active_kinds: set[str] = set()
        wrong = False
        for j, q in enumerate(world.quirks_by_addr[a][:N_QUIRK_SLOTS - 1]):
            if not q.active(day):
                continue
            active_kinds.add(q.kind)
            if not _in_window(cfg, q, weekday, t):
                continue
            eff = cfg.quirks.effects[q.kind]
            if eff.window == "lunch":
                res.window_hit = True
            cur = q.version(day)
            kv = known.get((a, q.id))
            q_hints = [h for h in h_list if h.kind == q.kind]
            complied = bool(q_hints) and st.u_comply[a, j] < cfg.memory.compliance
            if kv == cur:
                handled = True
            elif complied and any(h.truth_version == cur for h in q_hints):
                handled = True
                res.hint_helped = True
            else:
                handled = False
            if handled:
                if q.kind in CLOSED_KINDS:
                    deferred = True
                elif eff.window == "lunch":
                    wait = max(0.0, min(float(cfg.quirks.lunch_window[1]) - t, cfg.quirks.lunch_wait_max))
                    extra_min += wait
                    res.window_wait += wait
                extra_min += eff.known_minutes
                continue
            comp.append((REASON_OF_KIND[q.kind], eff.fail))
            extra_min += eff.minutes
            res.encountered.append((j, q))
            if kv is not None or complied:
                wrong = True
        # Adreste karşılığı olmayan ipuçları (yanlış adres/tür ya da süresi bitmiş) kuryeyi yanıltır.
        for h in h_list:
            if h.kind not in active_kinds and st.u_comply[a, N_QUIRK_SLOTS - 1] < cfg.memory.compliance:
                wrong = True
        if wrong:
            comp.append(("address_not_found", oc.delta_wrong))
            extra_min += oc.tau_wrong
            res.wrong_hint = True

        if deferred:
            res.deferred = n
            res.service = 0.0
            res.wasted = True
            results.append(res)
            continue

        # Beceri bilgiye bağlı bileşenin tamamını ölçekler: becerikli kurye bilmediği adreste de yolunu daha iyi bulur.
        p_k = min(0.95, courier.skill * sum(c for _, c in comp))
        svc = (oc.service_per_stop + oc.service_per_shipment * n) * courier.speed + extra_min
        res.service = svc
        t += svc
        if st.u_stop[a] < p_k:
            # Neden: bileşenlerin payına göre CRN ile seçilir.
            tot = sum(c for _, c in comp)
            x = st.u_cause[a] * tot
            reason = comp[-1][0]
            acc = 0.0
            for r, c in comp:
                acc += c
                if x < acc:
                    reason = r
                    break
            res.fail = n
            res.reasons[reason] = n
            if reason in PREVENTABLE:
                res.preventable_fail = n
            if reason == "closed":
                res.wasted = True
        else:
            off = int(st.ship_offset[a])
            if cfg.presence.enabled:
                # Durak düzeyi: kapıda kimse yoksa hiçbir gönderi teslim edilemez (adresin ilk gönderi sayısı CRN olarak).
                absent = n if st.u_ship[off] < p_absent(cfg, world, a, weekday, res.arrival) else 0
            else:
                absent = int(np.sum(st.u_ship[off:off + n] < oc.p0[world.addr_kind[a]]))
            res.fail = absent
            res.ok = n - absent
            if absent:
                res.reasons["recipient_absent"] = absent
        results.append(res)
    leg = float(np.sqrt(((world.depot_xy - pos) ** 2).sum())) * rf
    km_total += leg
    t += leg * mpk
    pd = [plan_deferred_result(cfg, world, int(a), day, weekday, counts, fam, courier)
          for a in (route.extra.get("deferred_addrs") or [])]
    return RouteResult(route_id=route.id, courier=courier.id, stops=results, km=km_total,
                       minutes=t - t0, end_minute=t, plan_deferred=pd, start_minute=t0)


def plan_deferred_result(cfg: Config, world: World, a: int, day: int, weekday: int, counts: np.ndarray,
                         fam: Familiarity, courier: Courier) -> StopResult:
    """Hafıza "bugün kapalı" dediği için plandan çıkarılan durak. Gerçekten kapalıysa doğru erteleme (deneme sayılmaz,
    yol harcanmaz); açıksa gönderi o gün kaçırılmıştır: başarısız (`wrong_deferral`, bilgiyle önlenebilir)."""
    b = int(world.addr_block[a])
    n = int(counts[a])
    f = fam.value(courier.id, b, day)
    res = StopResult(address=a, block=b, n=n, arrival=-1.0, service=0.0, familiarity=f,
                     unfamiliar=f < cfg.familiarity.unfamiliar_below, plan_deferred=True)
    closed = any(q.active(day) and q.kind in CLOSED_KINDS and _in_window(cfg, q, weekday, 0.0)
                 for q in world.quirks_by_addr[a][:N_QUIRK_SLOTS - 1])
    if closed:
        res.deferred = n
    else:
        res.fail = n
        res.reasons["wrong_deferral"] = n
        res.preventable_fail = n
    return res

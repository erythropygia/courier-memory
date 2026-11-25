"""Teslim zamanı analizi (Faz 2b): kayıtlardan, not olmadan "bu adreste hangi saatte kimse yok?".

Girdi yalnız gözlemlenebilir teslim kaydıdır: (gün, adres, varış dakikası, sonuç). Sonuç "teslim" ya da "alıcı yok";
bilgiye bağlı başarısızlık (adres bulunamadı, giriş …) ve ertelenen durak bulunabilirliği sınamadığı için sayılmaz.
Yalnız hedef günden ÖNCEKİ kayıtlar kullanılır (gelecek sızıntısı yok).

Model (açıklanabilir, iki düzeyli Beta-Binom büzme):
1. Adres türünün dilim şekli: q[tür, dilim] = türdeki tüm adreslerin o dilimdeki bulunamama oranı; q̄[tür] genel oran.
2. Adresin genel oranı: p̄ = (bulunamadı + κa·q̄) / (deneme + κa)     (az veride türün ortalamasına çekilir)
3. Dilim oranı: önce m = p̄ · q[d] / q̄ ; p[d] = (bulunamadı_d + κs·m) / (deneme_d + κs)   (az veride adresin genel oranına)

Bulgu ("pencere"): verisi olan (≥ min_att_bad deneme, ≥ min_abs_bad kendi "alıcı yok" kaydı) en kötü dilim oranı ≥
min_bad_rate ve verisi olan (≥ min_att_good) en iyi
dilimden en az min_diff kötü; güven = P(p_kötü > p_iyi) (Beta sonsallarıyla, ızgara üzerinde sayısal). Önerilen dilimin
adreste kendi kanıtı olmalıdır; yalnız öncel yetmez. Kötü dilim belli ama başka saatte veri yoksa bulgu "teyit": rotaya girmez,
hasat sorusuna dönüşebilir ("Bu adreste öğlen kimse yok gibi, doğru mu?").

Simülatör (kol D) ve ajan (`agents.delivery_time`) AYNI fonksiyonları çağırır; sayımlar tamsayıdır, sonuç birebir aynıdır.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import beta as _beta

BORDERS = (720, 840, 960, 1080)                 # dilim sınırları (dk): 12:00, 14:00, 16:00, 18:00
SLOT_NAMES = ("09–12", "12–14", "14–16", "16–18", "18 sonrası")
SLOT_MID = (630, 780, 900, 1020, 1110)       # yalnız ölçüm (gizli gerçekle doğrulama) için temsilî dakika
N_SLOT = len(SLOT_NAMES)
DAY_TYPES = ("weekdays", "saturday")
LEVEL_ORDER = {"low": 0, "mid": 1, "high": 2}
_U = (np.arange(1000) + 0.5) / 1000.0             # P(X1 > X2) = E[F2(X1)] = ∫ F2(Q1(u)) du (orta nokta kuralı)


def slot(minute: float) -> int:
    return int(np.searchsorted(BORDERS, float(minute), side="right"))


def slots(minutes: np.ndarray) -> np.ndarray:
    return np.searchsorted(np.asarray(BORDERS, dtype=float), np.asarray(minutes, dtype=float), side="right")


def day_type(weekday: int) -> int:
    return 1 if int(weekday) == 5 else 0


class TimeRecord:
    """Adres × gün tipi × dilim deneme/bulunamadı sayıları + ham kayıt (dışa aktarım ve demo geçmişi için)."""

    def __init__(self, n_addresses: int):
        self.att = np.zeros((n_addresses, 2, N_SLOT), dtype=np.int32)
        self.abs = np.zeros((n_addresses, 2, N_SLOT), dtype=np.int32)
        self.log: list[tuple[int, int, int, int]] = []          # (gün, adres, varış dk, bulunamadı 0/1)

    def add(self, day: int, address: int, weekday: int, minute: int, absent: bool) -> None:
        g, d = day_type(weekday), slot(minute)
        self.att[address, g, d] += 1
        if absent:
            self.abs[address, g, d] += 1
        self.log.append((int(day), int(address), int(minute), int(bool(absent))))


def counts_from_log(n_addresses: int, days, addrs, minutes, absent, before_day: int) -> tuple[np.ndarray, np.ndarray]:
    """Ham kayıttan (sütun dizileri) hedef günden önceki sayımlar. Ajan tarafı bunu kullanır."""
    days = np.asarray(days)
    m = days < before_day
    a = np.asarray(addrs)[m]
    g = (days[m] % 6 == 5).astype(np.int64)
    d = slots(np.asarray(minutes)[m])
    ab = np.asarray(absent)[m].astype(np.int64)
    att = np.zeros((n_addresses, 2, N_SLOT), dtype=np.int32)
    abs_ = np.zeros((n_addresses, 2, N_SLOT), dtype=np.int32)
    np.add.at(att, (a, g, d), 1)
    np.add.at(abs_, (a, g, d), ab)
    return att, abs_


@dataclass(frozen=True)
class Params:
    kappa_address: float = 4.0
    kappa_slot: float = 2.0
    min_att_bad: int = 3
    min_abs_bad: int = 2
    min_att_good: int = 2
    min_bad_rate: float = 0.3
    min_diff: float = 0.25
    conf_high: float = 0.95
    conf_mid: float = 0.85
    confirm_bad_rate: float = 0.5

    @classmethod
    def from_dict(cls, d: dict | None) -> "Params":
        d = d or {}
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


def type_profile(att: np.ndarray, abs_: np.ndarray, kind_idx: np.ndarray, n_kinds: int, g: int) -> tuple[np.ndarray, np.ndarray]:
    """(q[tür, dilim], q̄[tür]): türdeki tüm adreslerin dilim / genel bulunamama oranı (+1/+2 düzeltme)."""
    A = np.zeros((n_kinds, N_SLOT))
    B = np.zeros((n_kinds, N_SLOT))
    np.add.at(A, kind_idx, att[:, g, :])
    np.add.at(B, kind_idx, abs_[:, g, :])
    q = (B + 1.0) / (A + 2.0)
    qbar = (B.sum(1) + 1.0) / (A.sum(1) + 2.0)
    return q, qbar


def posterior(att_a: np.ndarray, abs_a: np.ndarray, q_k: np.ndarray, qbar_k: float, P: Params):
    """Bir adresin (tek gün tipi) dilim sonsalları: (ortalama[D], alfa[D], beta[D], p̄)."""
    att_a = np.asarray(att_a, dtype=float)
    abs_a = np.asarray(abs_a, dtype=float)
    pbar = (abs_a.sum() + P.kappa_address * qbar_k) / (att_a.sum() + P.kappa_address)
    m = np.clip(pbar * q_k / qbar_k, 1e-4, 0.95)
    al = abs_a + P.kappa_slot * m
    be = att_a - abs_a + P.kappa_slot * (1.0 - m)
    return al / (al + be), al, be, float(pbar)


def p_large(a1: float, b1: float, a2: float, b2: float) -> float:
    """P(X1 > X2), X1 ~ Beta(a1, b1), X2 ~ Beta(a2, b2) bağımsız. Nicelik integrali: yoğunluk 0/1 uçta tekil olsa da kararlı."""
    return float(np.clip(_beta.cdf(_beta.ppf(_U, a1, b1), a2, b2).mean(), 0.0, 1.0))


def level(confidence: float, P: Params) -> str:
    return "high" if confidence >= P.conf_high else "mid" if confidence >= P.conf_mid else "low"


def address_finding(att_a: np.ndarray, abs_a: np.ndarray, q_k: np.ndarray, qbar_k: float, P: Params) -> dict | None:
    """Tek adres, tek gün tipi. Bulgu yoksa None. Dönüş: {type: pencere|teyit, kotu, iyi, guven, seviye, tahmin[D], ...}."""
    att_a = np.asarray(att_a)
    if int(att_a.sum()) < P.min_att_bad:
        return None
    mean, al, be, pbar = posterior(att_a, abs_a, q_k, qbar_k, P)
    abs_a = np.asarray(abs_a)
    bad_c = [d for d in range(N_SLOT)
             if att_a[d] >= P.min_att_bad and abs_a[d] >= P.min_abs_bad and mean[d] >= P.min_bad_rate]
    if not bad_c:
        return None
    bad = max(bad_c, key=lambda d: (mean[d], -d))
    good_c = [d for d in range(N_SLOT) if d != bad and att_a[d] >= P.min_att_good and mean[bad] - mean[d] >= P.min_diff]
    base = {"bad": int(bad), "estimate": [round(float(x), 4) for x in mean], "general": round(pbar, 4),
            "attempt": [int(x) for x in att_a], "not_found": [int(x) for x in np.asarray(abs_a)]}
    if not good_c:
        if mean[bad] >= P.confirm_bad_rate:
            return {"type": "confirmation", "good": None, "confidence": None, "level": "low", **base}
        return None
    good = min(good_c, key=lambda d: (mean[d], d))
    g = p_large(al[bad], be[bad], al[good], be[good])
    return {"type": "window", "good": int(good), "confidence": round(g, 4), "level": level(g, P), **base}


def time_findings(att: np.ndarray, abs_: np.ndarray, kind_idx: np.ndarray, n_kinds: int, addrs, weekday: int,
                    P: Params) -> dict[int, dict]:
    """Verilen adresler için bugünkü gün tipinde bulgular (adres → bulgu). att/abs: (n_adres, 2, D) tamsayı sayımlar,
    yalnız hedef günden önceki kayıtlardan."""
    g = day_type(weekday)
    q, qbar = type_profile(att, abs_, kind_idx, n_kinds, g)
    out: dict[int, dict] = {}
    addrs = np.unique(np.asarray(addrs, dtype=np.int64))
    if len(addrs) == 0:
        return out
    tot = att[addrs, g, :].sum(1)
    for a in addrs[tot >= P.min_att_bad]:
        a = int(a)
        k = int(kind_idx[a])
        b = address_finding(att[a, g], abs_[a, g], q[k], float(qbar[k]), P)
        if b is not None:
            b["day_type"] = DAY_TYPES[g]
            out[a] = b
    return out


def fits_route(b: dict, min_level: str) -> bool:
    """Kurallı politika (kol D ve ajanın kurallı yedeği): önerilen saati kanıtlı ve güveni eşik üstü bulgu rotaya girer."""
    return b.get("type") == "window" and LEVEL_ORDER[b["level"]] >= LEVEL_ORDER[min_level]


def proposal_text(b: dict) -> str:
    """"12–14: 0/6 teslim · 16 sonrası: 3/3 → 16 sonrası öner" biçimi."""
    k, i = b["bad"], b.get("good")
    mins, nk = b["attempt"][k], b["not_found"][k]
    s = f"{SLOT_NAMES[k]}: {mins - nk}/{mins} teslim"
    if i is None:
        return s + " · başka saatte kayıt yok → teyit sorusu"
    di, ni = b["attempt"][i], b["not_found"][i]
    return s + f" · {SLOT_NAMES[i]}: {di - ni}/{di} teslim → {SLOT_NAMES[i]} öner"


# ---------------------------------------------------------------------------------------------- Faz 2c: kaydırılamayan bulgu
REASON_TEXT = {
    "no_good_hour": "rota bu adrese uygun saatte uğramıyor",
    "after_shift": "uygun saat vardiya bitişinden sonra",
    "route_duration": "uygun saate taşımak rotayı uzatırdı",
    "band": "uygun saate taşımak vardiya bandını aşardı",
    "km": "uygun saate taşımak km sınırını aşardı",
    "window": "uygun saate taşımak başka bir durağın bilinen öğle arasına denk gelirdi",
    "gain_insufficient": "taşımanın sürüş maliyeti beklenen kazançtan büyük",
}
OPTION_NAME = {"transfer": "başka kuryeye aktarma", "next_day": "ertesi gün uygun saatte",
               "evening_delivery_point": "akşam teslimi / teslim noktası"}


def _hm(t) -> str:
    t = int(round(float(t)))
    return f"{t // 60:02d}:{t % 60:02d}"


def sms_text(arrival: float) -> str:
    """Alıcıya önceden bilgilendirme önerisi (kişisel bilgi içermez; gönderim müdür onayıyla)."""
    lo = max(540, int(round(float(arrival))) - 30)
    hi = lo + 60
    return (f"Gönderiniz bugün yaklaşık {_hm(lo)}–{_hm(hi)} arasında adresinize ulaşacak. Bu saatte adreste olmayacaksanız "
            f"teslim noktasından alma ya da başka gün seçeneği için bu mesajı yanıtlayın.")


def alternative_text(x: dict, label: str, courier_name: str | None = None, target_name: str | None = None,
                     shift_end: float | None = None) -> str:
    """`routing_memory.time_alternatives` satırının tek cümlelik gerekçesi (iz, brifing, API)."""
    reason = REASON_TEXT.get(x.get("reason"), x.get("reason") or "?")
    if x.get("reason") == "after_shift" and shift_end is not None:
        reason += f" ({_hm(shift_end)})"
    if x.get("min_extra_min") is not None and x.get("reason") in ("route_duration", "band", "km"):
        reason += f"; en az {x['min_extra_min']:+.1f} dk"
    head = (f"{label}: {courier_name or 'kurye'} rotasında {_hm(x['arrival'])} (tahmini bulunamama %{round(100 * x['p_now'])}); "
           f"en iyi saat {x['good_slot']} ama aynı rotada kaydırılamadı: {reason} (kural: rota uzamaz, fazla mesai yok).")
    if x["option"] == "transfer":
        return (head + f" Öneri: {target_name or 'başka kurye'} rotasına aktar ({x['target_order']}. sıra, {_hm(x['target_arrival'])}, "
                f"%{round(100 * x['target_p'])}); iki rota toplamı {x['extra_min_total']:+.1f} dk, {x['extra_km_total']:+.2f} km, "
                f"{target_name or 'hedef kurye'} vardiya içinde ({x['target_duration_after']:.0f} dk). Alıcıya önceden SMS. Müdür onayı gerekir.")
    if x["option"] == "next_day":
        return (head + f" Öneri: bugün alıcıya SMS ile tahmini saat bildirilsin; uygun değilse gönderi ertesi gün {x['good_slot']} "
                f"diliminde planlansın. Müdür kararı.")
    return (head + f" Öneri: uygun saat ({x['good_slot']}) vardiya dışında; alıcıya SMS ile teslim noktası ya da akşam teslimi "
            f"seçeneği sunulsun. Müdür kararı.")

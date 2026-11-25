"""Yapılandırma modeli. YAML → pydantic; `--set a.b=c` ezmeleri ve senaryo katmanları."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

PKG_ROOT = Path(__file__).resolve().parents[1]           # sim/
DEFAULT_CONFIG = PKG_ROOT / "config" / "default.yaml"
SCENARIO_DIR = PKG_ROOT / "config" / "scenarios"

ADDRESS_KINDS = ("house", "apartment", "site", "workplace", "collection_point")
BLOCK_KINDS = ("busy_residential", "business_center", "site", "industrial", "rural")
QUIRK_KINDS = (
    "back_entry", "saturday_closed", "lunch_break", "safety", "bell",
    "position_wrong", "reception", "temporary_closed", "roadwork",
)
TEMPORARY_KINDS = ("temporary_closed", "roadwork")


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_dist(d: dict[str, float], allowed: tuple[str, ...], name: str) -> dict[str, float]:
    bad = [k for k in d if k not in allowed]
    if bad:
        raise ValueError(f"{name}: bilinmeyen anahtar(lar) {bad}; izinli: {list(allowed)}")
    if any(v < 0 for v in d.values()):
        raise ValueError(f"{name}: negatif değer olamaz")
    if sum(d.values()) <= 0:
        raise ValueError(f"{name}: toplam sıfırdan büyük olmalı")
    return d


class Days(_M):
    warmup: int = Field(ge=5)
    eval: int = Field(ge=1)


class World(_M):
    center: tuple[float, float]
    width_km: float = Field(gt=1)
    height_km: float = Field(gt=1)
    block_m: float = Field(gt=50)
    addresses: int = Field(ge=200)
    depot_offset_km: tuple[float, float]
    ring_core: float = Field(gt=0, lt=1)
    ring_mid: float = Field(gt=0, lt=1)
    ring_noise: float = Field(ge=0, le=0.5)
    block_kind_mix: dict[Literal["core", "mid", "outer"], dict[str, float]]
    address_weight: dict[str, float]
    address_kind_mix: dict[str, dict[str, float]]
    difficulty_mean: float = Field(gt=0, lt=0.5)
    difficulty_sigma: float = Field(ge=0, le=2)
    recurring_share: float = Field(gt=0, le=1)        # konut adreslerinin düzenli gönderi alan payı
    recurring_sigma: float = Field(ge=0, le=3)        # düzenli adreslerde talep çeşitliliği (lognormal)

    @model_validator(mode="after")
    def _v(self) -> "World":
        for ring, d in self.block_kind_mix.items():
            _check_dist(d, BLOCK_KINDS, f"world.block_kind_mix.{ring}")
        _check_dist(self.address_weight, BLOCK_KINDS, "world.address_weight")
        for bk, d in self.address_kind_mix.items():
            if bk not in BLOCK_KINDS:
                raise ValueError(f"world.address_kind_mix: bilinmeyen blok türü {bk}")
            _check_dist(d, ADDRESS_KINDS, f"world.address_kind_mix.{bk}")
        if self.ring_core >= self.ring_mid:
            raise ValueError("world.ring_core, world.ring_mid'den küçük olmalı")
        return self


class Couriers(_M):
    senior: int = Field(ge=2)
    reserve: int = Field(ge=0)
    skill_sigma: float = Field(ge=0)
    skill_clip: tuple[float, float]
    speed_sigma: float = Field(ge=0)
    speed_clip: tuple[float, float]
    note_propensity_beta: tuple[float, float]
    note_propensity_scale: float = Field(ge=0)


class Shock(_M):
    day: int = Field(ge=0)
    factor: float = Field(gt=0)


class Demand(_M):
    shipments_per_day: int = Field(ge=50)
    sporadic_share: float = Field(ge=0, lt=1)         # gönderilerin seyrek (çoğu tek seferlik) adreslere giden payı
    rate: dict[str, float]
    weekday_factor: list[float] = Field(min_length=6, max_length=6)
    workplace_saturday_factor: float = Field(ge=0)
    shocks: list[Shock] = []

    @field_validator("rate")
    @classmethod
    def _r(cls, v: dict[str, float]) -> dict[str, float]:
        return _check_dist(v, ADDRESS_KINDS, "demand.rate")


class Planning(_M):
    start_minute: int
    target_minutes: float = Field(gt=60)
    band: tuple[float, float]
    travel_per_stop_estimate: float = Field(ge=0)
    road_factor: float = Field(ge=1)
    minutes_per_km: float = Field(gt=0)
    two_opt_passes: int = Field(ge=0)
    kmeans_iters: int = Field(ge=1)
    fixed_absence_rule: Literal["reserve", "split"]
    fixed_zone_slack: float = Field(ge=1.0, le=3.0)
    fixed_zone_weight_exp: float = Field(ge=0.0, le=1.0)
    fixed_zone_demand_drift: float = Field(ge=0.0, le=2.0)
    dynamic_slack: float = Field(ge=1.0, le=1.5)
    anchor_bonus_km: float = Field(ge=0)          # Çekirdek bölge: tanıdık bloktaki durağın kuryesine "yakınlık" bonusu (km × f)
    anchor_alpha: float = Field(ge=0, le=1)        # Küme merkezinin çekirdekte kalma ağırlığı
    anchor_slack: float = Field(ge=1.0, le=1.5)
    anchor_min_f: float = Field(ge=0, le=1)        # Çekirdeğe sayılan en düşük tanıdıklık
    extra_courier_mode: Literal["compact", "zones"] = "zones"   # Ek kurye taşan işi nasıl toplar


class Outcome(_M):
    service_per_stop: float = Field(ge=0)
    service_per_shipment: float = Field(ge=0)
    p0: dict[str, float]
    eta_nav: float = Field(ge=0)
    nav_min: float = Field(ge=0)
    delta_wrong: float = Field(ge=0, le=1)
    tau_wrong: float = Field(ge=0)

    @field_validator("p0")
    @classmethod
    def _p0(cls, v: dict[str, float]) -> dict[str, float]:
        missing = [k for k in ADDRESS_KINDS if k not in v]
        if missing:
            raise ValueError(f"outcome.p0 eksik: {missing}")
        return v


class QuirkEffect(_M):
    fail: float = Field(ge=0, le=1)
    minutes: float = Field(ge=0)
    known_minutes: float = Field(0.0, ge=0)        # bilinse de kalan ek dakika (kimlik işlemi, arkadan dolaşma)
    window: Literal["saturday", "lunch"] | None = None


class Quirks(_M):
    prevalence: dict[str, float]
    prevalence_scale: float = Field(ge=0)
    kinds_by_address: dict[str, dict[str, float]]
    effects: dict[str, QuirkEffect]
    lunch_window: tuple[int, int]
    lunch_wait_max: float = Field(15.0, ge=0)      # bilinen öğle arasına denk gelinirse: bekle ya da sonra dön (dk üst sınırı)
    change_rate: float = Field(ge=0, le=1)
    temporary_rate: float = Field(ge=0, le=1)
    temporary_kinds: dict[str, float]
    temporary_days: tuple[int, int]

    @model_validator(mode="after")
    def _v(self) -> "Quirks":
        missing = [k for k in QUIRK_KINDS if k not in self.effects]
        if missing:
            raise ValueError(f"quirks.effects eksik: {missing}")
        for ak, d in self.kinds_by_address.items():
            if ak not in ADDRESS_KINDS:
                raise ValueError(f"quirks.kinds_by_address: bilinmeyen adres türü {ak}")
            _check_dist(d, QUIRK_KINDS, f"quirks.kinds_by_address.{ak}")
        _check_dist(self.temporary_kinds, TEMPORARY_KINDS, "quirks.temporary_kinds")
        return self


PRESENCE_PROFILES = ("home", "worker", "shop", "office", "reception")


class PresenceProfile(_M):
    weekdays: list[float] = Field(min_length=1)   # saat başına bulunamama olasılığı (presence.hours_start'tan; sonuncusu sonrası)
    saturday: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def _v(self) -> "PresenceProfile":
        if any(not 0 <= x <= 1 for x in self.weekdays + self.saturday):
            raise ValueError("presence.profiles: olasılıklar 0–1 arasında olmalı")
        return self


class Presence(_M):
    """Alıcı/adres bulunabilirliği (gizli gerçek): adres türüne göre saat profili. Alıcı yokluğu varış saatine bağlıdır."""
    enabled: bool = True
    hours_start: int = Field(9, ge=0, le=23)
    profiles: dict[str, PresenceProfile] = {}
    mix: dict[str, dict[str, float]] = {}
    intensity_sigma: float = Field(0.0, ge=0, le=2)
    intensity_max: float = Field(0.95, gt=0, le=1)

    @model_validator(mode="after")
    def _v(self) -> "Presence":
        bad = [k for k in self.profiles if k not in PRESENCE_PROFILES]
        if bad:
            raise ValueError(f"presence.profiles: bilinmeyen profil {bad}; izinli: {list(PRESENCE_PROFILES)}")
        for ak, d in self.mix.items():
            if ak not in ADDRESS_KINDS:
                raise ValueError(f"presence.mix: bilinmeyen adres türü {ak}")
            _check_dist(d, tuple(self.profiles), f"presence.mix.{ak}")
        if self.enabled:
            missing = [k for k in ADDRESS_KINDS if k not in self.mix]
            if missing:
                raise ValueError(f"presence.mix eksik: {missing}")
        return self


class TimeAnalysis(_M):
    """Teslim zamanı analizi (kayıtlardan, notsuz): adres × saat dilimi başarı oranı, iki düzeyli Beta-Binom büzme."""
    kappa_address: float = Field(4.0, gt=0)       # adresin genel bulunamama oranı → adres türü ortalamasına (sanal deneme)
    kappa_slot: float = Field(2.0, gt=0)          # dilim oranı → adresin genel oranına (sanal deneme)
    min_att_bad: int = Field(3, ge=1)             # kötü dilim için en az deneme
    min_abs_bad: int = Field(2, ge=1)             # kötü dilimde adresin kendi en az "alıcı yok" kaydı (yalnız öncel yetmez)
    min_att_good: int = Field(2, ge=1)            # önerilen dilim için en az deneme
    min_bad_rate: float = Field(0.3, ge=0, le=1)  # kötü dilimin tahmini bulunamama oranı en az
    min_diff: float = Field(0.25, ge=0, le=1)     # kötü − iyi en az fark
    conf_high: float = Field(0.95, gt=0, lt=1)    # P(kötü > iyi) ≥ → yüksek güven
    conf_mid: float = Field(0.85, gt=0, lt=1)     # ≥ → orta güven
    confirm_bad_rate: float = Field(0.5, ge=0, le=1)   # iyi dilim verisi yoksa: teyit sorusu eşiği


class Learning(_M):
    p_learn: float = Field(ge=0, le=1)


class Familiarity(_M):
    alpha: float = Field(gt=0, le=1)
    half_life: float = Field(gt=0)
    unfamiliar_below: float = Field(ge=0, le=1)


class Memory(_M):
    parse_accuracy: float = Field(ge=0, le=1)
    compliance: float = Field(ge=0, le=1)
    min_sources: int = Field(ge=1)
    ttl_days: int = Field(ge=1)
    seed_from_warmup: bool
    feedback: bool
    p_feedback: float = Field(ge=0, le=1)
    harvest_per_day: int = Field(0, ge=0)          # proaktif hasat: günde en çok kaç hedefli soru
    harvest_per_senior: int = Field(3, ge=1)       # kıdemli kurye başına günde en çok soru
    p_answer: float = Field(0.8, ge=0, le=1)       # sorulan kıdemlinin bildiği püf noktasını anlatma olasılığı


class Morning(_M):
    """Faz 5: şubede sabah akışı. Mesai planning.start_minute'ta başlar; kurye ancak indirme, ayrıştırma, zimmet ve
    yüklemeden sonra çıkar. Bugünkü süreçte kurye kendi gönderilerini ayrıştırır (~90 dk); ayrıştırma indirme okutmasına
    gömülünce (ajan zinciri: plan önden, okutmada raf talimatı) yalnız zimmet + yükleme kalır (~30 dk). Kapalıyken
    çıkış = mesai başlangıcı (Faz 0–4 modeli, sonuçlar birebir aynı)."""
    enabled: bool = False
    current_min: float = Field(default=90.0, ge=0)               # bugünkü süreç: mesai başından çıkışa (saha bilgisi; VARSAYIM)
    presorted_min: float = Field(default=30.0, ge=0)       # ayrıştırma okutmaya gömülü (saha bilgisi; VARSAYIM)
    deviation_min: float = Field(default=10.0, ge=0)               # kurye başına çıkış dağılımı (normal σ, ±2σ kesik; VARSAYIM)
    presorted_arms: list[Literal["A", "B", "C", "D"]] = ["D"]   # ayrıştırması okutmaya gömülü kollar


class Routing(_M):
    """Hafıza-farkında plan (kol D): hafıza kısıtları planı ve rotayı değiştirir."""
    enabled: bool = True
    defer_closed: bool = True                      # bugün kapalı olduğu bilinen durak plandan çıkar (planda erteleme)
    defer_min_sources: int = Field(2, ge=1)        # erteleme için en az bağımsız kaynak (yanlış erteleme teslimi kaçırır)
    window_repair: bool = True                     # kapalı penceresine denk gelen durak pencere dışına taşınır
    service_correction: bool = True                # bilinen püf noktasının kalan ek süresi plana girer
    extra_service_min: dict[str, float] = {}       # planlayıcının tür başına ek servis varsayımı (dk)
    time_scale: float = Field(1.1, ge=0.5, le=2.0) # planlanan varış → beklenen varış (planlanandan yavaş gidilir)
    window_margin_min: float = Field(10.0, ge=0)   # pencereye güvenlik payı (dk)
    time_aware: bool = True                        # teslim zamanı bulgusu olan durak, bulunma olasılığı yüksek saate kaydırılır
    time_min_confidence: Literal["low", "mid", "high"] = "mid"   # rotaya alınan en düşük bulgu güveni (kurallı politika)
    time_revisit_min: float = Field(10.0, ge=0)    # başarısız durağın tekrar ziyaret maliyeti (dk karşılığı)
    time_km_cost_min: float = Field(0.8, ge=0)     # km başına yakıt/aşınma (dk karşılığı); sürüş süresi ayrıca minutes_per_km
    time_min_gain_min: float = Field(0.5, ge=0)    # hamle en az bu kadar beklenen maliyet düşürmeli (dk)
    # Faz 2c: onarımların sert kısıtı (pencere + zaman). Onarım öncesi rotaya göre beklenen süre (sürüş + servis + bilinen
    # öğle beklemesi) ve km artamaz (tolerans), bant üstü aşılamaz, kaydırılan durak vardiya bitişinden sonraya konamaz.
    repair_limits: bool = True
    repair_max_extra_min: float = Field(0.0, ge=0)  # rota süresi toleransı (dk)
    repair_max_extra_km: float = Field(0.5, ge=0)   # km toleransı (rota başına)
    time_blocked_diff: float = Field(0.3, ge=0, le=1)   # en iyi dilimden bu kadar kötü dilimde kalan bulgu "kaydırılamadı"
    repair_wait_margin_min: float = Field(30.0, ge=0)   # bekleme tahmininde pencere payı (beklenen varış belirsizliği)
    time_alternatives: bool = True                 # kaydırılamayan bulguya aktarma / ertesi gün / SMS önerisi (müdür kararı)

    @field_validator("extra_service_min")
    @classmethod
    def _e(cls, v: dict[str, float]) -> dict[str, float]:
        bad = [k for k in v if k not in QUIRK_KINDS]
        if bad:
            raise ValueError(f"routing.extra_service_min: bilinmeyen tür(ler) {bad}")
        return v


class Notes(_M):
    difficulty_mix: dict[Literal["pii", "ambiguous", "wrong"], float]
    gps_sigma_m: float = Field(ge=0)
    noise_rate: float = Field(ge=0, le=1)


class Assignment(_M):
    w_fail: float = Field(ge=0)
    w_time: float = Field(ge=0)
    eta_prior: float = Field(ge=0)
    eta_prior_weight: float = Field(ge=0)
    memory_relief: float = Field(ge=0, le=1)
    shrink_block: float = Field(ge=0)
    shrink_courier: float = Field(ge=0)
    shrink_speed: float = Field(ge=0)


class Leave(_M):
    courier: str
    from_: int = Field(alias="from", ge=0)
    to: int = Field(ge=0)
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Departure(_M):
    courier: str
    day: int = Field(ge=0)


class Hire(_M):
    id: str
    kind: Literal["new"] = "new"
    day: int = Field(ge=0)


class Borrowed(_M):
    id: str
    from_: int = Field(alias="from", ge=0)
    to: int = Field(ge=0)
    border_side: Literal["east", "west", "north", "south"] | None = None   # komşu şubeyle ortak sınır sokakları
    border_depth_km: float = Field(2.0, gt=0)
    border_familiarity: float = Field(0.6, ge=0, le=1)
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Calendar(_M):
    leaves: list[Leave] = []
    departures: list[Departure] = []
    hires: list[Hire] = []
    borrowed: list[Borrowed] = []


class Export(_M):
    snapshots: bool
    round: int = Field(ge=3, le=7)


class Config(_M):
    seed: int
    days: Days
    world: World
    couriers: Couriers
    demand: Demand
    planning: Planning
    outcome: Outcome
    quirks: Quirks
    presence: Presence = Presence(enabled=False)
    time_analysis: TimeAnalysis = TimeAnalysis()
    learning: Learning
    familiarity: Familiarity
    memory: Memory
    routing: Routing = Routing()
    morning: Morning = Morning()
    notes: Notes
    assignment: Assignment
    calendar: Calendar
    export: Export
    scenarios: list[str] = []

    @property
    def n_days(self) -> int:
        return self.days.warmup + self.days.eval


class ConfigError(ValueError):
    pass


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        elif isinstance(v, list) and isinstance(out.get(k), list) and k in ("leaves", "departures", "hires", "borrowed", "shocks"):
            out[k] = out[k] + v          # takvim/şok listeleri senaryolar arasında birleşir
        else:
            out[k] = copy.deepcopy(v)
    return out


def _set_path(d: dict, dotted: str, raw: str) -> None:
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            raise ConfigError(f"--set {dotted}: '{k}' alanı yok")
        cur = cur[k]
    if keys[-1] not in cur:
        raise ConfigError(f"--set {dotted}: '{keys[-1]}' alanı yok")
    cur[keys[-1]] = yaml.safe_load(raw)


def load_config(path: str | Path | None = None, scenarios: list[str] | None = None,
                overrides: list[str] | None = None) -> Config:
    """YAML'ı yükler, senaryo katmanlarını ve `a.b=c` ezmelerini uygular, doğrular."""
    path = Path(path) if path else DEFAULT_CONFIG
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for name in scenarios or []:
        sp = SCENARIO_DIR / f"{name}.yaml"
        if not sp.exists():
            raise ConfigError(f"Senaryo bulunamadı: {name} ({sp})")
        raw = _deep_merge(raw, yaml.safe_load(sp.read_text(encoding="utf-8")) or {})
    raw["scenarios"] = list(scenarios or [])
    for ov in overrides or []:
        if "=" not in ov:
            raise ConfigError(f"--set biçimi a.b=c olmalı: {ov}")
        k, v = ov.split("=", 1)
        _set_path(raw, k.strip(), v.strip())
    try:
        return Config.model_validate(raw)
    except ValidationError as e:
        lines = [f"  {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        raise ConfigError("Geçersiz yapılandırma:\n" + "\n".join(lines)) from None


def config_to_dict(cfg: Config) -> dict[str, Any]:
    return cfg.model_dump(mode="json", by_alias=True)

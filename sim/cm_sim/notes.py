"""Kurye notları: kusurlu, konuşma dilinde Türkçe.

Her notun gizli karşılığı (adres, püf noktası, sürüm, kişisel veri var mı, zorluk) ayrıca tutulur;
Hafıza Ajanı'nın doğruluğu buna göre ölçülür. Telefon numaraları açıkça sahte kalıptadır.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from .config import QUIRK_KINDS, Config
from .demand import waybill
from .rng import S_NOISE, S_NOTE_TEXT, rng
from .world import Quirk, World, xy_to_latlng

TEMPLATES: dict[str, list[str]] = {
    "back_entry": [
        "giriş arka sokaktan ön kapı kilitli",
        "arka taraftan gir ön kapı açılmıyo",
        "bina girişi arkada, önden girilmiyo",
        "ön kapı hep kapalı arka bahçe kapısından gir",
        "girişi arka sokakta abi önden dolanma",
    ],
    "saturday_closed": [
        "cmt kapalı boşuna gelmeyin",
        "cumartesi burası kapalı",
        "cumartesileri dükkan kapalı oluyo",
        "hafta sonu kapalı cumartesi gitmeyin",
    ],
    "lunch_break": [
        "12 ile 1.5 arası kimse yok öğle arası",
        "öğlen kapalı 12den sonra gelme",
        "öğle arasında kapıyı açmıyolar 1.5ta açılıyo",
        "öğle arası kapalı sabah ya da 2den sonra",
    ],
    "safety": [
        "güvenlikte kimlik bırakıyosun 5 dk sürüyo",
        "site güvenliği kart istiyo önceden ara",
        "güvenlik kulübesinde kayıt yaptırmak lazım",
        "site girişinde güvenlik var kimlik lazım",
    ],
    "bell": [
        "zil bozuk telefonla aramak lazım",
        "zil çalışmıyo kapıyı çal ya da ara",
        "zil yok müşteriyi aramak gerekiyo",
        "zile basma çalışmıyo direk ara",
    ],
    "position_wrong": [
        "harita yanlış gösteriyo bina 100m ileride benzinliğin arkası",
        "konum yanlış, bina bir sonraki sokakta",
        "haritadaki nokta yanlış, köşedeki sarı bina",
        "navigasyon yanlış yere götürüyo bina caminin karşısında",
    ],
    "reception": [
        "hepsi resepsiyona bırakılıyo",
        "plazada resepsiyon var kargoları oraya ver",
        "danışmaya teslim ediliyo, yukarı çıkma",
    ],
    "temporary_closed": [
        "tadilat var dükkan geçici kapalı",
        "bu hafta kapalı tadilattalar",
        "geçici olarak kapalı kapıda kağıt asılı",
    ],
    "roadwork": [
        "yol çalışması var sokak kapalı arkadan dolan",
        "sokağa girilmiyo kazı var, aşağıya park et",
        "yol kapalı çalışma var yürüyerek git",
    ],
}
PII_SNIPPETS = [
    "Ayşe hanım çok huysuz", "yaşlı teyze kapıyı geç açıyo", "0555 000 00 00 arayın",
    "Mehmet bey hep evde", "adam biraz tuhaf", "hasta biri var evde sessiz ol",
]
AMBIGUOUS_PREFIX = ["şu köşedeki bina", "parkın yanındaki apartman", "bakkalın oradaki yer", "bu sokaktaki site"]
FILLERS = ["abi", "", "", "yani", "", "bi de", ""]
NOISE_TEXTS = [
    "trafik berbattı bugün", "araç lastiği indi yarım saat kaybettim", "bugün çok yoğundu",
    "depoda paketler karışıktı", "yağmur yüzünden geciktim",
]


def _degrade(text: str, g: np.random.Generator) -> str:
    """Konuşma dili ve yazım hataları: ünlü düşürme, 'yo' ekleri, dolgu sözcükler."""
    words = text.split()
    out = []
    for w in words:
        if len(w) > 5 and g.random() < 0.08:
            i = int(g.integers(1, len(w) - 1))
            if w[i] in "aeıioöuü":
                w = w[:i] + w[i + 1:]
        out.append(w)
    filler = FILLERS[int(g.integers(len(FILLERS)))]
    if filler and g.random() < 0.5:
        out.insert(0, filler)
    return " ".join(out)


@dataclass
class Note:
    id: str
    day: int
    minute: int
    courier: str
    lat: float
    lng: float
    barcode: str | None
    text: str
    # --- gizli karşılık ---
    address: int | None
    quirk_id: int | None
    kind: str | None             # gerçek tür
    stated_kind: str | None      # notun anlattığı tür ("wrong" zorlukta farklıdır)
    version: int | None
    pii: bool
    difficulty: str              # normal | pii | ambiguous | wrong | noise

    def public(self) -> dict:
        return {"id": self.id, "day": self.day, "minute": self.minute, "courier": self.courier,
                "lat": round(self.lat, 6), "lng": round(self.lng, 6), "barcode": self.barcode, "text": self.text}

    def truth(self) -> dict:
        return {"id": self.id, "address": self.address, "quirk_id": self.quirk_id, "kind": self.kind,
                "stated_kind": self.stated_kind, "version": self.version, "pii": self.pii, "difficulty": self.difficulty}


def make_quirk_note(cfg: Config, world: World, day: int, minute: float, courier: str, q: Quirk,
                    n_shipments: int) -> Note:
    a = q.address
    g = rng(cfg.seed, day, S_NOTE_TEXT, a, q.id)
    mix = cfg.notes.difficulty_mix
    u = g.random()
    if u < mix["pii"]:
        diff = "pii"
    elif u < mix["pii"] + mix["ambiguous"]:
        diff = "ambiguous"
    elif u < mix["pii"] + mix["ambiguous"] + mix["wrong"]:
        diff = "wrong"
    else:
        diff = "normal"
    stated = q.kind
    if diff == "wrong":
        others = [k for k in QUIRK_KINDS if k != q.kind and k in TEMPLATES]
        stated = others[int(g.integers(len(others)))]
    tpl = TEMPLATES[stated]
    text = _degrade(tpl[int(g.integers(len(tpl)))], g)
    if diff == "ambiguous":
        text = f"{AMBIGUOUS_PREFIX[int(g.integers(len(AMBIGUOUS_PREFIX)))]}, {text}"
    if diff == "pii":
        snip = PII_SNIPPETS[int(g.integers(len(PII_SNIPPETS)))]
        text = f"{text}, {snip}" if g.random() < 0.5 else f"{snip}, {text}"
    sigma_km = (cfg.notes.gps_sigma_m * (2.4 if diff == "ambiguous" else 1.0)) / 1000.0
    xy = world.addr_xy[a] + g.normal(0, sigma_km, 2)
    lat, lng = xy_to_latlng(xy, world.cfg_center).tolist()
    barcode = None if diff == "ambiguous" or n_shipments == 0 else waybill(day, a, int(g.integers(max(1, n_shipments))))
    nid = f"N{day:02d}-{a:05d}-{q.id:05d}-{zlib.crc32(courier.encode()) % 1000:03d}"
    return Note(id=nid, day=day, minute=int(minute), courier=courier, lat=lat, lng=lng, barcode=barcode,
                text=text, address=a, quirk_id=q.id, kind=q.kind, stated_kind=stated,
                version=q.version(day), pii=diff == "pii", difficulty=diff)


def maybe_noise_note(cfg: Config, world: World, day: int, courier: str, minute: float,
                     xy: np.ndarray) -> Note | None:
    g = rng(cfg.seed, day, S_NOISE, zlib.crc32(courier.encode()))
    if g.random() >= cfg.notes.noise_rate:
        return None
    text = _degrade(NOISE_TEXTS[int(g.integers(len(NOISE_TEXTS)))], g)
    lat, lng = xy_to_latlng(xy + g.normal(0, 0.03, 2), world.cfg_center).tolist()
    nid = f"N{day:02d}-noise-{zlib.crc32(courier.encode()) % 100000:05d}"
    return Note(id=nid, day=day, minute=int(minute), courier=courier, lat=lat, lng=lng, barcode=None,
                text=text, address=None, quirk_id=None, kind=None, stated_kind=None, version=None,
                pii=False, difficulty="noise")

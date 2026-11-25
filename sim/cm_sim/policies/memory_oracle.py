"""Deterministik hafıza politikası (kol D): LLM Hafıza Ajanı gelmeden önceki yer tutucu.

Kusurlu bir ayrıştırıcıyı taklit eder: her not `parse_accuracy` olasılıkla doğru adres + notun anlattığı
türe bağlanır; değilse komşu adrese, yanlış türe bağlanır ya da düşer. Kişisel veri asla kaydedilmez;
kayıt metni nötr kalıp cümledir. Ayrıştırma notların gizli karşılığını kullanır (simülasyon defteri);
LLM ajanı aynı arayüzü yalnız gözlemlenebilir verilerle uygular.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from ..config import QUIRK_KINDS, TEMPORARY_KINDS, Config
from ..notes import Note
from ..rng import S_HARVEST, S_PARSE, rng
from ..routing_memory import StopRule, rule_from_entries
from ..world import World
from .base import DayContext, DeliveryEvent, HintView, NoteView, StopView

HINT_TEXT = {
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


@dataclass
class MemoryEntry:
    id: str
    address: int
    kind: str
    text: str
    sources: int
    first_day: int
    last_day: int
    temporary: bool
    ttl_until: int | None
    truth_version: int                       # -1: gerçeğe karşılık gelmeyen kayıt
    note_ids: list[str] = field(default_factory=list)

    def alive(self, day: int) -> bool:
        return self.ttl_until is None or day <= self.ttl_until

    def view(self) -> HintView:
        return HintView(entry_id=self.id, address=self.address, kind=self.kind, text=self.text, sources=self.sources,
                        first_day=self.first_day, last_day=self.last_day, truth_version=self.truth_version)

    def public(self) -> dict:
        return {"id": self.id, "address": self.address, "kind": self.kind, "text": self.text, "sources": self.sources,
                "first_day": self.first_day, "last_day": self.last_day, "temporary": self.temporary,
                "ttl_until": self.ttl_until}


class MemoryStore:
    """Adres hafızası. Okuma arayüzü MemoryReader'ı uygular."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.entries: dict[int, list[MemoryEntry]] = {}
        self._seq = 0

    def entries_for(self, address: int, day: int) -> list[HintView]:
        ms = self.cfg.memory.min_sources
        return [e.view() for e in self.entries.get(address, []) if e.alive(day) and e.sources >= ms]

    def has_entry(self, address: int, day: int) -> bool:
        return bool(self.entries_for(address, day))

    def upsert(self, address: int, kind: str, day: int, truth_version: int, note_id: str | None,
               text: str | None = None) -> MemoryEntry:
        lst = self.entries.setdefault(address, [])
        for e in lst:
            if e.kind == kind:
                e.sources += 1
                e.last_day = day
                if truth_version > e.truth_version:
                    e.truth_version = truth_version
                if kind in TEMPORARY_KINDS:
                    e.ttl_until = day + self.cfg.memory.ttl_days
                if note_id:
                    e.note_ids.append(note_id)
                return e
        self._seq += 1
        e = MemoryEntry(id=f"M{self._seq:05d}", address=address, kind=kind, text=text or HINT_TEXT[kind], sources=1,
                        first_day=day, last_day=day, temporary=kind in TEMPORARY_KINDS,
                        ttl_until=day + self.cfg.memory.ttl_days if kind in TEMPORARY_KINDS else None,
                        truth_version=truth_version, note_ids=[note_id] if note_id else [])
        lst.append(e)
        return e

    def remove(self, entry_id: str) -> bool:
        for a, lst in self.entries.items():
            for e in lst:
                if e.id == entry_id:
                    lst.remove(e)
                    return True
        return False

    def all_alive(self, day: int) -> list[MemoryEntry]:
        return [e for lst in self.entries.values() for e in lst if e.alive(day)]

    def export(self, day: int) -> list[dict]:
        return [e.public() for e in sorted(self.all_alive(day), key=lambda e: (e.address, e.kind))]


class MemoryOraclePolicy:
    name = "memory_oracle"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.store = MemoryStore(cfg)

    # --- MemoryPolicy arayüzü ---
    def reader(self) -> MemoryStore:
        return self.store

    def hints_for(self, ctx: DayContext, courier: str, stops: Sequence[StopView]) -> dict[int, list[HintView]]:
        out: dict[int, list[HintView]] = {}
        for s in stops:
            h = self.store.entries_for(s.address, ctx.day)
            if h:
                out[s.address] = h
        return out

    def ingest(self, ctx: DayContext, notes: Sequence[NoteView], events: Sequence[DeliveryEvent]) -> None:
        raise NotImplementedError("Oracle gizli karşılıkla çalışır: ingest_with_truth kullanın")

    # --- simülatöre özgü ---
    def ingest_with_truth(self, world: World, day: int, notes: Sequence[Note]) -> dict:
        acc = self.cfg.memory.parse_accuracy
        g = rng(self.cfg.seed, day, S_PARSE, 7)
        stats = {"notes": 0, "correct": 0, "neighbor": 0, "wrong_kind": 0, "dropped": 0, "noise_ignored": 0, "junk": 0}
        for nt in notes:
            stats["notes"] += 1
            u, u2, u3 = g.random(), g.random(), g.random()
            if nt.difficulty == "noise":
                if u < acc:
                    stats["noise_ignored"] += 1
                else:
                    a = self._nearest_address(world, nt.lat, nt.lng)
                    self.store.upsert(a, QUIRK_KINDS[int(u2 * len(QUIRK_KINDS)) % len(QUIRK_KINDS)], day, -1, nt.id)
                    stats["junk"] += 1
                continue
            assert nt.address is not None and nt.stated_kind is not None and nt.kind is not None
            tv = nt.version if nt.stated_kind == nt.kind else -1
            if u < acc:
                self.store.upsert(nt.address, nt.stated_kind, day, tv if tv is not None else -1, nt.id)
                stats["correct"] += 1
                continue
            branch = int(u2 * 3)
            if branch == 0:
                a = self._neighbor(world, nt.address, u3)
                self.store.upsert(a, nt.stated_kind, day, -1, nt.id)
                stats["neighbor"] += 1
            elif branch == 1:
                others = [k for k in QUIRK_KINDS if k != nt.stated_kind]
                self.store.upsert(nt.address, others[int(u3 * len(others)) % len(others)], day, -1, nt.id)
                stats["wrong_kind"] += 1
            else:
                stats["dropped"] += 1
        return stats

    def ingest_events(self, world: World, day: int, weekday: int, stop_results: Sequence, lunch: tuple[int, int]) -> int:
        """Teslim kayıtlarından çıkarım: "kapalı" nedenli başarısızlık, gün/saat örüntüsüyle türe bağlanır.

        Cumartesi → saturday_closed; öğle penceresi → lunch_break; diğer → temporary_closed.
        Not bırakılmasa da hafıza bu kayıtlardan öğrenir (Hafıza Ajanı'nın ikinci kaynağı).
        """
        added = 0
        for s in stop_results:
            if not s.reasons.get("closed"):
                continue
            if weekday == 5:
                kind = "saturday_closed"
            elif lunch[0] <= s.arrival < lunch[1]:
                kind = "lunch_break"
            else:
                kind = "temporary_closed"
            cur = {q.kind: q.version(day) for q in world.quirks_by_addr[s.address] if q.active(day)}
            self.store.upsert(s.address, kind, day, cur.get(kind, -1), None)
            added += 1
        return added

    # --- hafıza → rota kısıtı (Hedef 3) ---
    def rules_for(self, day: int, weekday: int, addresses) -> dict[int, StopRule]:
        """Adres → bugünkü kısıt (kapalı gün, öğle penceresi, ek servis). Yalnız hafızadaki kayıtlardan (gözlemlenebilir)."""
        cfg = self.cfg
        out: dict[int, StopRule] = {}
        for a in addresses:
            es = self.store.entries_for(int(a), day)
            if not es:
                continue
            r = rule_from_entries([(e.kind, e.entry_id, e.sources) for e in es], weekday, cfg.quirks.lunch_window,
                                  cfg.routing.extra_service_min, cfg.routing.defer_min_sources)
            if r is not None:
                out[int(a)] = r
        return out

    # --- proaktif hasat (Hedef 1/2) ---
    def harvest(self, world: World, day: int, targets: list[tuple[int, int, str]], answerers: dict[str, float],
                fam, known: dict[str, dict], addr_days: dict[int, int], departing: dict[str, list[int]]) -> dict:
        """Plan kesinleşince hedefli soru. targets: (adres, blok, atanan kurye) — yabancı kurye için hafızası boş durakları.
        answerers: bugün çalışan yerel kurye → kota. departing: ayrılacak kurye → tanıdık blokları (devir teslim).

        Soru seçimi gözlemlenebilir: adresin geçmişteki durak günü sayısı × adres türünde hafıza kaydı yoğunluğu. Cevap
        kıdemlinin GİZLİ bilgisinden gelir (simüle edilen insan): bildiği etkin püf noktasını `p_answer` olasılıkla anlatır;
        cevap Hafıza Ajanı'ndan `parse_accuracy` ile geçer. Bilmiyorsa kayıt oluşmaz.
        """
        cfg = self.cfg
        mc = cfg.memory
        g = rng(cfg.seed, day, S_HARVEST)
        kinds = world.addr_kind
        tot: dict[str, int] = {}
        withm: dict[str, int] = {}
        for k in kinds:
            tot[k] = tot.get(k, 0) + 1
        for a, lst in self.store.entries.items():
            if any(e.alive(day) for e in lst):
                withm[kinds[a]] = withm.get(kinds[a], 0) + 1
        rate = {k: (withm.get(k, 0) + 1) / (tot[k] + 10) for k in tot}

        def score(a: int) -> float:
            return (1 + addr_days.get(a, 0)) * rate[kinds[a]]

        quota = dict(answerers)
        asked: list[tuple[int, str, str]] = []           # (adres, cevaplayan, neden)
        seen: set[int] = set()
        for cid, blocks in departing.items():             # devir teslim: ayrılan kuryeye bölgesinin sık adresleri
            bs = set(blocks)
            cands = sorted({a for a in addr_days if int(world.addr_block[a]) in bs and not self.store.has_entry(a, day)},
                           key=lambda a: (-score(a), a))
            for a in cands[:mc.harvest_per_senior * 3]:
                asked.append((a, cid, "handover"))
                seen.add(a)
        budget = mc.harvest_per_day
        for a, b, assignee in sorted(targets, key=lambda t: (-score(t[0]), t[0])):
            if budget <= 0:
                break
            if a in seen or self.store.has_entry(a, day):
                continue
            best = max((c for c in quota if quota[c] > 0 and c != assignee), key=lambda c: (fam.value(c, b, day), c), default=None)
            if best is None or fam.value(best, b, day) < 0.5:
                continue
            quota[best] -= 1
            budget -= 1
            asked.append((a, best, "unfamiliar_stop"))
            seen.add(a)
        stats = {"question": len(asked), "handover": sum(1 for x in asked if x[2] == "handover"), "answer": 0, "record": 0,
                 "no_info": 0, "falling": 0}
        for a, cid, _ in asked:
            u, u2 = g.random(), g.random()
            kn = known.get(cid, {})
            facts = [(q, kn[(a, q.id)]) for q in world.quirks_by_addr[a] if q.active(day) and (a, q.id) in kn]
            if u >= mc.p_answer or not facts:
                stats["no_info"] += 1
                continue
            stats["answer"] += 1
            if u2 >= mc.parse_accuracy:
                stats["falling"] += 1
                continue
            for q, give in facts[:2]:
                self.store.upsert(a, q.kind, day, give, None)
                stats["record"] += 1
        return stats

    def feedback_invalidate(self, world: World, address: int, day: int) -> int:
        """Kurye ipucunun yanlış/bayat olduğunu bildirir: gerçeğe uymayan kayıtlar düşer."""
        removed = 0
        current = {q.kind: q.version(day) for q in world.quirks_by_addr[address] if q.active(day)}
        for e in list(self.store.entries.get(address, [])):
            if e.kind not in current or e.truth_version != current[e.kind]:
                self.store.remove(e.id)
                removed += 1
        return removed

    @staticmethod
    def _neighbor(world: World, a: int, u: float) -> int:
        b = world.addr_block[a]
        same = np.where(world.addr_block == b)[0]
        same = same[same != a]
        if len(same):
            return int(same[int(u * len(same)) % len(same)])
        d = ((world.addr_xy - world.addr_xy[a]) ** 2).sum(1)
        d[a] = np.inf
        return int(np.argmin(d))

    @staticmethod
    def _nearest_address(world: World, lat: float, lng: float) -> int:
        d = (world.addr_latlng[:, 0] - lat) ** 2 + (world.addr_latlng[:, 1] - lng) ** 2
        return int(np.argmin(d))

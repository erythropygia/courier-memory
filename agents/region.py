"""Bölge Ajanı: üç katmanlı bilgi — durak (kapı kartı) · küme (kuryenin sabah kartı) · şube (müdürün bölge haritası).

Birim ~300 m blok (tanıdıklıkla aynı hücre). Geçmiş (gerçek teslim noktaları üzerindeki simülasyon günleri, hedef günden
önce) ve canlı hafızadan blok başına:
  deneme, bilgi nedenli başarısız (adres bulunamadı, giriş yapılamadı, kapalı, alıcıya ulaşılamadı), baskın neden,
  hafıza kaydı sayısı ve türleri.
Zorluk endeksi = bloğun bilgi nedenli başarısız oranı, şube ortalamasına doğru büzülmüş (Beta önsel, ağırlık PRIOR deneme)
÷ şube ortalaması. ≥ 1,5 yüksek · ≥ 1,1 orta · altı düşük. Hafıza boşluğu: zor blok + hafıza kaydı yok.
Kuryeye kart ve müdüre özet cümleleri kurallı şablonla üretilir (canlıda istenirse LLM yazar; sayılar araçtan gelir).
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from .memorybook import MemoryBook
from .rundata import RunData

CELL_LAT, CELL_LNG = 0.0027, 0.0036
INFO_REASONS = {"address_not_found": "adres bulunamadı", "entry_failed": "giriş yapılamadı", "closed": "kapalı",
               "recipient_unreachable": "alıcıya ulaşılamadı"}
PRIOR = 20.0
KIND_NAME = {"back_entry": "arka giriş", "saturday_closed": "cumartesi kapalı", "lunch_break": "öğle arası", "safety": "site güvenliği",
          "bell": "zil sorunu", "position_wrong": "hatalı konum", "reception": "resepsiyon", "temporary_closed": "geçici kapalı",
          "roadwork": "yol çalışması", "park": "park", "building_access": "bina erişimi", "directions": "adres tarifi",
          "animal": "hayvan", "other_info": "diğer"}


def cell(lat: float, lng: float) -> tuple[int, int]:
    return math.floor(lat / CELL_LAT), math.floor(lng / CELL_LNG)


def center(h: tuple[int, int]) -> list[float]:
    return [round((h[0] + 0.5) * CELL_LAT, 5), round((h[1] + 0.5) * CELL_LNG, 5)]


class RegionStats:
    def __init__(self, run: RunData, book: MemoryBook, day: int):
        self.run, self.book, self.day = run, book, day
        book.ensure(day)
        st = defaultdict(lambda: {"attempt": 0, "fails": 0, "reason": defaultdict(int), "address": defaultdict(int)})
        for d in [x for x in run.eval_days if x < day]:
            snap = run.snapshot("D", d)
            F = {k: i for i, k in enumerate(snap["stop_fields"])}
            for r in snap["routes"]:
                for s in r["stops"]:
                    h = cell(s[F["lat"]], s[F["lng"]])
                    x = st[h]
                    x["attempt"] += int(s[F["ok"]]) + int(s[F["fail"]])
                    if s[F["fail"]] and s[F["reason"]] in INFO_REASONS:
                        x["fails"] += int(s[F["fail"]])
                        x["reason"][s[F["reason"]]] += 1
                        x["address"][int(s[F["address"]])] += 1
        self.st = st
        total_attempts = sum(x["attempt"] for x in st.values())
        self.mean = sum(x["fails"] for x in st.values()) / max(total_attempts, 1)
        recs = defaultdict(lambda: defaultdict(int))
        for e in book.entries:
            if e.get("status", "active") == "active":
                a = int(e["address"])
                recs[cell(float(run.addr_ll[a, 0]), float(run.addr_ll[a, 1]))][e["kind"]] += 1
        self.record = recs

    def index(self, h) -> float:
        x = self.st.get(h)
        if not x:
            return 1.0
        p = (x["fails"] + PRIOR * self.mean) / (x["attempt"] + PRIOR)
        return p / max(self.mean, 1e-9)

    @staticmethod
    def level(e: float) -> str:
        return "high" if e >= 1.5 else ("mid" if e >= 1.1 else "low")

    def block(self, h) -> dict:
        x = self.st.get(h) or {"attempt": 0, "fails": 0, "reason": {}}
        e = self.index(h)
        nd = max(x["reason"].items(), key=lambda kv: kv[1])[0] if x["reason"] else None
        k = dict(self.record.get(h, {}))
        name = x.get("address") or {}
        worst = max(name.items(), key=lambda kv: kv[1])[0] if name else None
        return {"block_id": f"{h[0]}_{h[1]}", "center": center(h), "attempt": x["attempt"], "fails": x["fails"], "index": round(e, 2),
                "level": self.level(e), "main_reason": INFO_REASONS.get(nd), "record": sum(k.values()), "record_kinds": k,
                "gap": e >= 1.5 and not k, "worst_address": worst}

    def summary(self, cells: list, weight: dict | None = None) -> dict:
        """Bir alan (küme ya da şube) için: zorluk, en zor bloklar, kayıt türleri, hafıza boşlukları."""
        hs = list(dict.fromkeys(cells))
        bl = [self.block(h) for h in hs]
        w = np.array([(weight or {}).get(h, 1) for h in hs], dtype=float)
        e = float(np.average([b["index"] for b in bl], weights=w)) if bl else 1.0
        types: dict[str, int] = defaultdict(int)
        for b in bl:
            for t, n in b["record_kinds"].items():
                types[t] += n
        hard = sorted([b for b in bl if b["level"] != "low" and b["attempt"] >= 3], key=lambda b: -b["index"])
        return {"block": len(bl), "index": round(e, 2), "level": self.level(e), "high_blocks": sum(1 for b in bl if b["level"] == "high"),
                "gap": sum(1 for b in bl if b["gap"]), "record": sum(types.values()),
                "record_kinds": dict(sorted(types.items(), key=lambda kv: -kv[1])), "hardest": hard[:5], "branch_mean_fail": round(self.mean, 4)}

    # ------------------------------------------------------------------ katmanlar
    def cluster_card(self, stops: list[tuple[float, float]], unfamiliar: list[bool], name: str,
                   card_kinds: list[list[str]] | None = None) -> dict:
        """card_kinds: durak başına kart türleri (verilirse blok kayıtları bunlardan sayılır: durak kartlarıyla aynı kaynak)."""
        hs = [cell(la, lo) for la, lo in stops]
        say = defaultdict(int)
        for h in hs:
            say[h] += 1
        if card_kinds is not None:
            old = self.record
            self.record = defaultdict(lambda: defaultdict(int))
            for h, ts in zip(hs, card_kinds):
                for t in ts:
                    self.record[h][t] += 1
            try:
                return self._cluster_card(hs, say, unfamiliar, name, len(stops))
            finally:
                self.record = old
        return self._cluster_card(hs, say, unfamiliar, name, len(stops))

    def _cluster_card(self, hs, say, unfamiliar, name, n) -> dict:
        stops = range(n)
        o = self.summary(hs, say)
        unf_cells = {h for h, y in zip(hs, unfamiliar) if y}
        o_unf = self.summary(list(unf_cells)) if unf_cells else None
        kind = list(o["record_kinds"].items())[:3]
        sentence = [f"Günaydın {name}. Bugünkü kümen {len(stops)} durak; {sum(unfamiliar)} tanesi daha önce girmediğin sokaklarda."]
        if o["high_blocks"]:
            z = o["hardest"][0]
            sentence.append(f"{o['high_blocks']} blokta teslim geçmişte zor oldu; en zorunda en sık neden: {z['main_reason'] or 'bilinmiyor'}.")
        if kind:
            sentence.append("Hafızada bu kümede en çok " + ", ".join(f"{KIND_NAME.get(t, t)} ({n})" for t, n in kind) + " notu var; kapıya yaklaşınca söyleyeceğim.")
        if o["gap"]:
            sentence.append(f"{o['gap']} zor blokta henüz not yok; oradan geçerken gördüğünü bir cümleyle not bırakırsan bir sonraki kurye bilir.")
        return {"layer": "cluster", "difficulty": o["level"], "index": o["index"], "summary": o, "unfamiliar_summary": o_unf, "courier_card": sentence}

    def branch_layer(self) -> dict:
        hs = [h for h, x in self.st.items() if x["attempt"] >= 3]
        o = self.summary(hs)
        blocks = [self.block(h) for h in hs]
        manager = [f"Şubede {len(hs)} blok izleniyor; {o['high_blocks']} tanesi zor (bilgi nedenli başarısızlık şube ortalamasının en az 1,5 katı).",
                 f"Zor blokların {o['gap']} tanesinde hafızada hiç not yok: Hasat Ajanı soruları önce bu bloklara yönlendiriliyor."]
        if o["record_kinds"]:
            manager.append("Hafızada en sık bilgi: " + ", ".join(f"{KIND_NAME.get(t, t)} ({n})" for t, n in list(o["record_kinds"].items())[:4]) + ".")
        return {"layer": "branch", "summary": o, "blocks": blocks, "manager_summary": manager}

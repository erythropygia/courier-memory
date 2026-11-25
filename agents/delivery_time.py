"""Teslim zamanı analizi, ajan tarafı: "bu adreste hangi saatte kimse yok?" kayıtlardan, not olmadan.

Kaynak yalnız gözlemlenebilir teslim kaydıdır (`delivery_log.json`: gün, adres, varış dakikası, alıcı yok 0/1); hedef günden
ÖNCEKİ satırlar kullanılır. Hesap simülatörün kol D'de kullandığı AYNI fonksiyonlardır (`cm_sim.delivery_time`): aynı kayıt →
aynı sayımlar → aynı bulgular → `compute_route` aynı rotayı kurar (`same_as_sim`).

`TimeSource` rota planlayıcısına bulguları verir. Hangi bulguların rotaya gireceğine Orkestratör karar verir
(`apply_time_constraint`: en düşük güven + hariç tutulan adresler); karar yoksa kurallı politika (`routing.time_min_confidence`)
kullanılır. Hasat cevabıyla teyit edilen bulgu güvenden bağımsız rotaya girer; reddedilen bulgu girmez.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

import numpy as np

from cm_sim.config import ADDRESS_KINDS
from cm_sim.delivery_time import (SLOT_NAMES, DAY_TYPES, LEVEL_ORDER, Params, counts_from_log, slot, day_type, proposal_text,
                                  fits_route, posterior, type_profile, time_findings)

from .guardrails import redact
from .rundata import RunData
from .tr import hhmm

LIST_MAX = 25


def _cfg(run: RunData) -> dict:
    from .route import EtaModel
    return EtaModel.load_cfg(run)


class TimeData:
    """Teslim kaydını okur; güne göre sayımlar ve bulgular (önbellekli)."""

    def __init__(self, run: RunData):
        self.run = run
        cfg = _cfg(run)
        self.params = Params.from_dict(cfg.get("time_analysis"))
        r = cfg.get("routing") or {}
        self.min_level = str(r.get("time_min_confidence", "mid"))
        self.enabled = bool(r.get("enabled", False)) and bool(r.get("time_aware", False))
        p = run.dir / "delivery_log.json"
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            self.day, self.addr = np.array(d["day"], dtype=np.int64), np.array(d["address"], dtype=np.int64)
            self.minute, self.absent = np.array(d["minute"], dtype=np.int64), np.array(d["absent"], dtype=np.int64)
        else:
            self.enabled = False
            self.day = self.addr = self.minute = self.absent = np.zeros(0, dtype=np.int64)
        self.kind_idx = np.array([ADDRESS_KINDS.index(k) for k in run.addr_kind], dtype=np.int64)
        self._counts: dict[int, tuple] = {}
        self._found: dict[int, dict] = {}

    def counts(self, day: int):
        if day not in self._counts:
            self._counts[day] = counts_from_log(len(self.kind_idx), self.day, self.addr, self.minute, self.absent, day)
        return self._counts[day]

    def findings(self, day: int, addrs) -> dict[int, dict]:
        """Adres → bulgu (o güne kadarki kayıtlardan). Sonuç güne göre önbelleklenir; yeni adresler eklenir."""
        cache = self._found.setdefault(day, {})
        todo = [int(a) for a in addrs if int(a) not in cache]
        if todo:
            att, ab = self.counts(day)
            got = time_findings(att, ab, self.kind_idx, len(ADDRESS_KINDS), todo, day % 6, self.params)
            for a in todo:
                cache[a] = got.get(a)
        return {int(a): cache[int(a)] for a in addrs if cache.get(int(a)) is not None}

    def address_table(self, address: int, day: int) -> dict:
        """Bir adresin bugünkü gün tipinde dilim tablosu: deneme, teslim, bulunamadı, büzülmüş tahmin ve adres türü ortalaması."""
        att, ab = self.counts(day)
        g = day_type(day % 6)
        q, qbar = type_profile(att, ab, self.kind_idx, len(ADDRESS_KINDS), g)
        k = int(self.kind_idx[int(address)])
        mean, _, _, pbar = posterior(att[int(address), g], ab[int(address), g], q[k], float(qbar[k]), self.params)
        rows = [{"slot": SLOT_NAMES[d], "attempt": int(att[address, g, d]), "delivery": int(att[address, g, d] - ab[address, g, d]),
                 "not_found": int(ab[address, g, d]), "estimate": round(float(mean[d]), 3), "type_mean": round(float(q[k, d]), 3)}
                for d in range(len(SLOT_NAMES))]
        return {"day_type": DAY_TYPES[g], "address_general_estimate": round(pbar, 3), "slots": rows}

    def history(self, address: int, day: int) -> list[dict]:
        m = (self.addr == int(address)) & (self.day < day)
        return [{"day": int(d), "weekday": self.run.weekday_name(int(d)), "hour": hhmm(int(t)), "slot": SLOT_NAMES[slot(int(t))],
                 "result": "recipient_absent" if int(x) else "delivery"} for d, t, x in zip(self.day[m], self.minute[m], self.absent[m])]


CONFIRMATION_YES = re.compile(r"\b(evet|doğru|dogru|haklısın|aynen|öyle|oluyor|kimse yok|çalışıyor|kapalı)", re.I)
CONFIRMATION_NO = re.compile(r"\b(hayır|hayir|değil|degil|yanlış|genelde evde|her zaman (biri|birisi) var|sorun yok)", re.I)
HOUR_AFTER = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*'?\s*(?:d[ae]n|t[ae]n)\s+sonra", re.I)


def parse_confirmation(text: str) -> tuple[bool | None, int | None]:
    """Kurye cevabı → (teyit evet/hayır/None, "X'ten sonra" saati dk). "akşam 5'ten sonra" → 17:00."""
    t = text or ""
    no, yes = bool(CONFIRMATION_NO.search(t)), bool(CONFIRMATION_YES.search(t))
    decision = False if no and not yes else True if yes and not no else (False if no else None)
    m = HOUR_AFTER.search(t)
    hour = None
    if m:
        h = int(m.group(1))
        if h < 9:
            h += 12
        hour = h * 60 + int(m.group(2) or 0)
    return decision, hour


class TimeSource:
    """Rota planlayıcısının teslim zamanı kaynağı: bulgular + Orkestratör seçimi + hasat teyitleri."""
    name = "delivery_time"

    def __init__(self, run: RunData):
        self.data = TimeData(run)
        self.run = run
        self.selection: dict[int, dict] = {}            # gün → {min_confidence, haric[]}
        self.confirmations: dict[int, dict] = {}         # adres → {gun, teyit, saat, metin}

    @property
    def enabled(self) -> bool:
        return self.data.enabled

    def make_selection(self, day: int, min_confidence: str | None = None, excluded: list[int] | None = None) -> dict:
        lv = min_confidence or self.data.min_level
        if lv not in LEVEL_ORDER:
            raise ValueError(f"min_confidence şunlardan biri olmalı: {', '.join(LEVEL_ORDER)}")
        self.selection[day] = {"min_confidence": lv, "excluded": sorted({int(a) for a in (excluded or [])})}
        return self.selection[day]

    def _selection(self, day: int) -> dict:
        return self.selection.get(day) or {"min_confidence": self.data.min_level, "excluded": []}

    def reset(self) -> None:
        """Seçim ve teyitleri temizler (hafıza sıfırlanınca; kayıt/oynatma için deterministik başlangıç)."""
        self.selection.clear()
        self.confirmations.clear()

    def write_confirmation(self, address: int, day: int, confirmation: bool | None, hour: int | None, text: str) -> dict:
        x = {"day": int(day), "confirmation": confirmation, "hour": hour, "text": redact(text)[:200]}
        self.confirmations[int(address)] = x
        return x

    def _confirmation(self, a: int, day: int) -> dict | None:
        t = self.confirmations.get(int(a))
        return t if t is not None and t["day"] <= day else None

    def route(self, day: int, addrs) -> dict[int, dict]:
        """Adres → rotaya giren bulgu (tahmin vektörü dahil). Kurallı politika + seçim + teyitler."""
        if not self.enabled:
            return {}
        sel = self._selection(day)
        out = {}
        for a, b in self.data.findings(day, addrs).items():
            if a in sel["excluded"]:
                continue
            t = self._confirmation(a, day)
            if t is not None and t["confirmation"] is False:
                continue
            if t is not None and t["confirmation"]:
                est = list(b["estimate"])
                est[b["bad"]] = max(est[b["bad"]], 0.8)
                if t["hour"] is not None:
                    d = slot(t["hour"])
                    if d != b["bad"]:
                        est[d] = min(est[d], 0.05)
                out[a] = {**b, "estimate": est, "confirmed": True}
            elif fits_route(b, sel["min_confidence"]):
                out[a] = b
        return out

    def presence(self, day: int, addrs) -> dict[int, tuple]:
        return {a: tuple(float(x) for x in b["estimate"]) for a, b in self.route(day, addrs).items()}

    def row(self, a: int, b: dict, day: int) -> dict:
        """Bulgunun okunabilir satırı (araç çıktısı ve API)."""
        t = self._confirmation(a, day)
        return {"address": int(a), "label": self.run.addr_label[a], "address_type": self.run.addr_kind[a], "type": b["type"],
                "day_type": b["day_type"], "bad_slot": SLOT_NAMES[b["bad"]],
                "good_slot": SLOT_NAMES[b["good"]] if b.get("good") is not None else None, "confidence": b.get("confidence"),
                "level": b["level"], "text": proposal_text(b), "attempt": b["attempt"], "not_found": b["not_found"],
                "estimate": b["estimate"], "confirmation": None if t is None else t["confirmation"],
                "fits_route": fits_route(b, self._selection(day)["min_confidence"]) or bool(t and t["confirmation"])}


@lru_cache(maxsize=4)
def time_source(run: RunData) -> TimeSource:
    """Çalıştırma klasörü başına tek kaynak (Orkestratör, API ve brifing aynı seçimi ve teyitleri görür)."""
    return TimeSource(run)


def delivery_time_analysis(zk: TimeSource, day: int, plan_addrs: dict[int, list[int]], mapping: dict[int, str],
                          min_confidence: str = "low") -> dict:
    """Orkestratör aracı: bugünkü planın duraklarında teslim zamanı bulguları. plan_addrs: küme → adresler; mapping: küme → kurye."""
    of = {a: k for k, addrs in plan_addrs.items() for a in addrs}
    found = zk.data.findings(day, list(of))
    rows = []
    for a, b in found.items():
        r = zk.row(a, b, day)
        r.update(cluster=of[a], courier=mapping.get(of[a]), courier_name=zk.run.courier_name(mapping.get(of[a], "")))
        rows.append(r)
    pen = [r for r in rows if r["type"] == "window" and LEVEL_ORDER[r["level"]] >= LEVEL_ORDER.get(min_confidence, 0)]
    pen.sort(key=lambda r: (-LEVEL_ORDER[r["level"]], -(r["confidence"] or 0), r["address"]))
    conf = sorted((r for r in rows if r["type"] == "confirmation"), key=lambda r: (-max(r["estimate"]), r["address"]))
    return {"day": day, "day_type": "saturday" if day % 6 == 5 else "weekdays", "stop": len(of),
            "window_finding": len(pen), "confirmation_pending": len(conf),
            "rule_policy": zk.data.min_level, "fits_route": sum(1 for r in pen if r["fits_route"]),
            "findings": pen[:LIST_MAX], "confirmations": conf[:10],
            "method": ("Kayıtlardan, hedef günden önceki denemeler; adres × saat dilimi; az veride adresin genel oranına, o da "
                       "adres türünün saat şekline çekilir (Beta-Binom). Önerilen saatin adreste kendi kanıtı olmalıdır.")}

"""Politika arayüzleri ve gözlemlenebilir görünümler.

Politikalar (deterministik ya da LLM ajanı) yalnız buradaki `*View` nesnelerini ve `HistoryReader`'ı
alır. Gizli gerçek nesneleri (Courier, Address, Quirk, Block) politikalara geçirilmez; bunu bir test denetler.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

from ..history import HistoryReader


@dataclass(frozen=True)
class StopView:
    id: str
    address: int
    block: int
    lat: float
    lng: float
    n_shipments: int
    x: float = 0.0          # yerel düzlem, km
    y: float = 0.0


@dataclass(frozen=True)
class ClusterView:
    id: int
    stops: tuple[StopView, ...]
    planned_minutes: float
    km: float


@dataclass(frozen=True)
class CourierView:
    id: str
    name: str
    kind: str              # senior | reserve | new | borrowed
    available: bool
    days_in_branch: int


@dataclass(frozen=True)
class HintView:
    entry_id: str
    address: int
    kind: str
    text: str
    sources: int
    first_day: int
    last_day: int
    truth_version: int = field(default=-1, compare=False, repr=False)   # simülatörün defter kaydı; politikalar kullanmaz


class MemoryReader(Protocol):
    def entries_for(self, address: int, day: int) -> list[HintView]: ...
    def has_entry(self, address: int, day: int) -> bool: ...


@dataclass(frozen=True)
class DayContext:
    day: int
    weekday: int
    history: HistoryReader
    memory: MemoryReader | None
    assignment_cfg: object          # config.Assignment
    service_per_stop: float
    service_per_shipment: float
    unfamiliar_below: float
    block_xy: object = None           # blok merkezleri (km), gözlemlenebilir harita bilgisi


@dataclass
class AssignmentDecision:
    mapping: dict[int, str]                       # küme → kurye
    rationale: str | None = None                  # LLM ajanı doldurur
    details: dict | None = None                   # maliyet matrisi vb. (dışa aktarım ve açıklama için)


@dataclass(frozen=True)
class NoteView:
    id: str
    day: int
    minute: int
    courier: str
    lat: float
    lng: float
    barcode: str | None
    text: str


@dataclass(frozen=True)
class DeliveryEvent:
    day: int
    courier: str
    address: int
    ok: int
    fail: int
    reason: str | None
    hinted: bool


@runtime_checkable
class AssignmentPolicy(Protocol):
    name: str

    def assign(self, ctx: DayContext, clusters: Sequence[ClusterView], couriers: Sequence[CourierView]) -> AssignmentDecision: ...


@runtime_checkable
class MemoryPolicy(Protocol):
    name: str

    def hints_for(self, ctx: DayContext, courier: str, stops: Sequence[StopView]) -> dict[int, list[HintView]]: ...

    def ingest(self, ctx: DayContext, notes: Sequence[NoteView], events: Sequence[DeliveryEvent]) -> None: ...

    def reader(self) -> MemoryReader: ...


class PolicyError(RuntimeError):
    pass


def validate_mapping(policy_name: str, mapping: dict[int, str], clusters: Sequence[ClusterView],
                     couriers: Sequence[CourierView]) -> None:
    cl = {c.id for c in clusters}
    avail = {c.id for c in couriers if c.available}
    if set(mapping) != cl:
        raise PolicyError(f"{policy_name}: eşleme tüm kümeleri kapsamıyor (eksik: {sorted(cl - set(mapping))}, fazla: {sorted(set(mapping) - cl)})")
    used = list(mapping.values())
    if len(set(used)) != len(used):
        raise PolicyError(f"{policy_name}: aynı kurye birden fazla kümeye atanmış")
    bad = [c for c in used if c not in avail]
    if bad:
        raise PolicyError(f"{policy_name}: müsait olmayan ya da bilinmeyen kurye: {bad}")

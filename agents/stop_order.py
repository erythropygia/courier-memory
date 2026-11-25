"""Gerçek gün: kümeleme motorunun rota sırasını kümenin duraklarına bağlar (agents/real_day.py; OSRM önbellek aracı da aynı fonksiyonu kullanır).

Rota sırasındaki koordinatlar durak listesindekinden birkaç metre farklı olabilir (ayrı kaynaklar). Tam eşleşme yerine her sıra
noktası, kümenin henüz kullanılmamış en yakın durağına (en çok THRESHOLD_M) bağlanır; eşleşmeyen duraklar rotada kendilerine en yakın
konumdan sonra araya eklenir (sona değil: kurye kümede geri dönüp zikzak çizmesin).
"""
from __future__ import annotations

import math

THRESHOLD_M = 150.0


def _m(a, b) -> float:
    kx = 111320 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[0] - b[0]) * 110570, (a[1] - b[1]) * kx)


def route_order(stops: list, cluster_field: int, cluster_j: int, seq: list) -> list[int]:
    """stops: [lat, lng, …] satırları; cluster_field: küme sütununun indeksi; seq: motorun [lat, lng] sırası. Dönüş: durak indeksleri."""
    members = [i for i, d in enumerate(stops) if d[cluster_field] == cluster_j]
    empty = set(members)
    order: list[int] = []
    for p in seq:
        if not empty:
            break
        i = min(empty, key=lambda q: _m(p, stops[q]))
        if _m(p, stops[i]) <= THRESHOLD_M:
            order.append(i)
            empty.discard(i)
    for i in sorted(empty):                                       # kalanlar: rotada en yakın durağın hemen arkasına
        if not order:
            order.append(i)
            continue
        k = min(range(len(order)), key=lambda n: _m(stops[i], stops[order[n]]))
        order.insert(k + 1, i)
    return order

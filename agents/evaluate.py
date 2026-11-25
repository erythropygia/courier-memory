"""Hafıza Ajanı'nın doğruluğunu notların gizli karşılığıyla ölçer.

python -m agents.evaluate --n 60            # CM_LLM_MODE'a göre (mock/live/record/replay)
Çıktı: data/memory_evaluation.json ve simülatöre verilecek parse_accuracy önerisi.
"""
from __future__ import annotations

import argparse
import json
import random
import tempfile
from pathlib import Path

from . import Services
from .guardrails import find_pii
from .rundata import ROOT


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agents.evaluate")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--run", default=None)
    ap.add_argument("--out", default=str(ROOT / "data" / "memory_evaluation.json"))
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as td:
        sv = Services.create(a.run, memory_file=Path(td) / "mem.json")
        truth = sv.run.notes_truth()
        evald = set(sv.run.eval_days)
        pool = [n for n in sv.run.notes() if n["day"] in evald]
        random.Random(a.seed).shuffle(pool)
        by_diff: dict[str, list] = {}
        for n in pool:
            by_diff.setdefault(truth[n["id"]]["difficulty"], []).append(n)
        # zorluk türlerinden dengeli örneklem
        sample: list[dict] = []
        quotas = {"normal": 0.5, "pii": 0.15, "ambiguous": 0.15, "wrong": 0.1, "noise": 0.1}
        for d, q in quotas.items():
            sample += by_diff.get(d, [])[: max(1, int(a.n * q))]
        rows = []
        for n in sample:
            t = truth[n["id"]]
            sv.book.reset(n["day"])
            r = sv.memory.process(n["day"], n["courier"], n["text"], n["lat"], n["lng"], n["barcode"], n["minute"], note_id=n["id"])
            stored = r.get("hint") or ""
            row = {"id": n["id"], "difficulty": t["difficulty"], "status": r["status"], "degraded": r.get("degraded", False)}
            if t["difficulty"] == "noise":
                row["correct"] = r["status"] == "noise"
            else:
                addr_ok = r["address"] is not None and r["address"]["id"] == t["address"]
                kind_ok = r.get("type") == t["stated_kind"]
                row.update(address_correct=addr_ok, type_correct=kind_ok, correct=addr_ok and kind_ok and r["status"] in ("saved", "updated"),
                           uncertain=r["status"] == "uncertain")
            row["personal_data_leaked"] = bool(find_pii(stored))
            if t["pii"]:
                row["personal_data_detection"] = bool(r.get("personal_data_redacted"))
            rows.append(row)
    q = [r for r in rows if r["difficulty"] != "noise"]
    acc = sum(r["correct"] for r in q) / max(1, len(q))
    res = {
        "app_data": True, "mode": sv.llm.mode, "n": len(rows),
        "parse_accuracy": round(acc, 3),
        "address_accuracy": round(sum(r["address_correct"] for r in q) / max(1, len(q)), 3),
        "type_accuracy": round(sum(r["type_correct"] for r in q) / max(1, len(q)), 3),
        "uncertain_rate": round(sum(r["uncertain"] for r in q) / max(1, len(q)), 3),
        "noise_accuracy": round(sum(r["correct"] for r in rows if r["difficulty"] == "noise") / max(1, sum(1 for r in rows if r["difficulty"] == "noise")), 3),
        "personal_data_leak": sum(r["personal_data_leaked"] for r in rows),
        "personal_data_detection_rate": round(sum(r.get("personal_data_detection", False) for r in rows) / max(1, sum(1 for r in rows if "personal_data_detection" in r)), 3),
        "by_difficulty": {d: round(sum(r["correct"] for r in rows if r["difficulty"] == d) / max(1, sum(1 for r in rows if r["difficulty"] == d)), 3)
                         for d in sorted({r["difficulty"] for r in rows})},
        "rows": rows,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, ensure_ascii=False, indent=1))
    print(f"\nSimülasyonu ölçülen doğrulukla yeniden koş:\n  python -m cm_sim.run --demo --set memory.parse_accuracy={res['parse_accuracy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

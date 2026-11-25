"""Ajan başına token kullanımı: canlı ölçüm varsa onu, yoksa gerçek araç çıktılarıyla kurulan temsili
çağrı dizilerinden tahmin kullanır.

python -m agents.cost            → data/demo_run/token_usage.json

Tahmin yöntemi: Her ajan için tipik araç çağrı dizisi (ör. Hafıza: yakın adresler → hafıza → yaz → sonuç),
demo gününün gerçek araç çıktılarıyla kurulur. Her isteğin boyutu ölçülür:
  - ön ek = araç tanımları + sistem istemi
  - mesajlar = kullanıcı + önceki turlar + araç sonuçları
Token ≈ karakter / CHARACTER_TOKEN (Türkçe + JSON için temkinli 3,0). Çıktı tokenı tur başına varsayımdır
(düşünme dahil). Canlı ölçüm (`data/usage.jsonl`) geldiğinde ölçülen ortalamalar kullanılır.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
from pathlib import Path

from . import Services
from .llm import LLM

CHARACTER_TOKEN = 3.0
# Tur başına çıktı tokenı varsayımı (düşünme + metin + araç girdisi)
OUTPUT_MID_TURN = {"low": 150, "medium": 300}
OUTPUT_LAST_TURN = {"propose_assignment": 1200, "ask_assignment": 600, "memory": 350, "briefing": 700, "orchestrator": 1200,
                 "ask_orchestrator": 600, "harvest": 300}
AGENT_EFFORT = {"propose_assignment": "medium", "ask_assignment": "medium", "memory": "medium", "briefing": "low", "orchestrator": "medium",
             "ask_orchestrator": "medium", "harvest": "medium"}


def _script_from_trace(events: list[dict]) -> list[dict]:
    """Kurallı yedeğin izinden (agents/trace.py) aynı araçları aynı sırayla çağıran yanıt dizisi: karar metinleri modelin
    metin blokları, arac olayları araç çağrıları olur. Böylece istek boyutları gerçek araç çıktılarıyla ölçülür."""
    out, texts, n = [], [], 0
    for e in events:
        if e["type"] == "decision":
            texts.append(e["text"])
        elif e["type"] == "tool":
            n += 1
            content = [{"type": "text", "text": t} for t in texts] + [{"type": "tool_use", "id": f"t{n}", "name": e["tool"], "input": e["input"]}]
            out.append({"stop_reason": "tool_use", "content": content})
            texts = []
    return out


class MeasurementLLM(LLM):
    """İstekleri ağa göndermez; senaryodaki yanıtları sırayla döndürür ve istek boyutlarını kaydeder."""

    def __init__(self, script: list[dict]):
        super().__init__(mode="live")
        self.script = list(script)
        self.requests: list[dict] = []

    def _call(self, agent: str, req: dict) -> dict:
        self.requests.append(json.loads(json.dumps(req, ensure_ascii=False, default=str)))
        return self.script.pop(0)


def _tu(i: int, name: str, inp: dict, text: str = "") -> dict:
    content = ([{"type": "text", "text": text}] if text else []) + [{"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}]
    return {"stop_reason": "tool_use", "content": content}


def _measure(requests: list[dict]) -> dict:
    """İstek listesinden token tahmini (önbelleksiz ve önbellekli)."""
    rows = []
    for r in requests:
        prefix = len(json.dumps(r.get("tools", []), ensure_ascii=False)) + len(json.dumps(r["system"], ensure_ascii=False))
        msgs = len(json.dumps(r["messages"], ensure_ascii=False))
        rows.append((prefix / CHARACTER_TOKEN, msgs / CHARACTER_TOKEN))
    input = sum(p + m for p, m in rows)
    # Önbellekli: ilk istek her şeyi yazar; sonrakiler bir önceki isteğin tamamını okur, yalnız yeni kısmı yazar.
    write, read, prev = 0.0, 0.0, 0.0
    for p, m in rows:
        cur = p + m
        read += prev
        write += cur - prev
        prev = cur
    return {"request": len(rows), "input": round(input), "cached_read": round(read), "cached_write": round(write),
            "prefix": round(rows[0][0]) if rows else 0}


def estimate(run_dir: str | None = None) -> dict:
    with tempfile.TemporaryDirectory() as td:
        sv = Services.create(run_dir, mode="mock", memory_file=Path(td) / "m.json")
        m = sv.run.meta
        day, cur = m["critical"]["day"], m["critical"]["courier"]
        sv.book.reset(day)
        out: dict[str, dict] = {}

        # --- Atama: öneri
        from .assignment import AssignmentTools, AssignmentAgent
        ar = AssignmentTools(sv.run, day)
        solve = ar.solve_assignment({"exclude": [], "pin": []})
        k0 = solve["assignment"][0]["cluster_id"]
        mock = sv.assignment._propose_mock(ar)
        script = [_tu(1, "day_summary", {}, "Önce günün özetine bakıyorum."),
                  _tu(2, "solve_assignment", {"exclude": [], "pin": []}, "Şimdi en düşük maliyetli atamayı çözüyorum."),
                  _tu(3, "cluster_detail", {"cluster_id": k0}, "Yabancı durağı en çok olan kümeye bakıyorum."),
                  _tu(4, "save_assignment", {"assignment": solve["assignment"], "rationale": mock["rationale"], "highlights": mock["highlights"]})]
        llm = MeasurementLLM(script)
        AssignmentAgent(sv.run, llm).propose(day)
        out["propose_assignment"] = _measure(llm.requests)

        # --- Atama: senaryo sorusu
        a2 = AssignmentTools(sv.run, day).solve_assignment({"exclude": [cur], "pin": []})
        script = [_tu(1, "solve_assignment", {"exclude": [cur], "pin": []}, "Kuryeyi çıkarıp yeniden çözüyorum."),
                  _tu(2, "respond", {"response": "Kurye çıkarılınca beklenen başarısız teslim biraz artıyor; bir kümede kurye değişiyor. "
                                              "Yeni kurye yabancı duraklarda hafıza notlarından ipucu alacak.", "assignment": a2["assignment"]})]
        llm = MeasurementLLM(script)
        AssignmentAgent(sv.run, llm).ask(day, f"{m['critical']['courier_name']} gelmezse ne olur?")
        out["ask_assignment"] = _measure(llm.requests)

        # --- Hafıza: bir not
        from .memory import MemoryAgent
        stop = sv.run.route_of(day, cur)["stops"][5]
        a = int(stop[0])
        script = [_tu(1, "near_addresses", {"lat": stop[1], "lng": stop[2], "radius_m": 80}, "Notun adresini buluyorum."),
                  _tu(2, "address_memory", {"address_id": a}),
                  _tu(3, "write_memory", {"address_id": a, "type": "bell", "hint": "Zil çalışmıyor; alıcıyı telefonla arayın."}),
                  _tu(4, "report_result", {"status": "saved", "address_id": a, "type": "bell", "hint": "Zil çalışmıyor; alıcıyı telefonla arayın.",
                                           "personal_data_redacted": True, "summary": "Not adrese bağlandı; kişisel bilgi kaydedilmedi.", "question": None})]
        llm = MeasurementLLM(script)
        MemoryAgent(sv.run, sv.book, llm).process(day, cur, "zil bozuk Ayşe hanım çok huysuz telefonla arayın", stop[1], stop[2], None, stop[4])
        out["memory"] = _measure(llm.requests)

        # --- Brifing
        from .briefing import BriefingAgent, BriefingTools
        rr = BriefingTools(sv.run, sv.book, day, cur).route_risks()
        final = {"morning_briefing": "Günaydın. " * 30, "door_sentences": [{"address": h["address"], "sentence": h["hints"][0][:80]} for h in rr["hinted_stops"]],
                 "warnings": rr["warnings"][:3]}
        script = [_tu(1, "route_risks", {}), {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(final, ensure_ascii=False)}]}]
        llm = MeasurementLLM(script)
        BriefingAgent(sv.run, sv.book, llm).prepare(day, cur)
        out["briefing"] = _measure(llm.requests)

        # --- Orkestratör: günün planı + müdürün senaryo sorusu (ekonomi hesabına Faz 2'de girdi)
        from .orchestrator import Orchestrator
        mock_plan = sv.orchestrator.plan(day)
        llm = MeasurementLLM(_script_from_trace(mock_plan["trace"]))
        Orchestrator(sv.run, sv.book, llm).plan(day)
        out["orchestrator"] = _measure(llm.requests)
        o = mock_plan["proposal"]
        who = o["borrowed"][0]["name"] if o["borrowed"] else m["critical"]["courier_name"]
        ask_mock = sv.orchestrator.ask(day, f"{who} gelmezse ne olur?", o)
        llm = MeasurementLLM(_script_from_trace(ask_mock["trace"]))
        Orchestrator(sv.run, sv.book, llm).ask(day, f"{who} gelmezse ne olur?", o)
        out["ask_orchestrator"] = _measure(llm.requests)

        # --- Hasat: günün soruları (her cevap ayrıca bir Hafıza Ajanı çağrısıdır; ekonomide 'harvest_answer' = hafiza profili)
        from .harvest import HarvestAgent
        mock_h = sv.harvest.agent.plan(day)
        llm = MeasurementLLM(_script_from_trace(mock_h["trace"]))
        HarvestAgent(sv.run, sv.book, llm).plan(day)
        out["harvest"] = _measure(llm.requests)

    for k, v in out.items():
        ef = AGENT_EFFORT[k]
        v["output"] = OUTPUT_MID_TURN[ef] * (v["request"] - 1) + OUTPUT_LAST_TURN[k]
        v["source"] = "estimate"
    return out


def measurement(log: Path) -> dict:
    """Canlı kullanım günlüğünden ajan başına çağrı ortalaması (bir ajan çağrısı = ardışık istekler)."""
    if not log.exists():
        return {}
    per: dict[str, list[dict]] = defaultdict(list)
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            per[r["agent"]].append(r)
    out = {}
    name_map = {"assignment": "propose_assignment", "ask_assignment": "ask_assignment", "memory": "memory", "briefing": "briefing",
                "orchestrator": "orchestrator", "ask_orchestrator": "ask_orchestrator", "harvest": "harvest"}
    for ag, rows in per.items():
        key = name_map.get(ag, ag)
        n = len(rows)
        out[key] = {"request_total": n, "input_request_mean": sum(r["input_tokens"] for r in rows) / n,
                    "output_request_mean": sum(r["output_tokens"] for r in rows) / n,
                    "cache_read_request_mean": sum(r["cache_read_input_tokens"] for r in rows) / n,
                    "cache_write_request_mean": sum(r["cache_creation_input_tokens"] for r in rows) / n,
                    "duration_request_mean": sum(r["seconds"] for r in rows) / n}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agents.cost")
    ap.add_argument("--run", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    from .rundata import RunData
    rd = RunData(a.run)
    t = estimate(a.run)
    lg = LLM(mode="mock").usage_log
    m = measurement(lg)
    for k, v in m.items():          # ölçüm varsa tahminin istek sayısını koruyup istek başı değerleri ölçümle değiştir
        if k in t:
            n = t[k]["request"]
            t[k].update(input=round(v["input_request_mean"] * n + v["cache_read_request_mean"] * n + v["cache_write_request_mean"] * n),
                        output=round(v["output_request_mean"] * n), cached_read=round(v["cache_read_request_mean"] * n),
                        cached_write=round(v["cache_write_request_mean"] * n), source="measurement", measurement=v)
    res = {"app_data": True, "character_token": CHARACTER_TOKEN, "agents": t,
           "note": "Çağrı başına token. 'tahmin': temsili çağrı dizisinden; 'olcum': canlı kullanım günlüğünden."}
    out = Path(a.out) if a.out else rd.dir / "token_usage.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in t.items():
        print(f"{k:11s} istek {v['request']}  girdi ~{v['input']:>6}  çıktı ~{v['output']:>5}  ön ek ~{v['prefix']:>5}  ({v['source']})")
    print(f"Yazıldı: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

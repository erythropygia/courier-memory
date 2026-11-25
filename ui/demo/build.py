"""Builds the QR demo page (ui/demo/index.html): what each agent took, thought, did and gave in one past demo run.

Runs the same eight steps as the /flow/ UI in-process (FastAPI TestClient, no server, no AWS), turns the responses into
a compact view model and embeds it in template.html. The result is one self-contained file: open it anywhere.

  PYTHONPATH=.:sim PYTHONUTF8=1 CM_LLM_MODE=mock .venv/bin/python ui/demo/build.py [--url https://.../demo/]

--url also writes the QR code (needs `pip install segno`) to ui/demo/qr.svg and ui/story/data/demo-qr.svg; the
closing scene of the story UI shows it.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("CM_LLM_MODE", "mock")

HERE = Path(__file__).resolve().parent
TEMPLATE, OUT = HERE / "template.html", HERE / "index.html"
NOTE_TEXT = "sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakıp yürüyün. B blok kapı şifresi 2580"

STATUS_TR = {"finalized": "kesinleşti", "rejected": "reddedildi", "error": "hata"}
KIND_TR: dict = {}
TOOL_TR = {
    "read_volume": "Günün hacmini oku", "capacity_gap": "Kapasite açığını hesapla",
    "neighbor_candidates": "Komşu şubeden aday sırala", "core_assignment": "Çekirdek bölgeli atama",
    "delivery_time_analysis": "Teslim saati örüntüsü", "apply_time_constraint": "Saat bulgularını rotaya al",
    "time_alternatives": "Kaydırılamayanlara alternatif", "compute_route": "Hafızalı rota hesapla",
    "sorting_plan": "Ayrıştırma ve raf planı", "present_proposal": "Müdüre öneri sun",
    "route_risks": "Rota risklerini oku", "near_addresses": "Yakındaki adresleri bul", "write_memory": "Hafızaya yaz",
    "memory_gaps": "Hafıza boşluklarını bul", "save_questions": "Soruları kaydet", "recurring_failure": "Tekrarlayan başarısızlık",
    "time_confirmations": "Saat teyidi bekleyenler", "harvest_plan": "Hasat planını kapat",
    "trend": "Son 5 gün ↔ önceki 5 gün", "hint_outcomes": "İpucuna rağmen başarısızlar",
    "recurring_problems": "Hafızasız tekrarlayan sorun", "duration_estimate": "Süre tahmini sapması",
    "assignment_check": "Atama kontrolü", "apply": "Düzeltmeleri uygula", "present_report": "Sabah raporu",
    "branch_summary": "Şube özeti", "hard_blocks": "Zor bloklar", "open_question": "Kıdemliye soru aç",
    "present_branch_report": "Müdüre şube raporu",
}


def short(v, n=1800):
    """Compact JSON for the 'details' drawer; long payloads are cut."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            pass
    s = json.dumps(v, ensure_ascii=False, indent=1)
    return s if len(s) <= n else s[:n] + "\n… (kısaltıldı)"


def trim(v, depth=0):
    """Real tool parameters, kept readable: long lists cut to 8 items, deep objects summarized."""
    if isinstance(v, str):
        try:
            v = json.loads(v) if v[:1] in "{[" else v
        except ValueError:
            pass
    if isinstance(v, list):
        out = [trim(x, depth + 1) for x in v[:8]]
        return out + [f"… +{len(v) - 8}"] if len(v) > 8 else out
    if isinstance(v, dict):
        return {k: trim(x, depth + 1) for k, x in v.items()} if depth < 3 else "{…}"
    if isinstance(v, str) and len(v) > 400:
        return v[:400] + "…"
    return v


def from_trace(events):
    """Agent trace → turns: why (the decision just before) · tool call with its real parameters · result · full output."""
    turns, pending, source = [], [], "rule"
    for e in events:
        source = e.get("source", source) if e.get("source") in ("llm", "rule") else source
        if e["type"] == "decision":
            pending.append(e["text"])
        elif e["type"] == "tool":
            turns.append({"why": " ".join(pending), "tool": e["tool"], "name": TOOL_TR.get(e["tool"], e["tool"]),
                          "params": trim(e.get("input") or {}), "summary": "", "output": "", "source": e.get("source", source)})
            pending = []
        elif e["type"] == "result":
            for t in reversed(turns):
                if t.get("tool") == e["tool"] and not t["summary"]:
                    t["summary"], t["output"] = e.get("summary", ""), short(e.get("data", {}))
                    break
        elif e["type"] == "error":
            turns.append({"why": "", "tool": e.get("tool", ""), "name": "Araç hatası", "params": {}, "summary": e.get("text", ""), "output": ""})
        elif e["type"] == "fallback":
            pending.append("Canlı yol tamamlanamadı, kurallı yedek devam etti: " + e.get("text", ""))
    for t in turns:                                             # finish tools have no result: their parameters ARE the decision
        if t.get("tool") and not t["summary"]:
            t["summary"] = "Nihai karar: ajan çıktısını bu parametrelerle verdi (aşağıda “Ne verdi”)."
    if pending:
        turns.append({"why": " ".join(pending)})                # closing decision without a tool call
    return turns, source


def from_steps(steps):
    return [{"why": "", "tool": s["tool"], "name": TOOL_TR.get(s["tool"], s["tool"]), "params": trim(s.get("input") or {}),
             "summary": s.get("summary", ""), "output": ""} for s in steps]


def request(method, path, body, resp):
    """The real HTTP call that fed the agent and what it answered (trimmed for the page)."""
    return {"call": f"{method} {path}", "body": trim(body) if body else None, "response": short(trim(resp), 2500)}


def run() -> dict:
    global KIND_TR
    from fastapi.testclient import TestClient
    from api.main import app
    from agents.cards import TITLE as KIND_TR

    c = TestClient(app)

    log: dict[str, dict] = {}

    def call(method, path, body=None, key=None):
        r = c.request(method, path, json=body)
        r.raise_for_status()
        out = r.json()
        if key:
            log.setdefault(key, []).append(request(method, path, body, out))
        return out

    meta, status = call("GET", "/api/meta"), call("GET", "/api/status")
    day, cour, name = meta["critical"]["day"], meta["critical"]["courier"], meta["critical"].get("courier_name", "")
    mode = status.get("llm_mode") or status.get("mode") or os.environ["CM_LLM_MODE"]
    call("POST", "/api/demo/reset", {"day": day})
    try:
        sid = call("POST", "/api/orchestrator/start", {"day": day}, key="orch")["session_id"]
        for _ in range(900):
            orch = call("GET", f"/api/orchestrator/session/{sid}?after=0")
            if orch["status"] != "running":
                break
            time.sleep(0.2)
        if orch["status"] == "awaiting_approval":            # escalated (should not happen on the demo day): approve to continue
            call("POST", f"/api/orchestrator/session/{sid}/decision", {"decision": "approval"})
        log["orch"].append(request("GET", f"/api/orchestrator/session/{sid}", None,
                                   {k: v for k, v in orch.items() if k not in ("events", "plan")}))
        brief = call("GET", f"/api/briefing/{day}/{cour}", key="brief")
        cards = call("GET", f"/api/cards/{day}/{cour}?all=true")
        stop = next((x for x in cards["stops"] if not x["cards"]), cards["stops"][0])
        note = call("POST", "/api/note", {"day": day, "courier": cour, "lat": stop["lat"], "lng": stop["lng"], "text": NOTE_TEXT}, key="note")
        base = {"day": day, "courier": cour, "next_order": stop["order"]}
        ap = [call("POST", "/api/approach", {**base, "lat": stop["lat"] + 0.006, "lng": stop["lng"]}, key="ap")]
        ap.append(call("POST", "/api/approach", {**base, "lat": stop["lat"] + 0.002, "lng": stop["lng"]}, key="ap"))
        ap.append(call("POST", "/api/approach", {**base, "lat": stop["lat"], "lng": stop["lng"], "shown": [k["id"] for k in ap[1]["cards"]]}, key="ap"))
        harvest = call("POST", "/api/harvest/plan", {"day": day}, key="harvest")
        review = call("POST", "/api/review/run", {"day": day}, key="review")
        region = call("POST", "/api/region/run", {"day": day}, key="region")
    finally:
        call("POST", "/api/demo/reset", {"day": day})        # leave the live memory as it was

    from agents.orchestrator import ESCALATE_COURIER_OVER_MIN, ESCALATE_TOTAL_OVER_MIN
    from api.main import sv
    o = sv().sessions.orch
    CODE_TR = {"capacity": "kapasite açığı", "overtime": "ciddi fazla mesai", "plan_worse": "plan kötüleşti", "agent_failed": "ajan çalışamadı"}
    escalated = {d: [r["code"] for r in o.plan(d)["escalation"]] for d in o.run.eval_days}   # how often the manager is called
    escalated = {d: c for d, c in escalated.items() if c}
    why = sorted({CODE_TR.get(c, c) for cs in escalated.values() for c in cs})
    gate = [e for e in orch["events"] if e["type"] in ("escalation", "auto_decision")]
    reasons = [r["text"] for e in gate if e["type"] == "escalation" for r in e["reasons"]]
    auto = next((e for e in gate if e["type"] == "auto_decision"), None)
    p = orch["proposal"] or {}
    p_gap = next((json.loads(e["data"]) if isinstance(e["data"], str) else e["data"] for e in orch["events"]
                  if e["type"] == "result" and e["tool"] == "capacity_gap"), {}).get("shortfall")
    tot = p.get("total") or {}
    o_tools, o_src = from_trace(orch["events"])
    h_tools, h_src = from_trace(harvest["trace"])
    r_tools, r_src = from_trace(review["trace"])
    g_tools, g_src = from_trace(region["trace"])
    src = lambda m: "rule" if m == "mock" else "llm"
    steps = [
        {"agent": "Orkestratör Ajanı", "color": "blue", "title": "Gün planlanır",
         "role": "Günü yönetir: hacim, kapasite açığı, komşu şubeden kurye, çekirdek bölgeli atama, hafızalı rota.",
         "took": [f"Gün {day} teslim kayıtları ve gönderi hacmi", "Kadro: izinli, yeni, yedek kurye", "Şube hafızası (adres notları)",
                  "Komşu şubenin aday kuryeleri"],
         "trace": o_tools, "source": o_src,
         "gave": {"head": "Gerekçeli gün planı", "kv": [[tot.get("courier_count", "–"), "kurye"],
                  ["%" + str(round(100 * p.get("own_zone_share", 0))), "kendi bölgesinde"],
                  [tot.get("expected_fails", "–"), "beklenen başarısız teslim"]],
                  "list": (p.get("rationale") or [])[:4], "warn": (p.get("risks") or [])[:2]}},
        {"agent": "Acil Durum Kapısı", "color": "gray", "title": "Müdür yalnız acil durumda çağrılır",
         "role": "Zincir temassız çalışır. Kod (LLM değil) planı üç acil durum eşiğine karşı denetler; hiçbiri yoksa plan "
                 "müdüre gitmeden kesinleşir.",
         "took": ["Orkestratör'ün planı ve sayıları",
                  "Kapasite açığı kapandı mı (komşu şubeden gelen kurye sayısı)",
                  f"Fazla mesai: tek kuryede vardiya bandı üstü ≥ {ESCALATE_COURIER_OVER_MIN} dk ya da şubede toplam ≥ {ESCALATE_TOTAL_OVER_MIN} dk",
                  "Ajan çalıştı mı; plan geçmişe bakmayan atamadan iyi mi"],
         "trace": [{"why": "Plan hazır. Müdürü çağırmayı gerektiren bir acil durum var mı?", "tool": "escalation",
                    "name": "Acil durum eşiklerini denetle",
                    "params": {"kurye_basi_bant_ustu_esik_dk": ESCALATE_COURIER_OVER_MIN, "sube_toplam_bant_ustu_esik_dk": ESCALATE_TOTAL_OVER_MIN,
                               "kapasite_acigi": p_gap, "komsu_subeden_gelen": len(p.get("borrowed") or []),
                               "toplam_bant_ustu_dk": (p.get("total") or {}).get("over_band_min"),
                               "beklenen_basarisiz": (p.get("total") or {}).get("expected_fails"),
                               "gecmise_bakmadan_beklenen_basarisiz": (p.get("comparison") or {}).get("history_blind_expected_fails")},
                    "summary": "eşik aşılmadı → plan temassız kesinleşti" if auto else "eşik aşıldı → müdüre eskale: " + " ".join(reasons),
                    "output": short({"escalation": reasons, "decision": "auto_approval" if auto else "awaiting_approval"})},
                   {"why": auto["text"] if auto else "Plan müdür onayına kadar bekler."}], "source": "rule",
         "gave": {"head": "Plan kesinleşti · müdür çağrılmadı" if auto else "Müdüre eskale edildi",
                  "kv": [["temassız" if auto else "eskale", "karar"], [STATUS_TR.get(orch["status"], orch["status"]), "durum"],
                         [f"{len(escalated)}/{len(o.run.eval_days)}", "günde müdür çağrıldı"]],
                  "list": ["Kesinleşen plan Brifing, durak kartı ve Hasat ajanlarının girdisi olur.",
                           "Simülasyonda müdürün çağrıldığı günler: " + (", ".join(map(str, escalated)) or "yok")
                           + (f". Sebep: {', '.join(why)}" if why else "") + ". Müdür sistemin göremediği bir acil durumu da kendisi bildirebilir."] + reasons}},
        {"agent": "Brifing Ajanı", "color": "violet", "title": "Kuryeye sabah brifingi",
         "role": f"Bölgeyi bilmeyen ödünç kurye {name} için rotadaki riskleri ve hafızadaki notları sesli özete çevirir.",
         "took": ["Kesinleşen plan ve kuryenin rotası", "Hafızadaki adres notları", "Dönüş saati tahmini (EtaModel)"],
         "trace": from_steps(brief.get("steps", [])), "source": src(brief.get("mode")),
         "gave": {"head": "Kuryenin dinlediği brifing", "say": brief.get("morning_briefing", ""),
                  "kv": [[brief.get("estimated_return", "–"), "tahmini dönüş"], [len(brief.get("door_sentences") or []), "durakta kapı cümlesi"]],
                  "warn": brief.get("warnings") or []}},
        {"agent": "Hafıza Ajanı", "color": "green", "title": "Kurye kapıda not bırakır",
         "role": "Kurye notunu adrese bağlar, türünü çıkarır; kişisel veriyi ve kapı şifresini araç düzeyinde ayıklar.",
         "took": [f"Kuryenin serbest notu: “{NOTE_TEXT}”", "Kuryenin konumu (yakındaki adresler)"],
         "trace": from_steps(note.get("steps", [])), "source": src(note.get("mode")),
         "gave": {"head": "Hafızaya yazılan", "say": note.get("hint", ""),
                  "kv": [[KIND_TR.get(note.get("type"), note.get("type", "–")), "tür"], ["ayıklandı" if note.get("personal_data_redacted") else "temiz", "şifre / kişisel veri"]],
                  "list": [note.get("summary", "")]}},
        {"agent": "Durak Kartları", "color": "teal", "title": "Sonraki kurye aynı kapıya yaklaşır", "rule_only": True,
         "role": "LLM yok, kural: park bilgisi durağa ~400 m kala, kapı bilgisi ~60 m kala söylenir; bir kart iki kez söylenmez.",
         "took": ["Kuryenin anlık konumu", "Durağın hafıza kartları"],
         "trace": [{"why": f"Kurye durağa {a['stop']['distance_m']} m uzakta; bu anda söylenecek kart var mı?", "tool": "approach",
                    "name": "Konuma göre kart seç", "params": trim(r["body"]),
                    "summary": (f"an: {a.get('moment')} · söylenecek: “{a['to_speak']}”" if a.get("to_speak")
                                else f"henüz söylenecek kart yok · bekleyen {a.get('pending')}"), "output": r["response"]}
                   for a, r in zip(ap, log["ap"])], "source": "rule",
         "gave": {"head": "Kuryenin duyduğu", "say": ap[1].get("to_speak") or "—"}},
        {"agent": "Hasat Ajanı", "color": "amber", "title": "Kıdemliye hedefli soru",
         "role": "Yabancı kuryenin gideceği, hafızası boş adresleri bulur; oraya en son giden kıdemliye kısa soru sorar (kurye başına ≤ 3).",
         "took": ["Kesinleşen plan: kim nereye yabancı", "Hafıza boşlukları", "Son günlerin teslim olayları"],
         "trace": h_tools, "source": h_src,
         "gave": {"head": f"{len(harvest['questions'])} soru", "list": [harvest.get("summary", "")],
                  "q": [f"{q.get('courier_name', '')}: {q['question']}" for q in harvest["questions"][:3]]}},
        {"agent": "Değerlendirme Ajanı", "color": "rose", "title": "Ertesi sabah: sistem kendini değerlendirir",
         "role": "Kuryeyi değil sistemin kararlarını değerlendirir: ipucuna rağmen başarısız kaydı teyide alır, süre tahminini ayarlar.",
         "took": ["Son 5 gün ↔ önceki 5 gün", "İpucu gösterilen duraklarda sonuç", "Süre tahmini sapması"],
         "trace": r_tools, "source": r_src,
         "gave": {"head": "Sabah raporu", "list": [(review.get("report") or {}).get("summary", "")],
                  "good": (review.get("report") or {}).get("going_well", []), "warn": (review.get("report") or {}).get("going_badly", [])}},
        {"agent": "Bölge Ajanı", "color": "indigo", "title": "Şube raporu ve hafıza boşlukları",
         "role": "Blok zorluğunu hesaplar; zor ama hafızası boş bloklar için kıdemliye soru açar, müdüre kısa rapor sunar.",
         "took": ["Blok istatistikleri (~300 m)", "Hafıza kapsamı"],
         "trace": g_tools, "source": g_src,
         "gave": {"head": "Müdüre", "list": region.get("manager_summary", []),
                  "q": [q["question"] for q in region.get("questions", [])[:2]]}},
    ]
    for s, key in zip(steps, ["orch", None, "brief", "note", "ap", "harvest", "review", "region"]):
        s["requests"] = log.get(key, []) if key else []
    return {"day": day, "courier": name, "mode": mode, "built": time.strftime("%d.%m.%Y"), "steps": steps}


def write_qr(url: str) -> None:
    import segno

    qr = segno.make(url, error="m")
    for path in (HERE / "qr.svg", HERE.parent / "story" / "data" / "demo-qr.svg"):
        qr.save(str(path), scale=8, border=2, dark="#0d1424", light="#ffffff")
        print("QR:", path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="public URL of the page; writes the QR code")
    args = ap.parse_args()
    data = run()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    OUT.write_text(html, encoding="utf-8", newline="\n")
    print(OUT, f"{OUT.stat().st_size / 1e3:.0f} KB", len(data["steps"]), "adım")
    if args.url:
        write_qr(args.url)


if __name__ == "__main__":
    main()

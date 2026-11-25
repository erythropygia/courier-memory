"""Sahne 3–7'nin kayıtlı yanıtlarını üretir: API'ye ulaşılamazsa arayüz bunları "API yok · kayıtlı yanıt" etiketiyle kullanır.

  CM_LLM_MODE=mock uvicorn api.main:app --port 8000      (ayrı pencerede; 8080 kullanılmaz)
  python ui-story/tools/record_fallback.py [http://127.0.0.1:8000]

Demo akışını sırayla oynatır (canlı hafıza önce ve sonra sıfırlanır) ve yanıtları `data/fallback.json`'a yazar.
Anahtar biçimi `ui-story/js/common.js → CM.api` ile aynıdır: "GET /api/..." ya da "POST /api/...#name".
Demo seçimleri (`demo`) kurallıdır ve burada hesaplanır:
  note_address   Gökhan'ın (O02) gün 32 rotasında, bölgeye yabancı, kapı notu olmayan, en az 8. sıradaki ve sonraki
              günlerde (33–39) başka bir kuryenin gittiği adres; en erken gün, sonra en küçük sıra.
  sonraki     o adrese giden kurye ve gün.
  harvest_gap  Gökhan'ın rotasındaki boşluk sorularından simüle cevabı hafızaya yazılan ve rotayı değiştiren ilki.
  harvest_time   saat teyidi sorularından cevabı teyit olan ve o adrese bugün giden kuryenin rotasını değiştiren ilki.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "data" / "fallback.json"
DAY, COURIER = 32, "O02"
record: dict = {}


def request(path, body=None, name="", keep=True):
    r = urllib.request.Request(API + path, data=None if body is None else json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(r, timeout=300).read())
    if keep:
        record[("POST " if body is not None else "GET ") + path + (f"#{name}" if name else "")] = d
    return d


def reset():
    request("/api/memory/reset", {"day": DAY}, keep=False)


def trim_summary(o):
    sw = o.get("sweep") or {}
    s = o["summary"] or {}
    return {
        "summary": {"memory_routing": s.get("memory_routing"), "preventable_reasons": s.get("preventable_reasons"),
                    "arms": {k: {"label": a["label"], "first_attempt_rate": a["first_attempt_rate"], "fail_by_reason": a["fail_by_reason"]}
                             for k, a in (s.get("arms") or {}).items()}},
        "daily": {k: [{"day": r["day"], "first_attempt_rate": r["first_attempt_rate"]} for r in v] for k, v in (o.get("daily") or {}).items()},
        "long_term": {"summary": {"arms": {k: {"unfamiliar_share": v["unfamiliar_share"]} for k, v in o["long_term"]["summary"]["arms"].items()}}}
        if o.get("long_term") else None,
        "sweep": {"keys": sw.get("keys"), "seeds": sw.get("seeds"), "headline": sw.get("headline"),
                  "rows": [{"params": r["params"], "arms": {k: {"first_attempt_rate": a["first_attempt_rate"]} for k, a in r["arms"].items()}}
                           for r in sw.get("rows", [])]} if sw else None,
        "calibration": {"source": o["calibration"].get("source"), "rows": [{k: r.get(k) for k in ("measure", "explanation", "value", "compatible")}
                                                                       for r in o["calibration"]["rows"]]} if o.get("calibration") else None,
        "ablation": {k: o["ablation"][k] for k in ("seeds", "scenarios", "variants")} if o.get("ablation") else None,
    }


# ------------------------------------------------------------------ demo seçimleri
def route_courier(address, d32):
    for r in d32["routes"]:
        if any(s[0] == address for s in r["stops"]):
            return r["courier"], r["courier_name"]
    return None, None


def selections():
    reset()
    p = request("/api/orchestrator/plan", {"day": DAY}, keep=False)
    request(f"/api/orchestrator/session/{p['session_id']}/decision", {"decision": "approval"}, keep=False)
    b = request(f"/api/briefing/{DAY}/{COURIER}", keep=False)
    F = b["stop_fields"]
    noted = {k["address"] for k in b["door_sentences"]}
    mine = {s[0]: (i + 1, s[F.index("unfamiliar")]) for i, s in enumerate(b["route"]["stops"])}
    candidate = []
    for g in range(DAY + 1, DAY + 8):
        try:
            d = request(f"/api/day/D/{g}", keep=False)
        except urllib.error.HTTPError:
            continue
        for r in d["routes"]:
            if r["courier"] == COURIER:
                continue
            for s in r["stops"]:
                a = s[0]
                if a in mine and mine[a][1] == 1 and a not in noted and mine[a][0] >= 8:   # yabancı duraklar rotanın sonunda
                    candidate.append((g, mine[a][0], a, r["courier"], r["courier_name"]))
    candidate.sort()
    g, order, address, k, name = candidate[0]
    demo = {"note_address": address, "note_order": order, "next": {"day": g, "courier": k, "name": name}}

    d32 = request(f"/api/day/D/{DAY}", keep=False)
    h = request("/api/harvest/plan", {"day": DAY}, keep=False)

    def dene(q, courier):
        reset()
        r0 = request(f"/api/route/{DAY}/{courier}", keep=False)
        c = request("/api/harvest/simulate-answer", {"question_id": q["id"]}, keep=False)
        r1 = request(f"/api/route/{DAY}/{courier}", keep=False)
        is_changed = r0["changes"] != r1["changes"] or r0["comparison"]["memory"]["order"] != r1["comparison"]["memory"]["order"]
        return c, is_changed, r1

    for q in h["questions"]:
        if q["reason"] != "gap" or q["address"] not in mine:
            continue
        c, is_changed, _ = dene(q, COURIER)
        if c.get("memory") and c["memory"]["status"] in ("saved", "updated") and is_changed:
            demo["harvest_gap"] = {"address": q["address"], "courier": COURIER, "courier_name": b["courier_name"]}
            break
    fallback_time = None
    for q in h["questions"]:
        if q["reason"] != "time":
            continue
        k, name = route_courier(q["address"], d32)
        if not k:
            continue
        c, is_changed, r1 = dene(q, k)
        confirmation = (c.get("time") or {}).get("status") == "confirmation"
        if confirmation and is_changed:
            demo["harvest_time"] = {"address": q["address"], "courier": k, "courier_name": name}
            break
        # rotayı değiştiren teyit yoksa kuralın (rota uzamaz) engellediği ilk teyit gösterilir (müdüre alternatif)
        if confirmation and fallback_time is None and any(x["address"] == q["address"] for x in r1.get("time_unshiftable") or []):
            fallback_time = {"address": q["address"], "courier": k, "courier_name": name, "unshiftable": True}
    if "harvest_time" not in demo and fallback_time:
        demo["harvest_time"] = fallback_time
    print("demo seçimleri:", json.dumps(demo, ensure_ascii=False))
    return demo


# ------------------------------------------------------------------ akış (arayüzün çağırdığı sırayla)
def stream(demo):
    reset()
    request("/api/status")
    request("/api/meta")
    # Sahne 3
    p = request("/api/orchestrator/plan", {"day": DAY})
    kid = p["session_id"]
    request(f"/api/orchestrator/session/{kid}/ask", {"question": "Onur gelmezse ne olur?"}, name="onur")
    request(f"/api/orchestrator/session/{kid}/ask", {"question": "Gökhan gelmezse ne olur?"}, name="gokhan")
    request(f"/api/orchestrator/session/{kid}/decision", {"decision": "approval"}, name="approval")
    request(f"/api/orchestrator/session/{kid}?after={p['total_event']}")
    # Sahne 3: indirme okutması → raf (onaylı planla)
    sb = request(f"/api/morning/{DAY}")
    for g in (sb.get("example_shipments") or [])[:8] + [f"G{DAY}-0-1"]:
        request("/api/morning/scan", {"day": DAY, "shipment": g}, name=g)
    # Sahne 4
    b = request(f"/api/briefing/{DAY}/{COURIER}")
    request(f"/api/route/{DAY}/{COURIER}")
    F = b["stop_fields"]
    stops = b["route"]["stops"]
    for k in b["door_sentences"]:
        if k["order"] <= demo["note_order"]:
            for x in k.get("records") or []:
                request("/api/memory/feedback", {"day": DAY, "record": x["id"], "valid": True}, name=x["id"])
    s = next(x for x in stops if x[F.index("address")] == demo["note_address"])
    place = {"lat": s[F.index("lat")], "lng": s[F.index("lng")], "minute": round(s[F.index("eta")])}
    notes = [("personal", "site güvenliği kimlik istiyor, kayıt yaptırınca giriyorsunuz. yönetici Ahmet bey 0532 412 55 10"),
             ("noise", "trafik berbattı bugün"),
             ("park", "sitenin önünde park yeri yok, aracı arka sokaktaki otoparka bırakıp yürüyün"),
             ("access", "asansör yok, 4. kata merdivenle çıkılıyor")]
    request("/api/note", {"day": DAY, "courier": COURIER, "text": notes[0][1], **place}, name=notes[0][0])
    so = demo["next"]
    request(f"/api/briefing/{so['day']}/{so['courier']}")
    for name, text in notes[1:]:
        request("/api/note", {"day": DAY, "courier": COURIER, "text": text, **place}, name=name)
    # Sahne 5
    h = request("/api/harvest/plan", {"day": DAY})
    for key in ("harvest_gap", "harvest_time"):
        d = demo.get(key)
        if not d:
            continue
        q = next((x for x in h["questions"] if x["address"] == d["address"]), None)
        if not q:
            continue
        request(f"/api/route/{DAY}/{d['courier']}", name="before")
        request("/api/harvest/simulate-answer", {"question_id": q["id"]}, name=q["id"])
        request(f"/api/route/{DAY}/{d['courier']}", name=f"after-{q['id']}")
    request("/api/time/example")
    # Sahne 6–7
    request("/api/learning")
    record["GET /api/summary"] = trim_summary(request("/api/summary", keep=False))
    request("/api/economics")
    request("/api/economics?scenario=optimize")
    reset()


if __name__ == "__main__":
    demo = selections()
    stream(demo)
    record["demo"] = demo
    record["_note"] = "tools/record_fallback.py ile üretildi (mock mod). Uygulama verisi · 1 aylık geçmiş."
    OUT.write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    print("yazıldı", OUT, f"{OUT.stat().st_size / 1024:.0f} KB", len(record), "key")

"""Orkestratör izinin yedeğini kaydeder: API'ye ulaşılamazsa Sahne 2 bunu "KAYIT" etiketiyle oynatır.

  CM_LLM_MODE=mock uvicorn api.main:app --port 8767   (ayrı pencerede)
  python ui/story/tools/record_trace.py [http://127.0.0.1:8767]
Büyük ve arayüzün kullanmadığı alanlar (rota kısıt listeleri) kırpılır.
"""
import json
import sys
import urllib.request
from pathlib import Path

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8767"
OUT = Path(__file__).resolve().parents[1] / "data" / "trace_fallback.json"

req = urllib.request.Request(API + "/api/orchestrator/plan", data=json.dumps({"day": 32}).encode(),
                             headers={"Content-Type": "application/json"})
d = json.loads(urllib.request.urlopen(req, timeout=120).read())
for e in d["events"]:
    v = e.get("data")
    if isinstance(v, dict):
        for k in ("constraints", "changes", "order", "expected_arrival", "comparison"):
            v.pop(k, None)
        if "findings" in v:
            v["findings"] = v["findings"][:12]
d["record"] = True
OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
print("yazıldı", OUT, len(d["events"]), "event")

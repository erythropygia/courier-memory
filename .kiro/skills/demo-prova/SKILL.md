---
name: demo-prova
description: Sunum öncesi demo provası yapar: testler, yerel API, demo sıfırlama, "nasıl çalışır" akışının sekiz adımı ve hikaye arayüzü. "Demoyu prova et", "demo çalışıyor mu", "sunum öncesi kontrol" istendiğinde kullan.
---

# Demo provası

Çalışma klasörü: reponun kökü (`courier-memory`).

1. Ortam ve testler:
   ```bash
   uv venv && source .venv/bin/activate && uv pip install -e ".[dev,agentcore]"
   PYTHONUTF8=1 CM_LLM_MODE=mock pytest -q
   ```
   Kırmızı test varsa dur, nedenini söyle.
2. API (8080 ve 8081 dolu; 8000 kullan):
   ```bash
   CM_LLM_MODE=mock PYTHONUTF8=1 uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```
   Canlı model için: `CM_LLM_MODE=live CM_BEDROCK_CLIENT=invoke CM_MODEL_ID=global.anthropic.<güncel-sonnet>`; önce `python -m agents.check`.
3. Sıfırla ve sekiz adımı API'den geç:
   ```bash
   B=http://localhost:8000
   curl -s -XPOST $B/api/demo/reset -H 'content-type: application/json' -d '{"day":32}'
   curl -s -XPOST $B/api/orchestrator/plan -H 'content-type: application/json' -d '{"day":32}' | jq '.status, .proposal.rationale[0]'
   curl -s $B/api/briefing/32/O02 | jq -r .morning_briefing
   curl -s -XPOST $B/api/review/run -H 'content-type: application/json' -d '{"day":32}' | jq -r .report.summary
   curl -s -XPOST $B/api/region/run -H 'content-type: application/json' -d '{"day":32}' | jq -r '.manager_summary[]'
   ```
4. Tarayıcıda:
   ```bash
   python3 -m webbrowser http://localhost:8000/flow/      # nasıl çalışır: "Hepsini oynat", sekiz adım ✓ olmalı
   python3 -m webbrowser http://localhost:8000/           # hikaye, 8 sahne
   ```
5. Sunumdan hemen önce akış sayfasında "Baştan".

Rapor: test sayısı, her adımın durumu, mod (mock / live), varsa `degraded: true` dönen ajanlar.

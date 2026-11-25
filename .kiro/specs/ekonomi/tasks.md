# Uygulama planı: Ekonomi

- [x] 1. `llm.py`: kullanım günlüğü (`data/usage.jsonl`), `cache_creation` alanı, `CM_AUTO_CACHE`
- [x] 2. `agents/cost.py`: temsili çağrı dizileri, `_measure`, ölçüm birleştirme → `token_usage.json`
- [x] 3. `agents/economics.yaml` + `agents/economics.py` (`compute`, `load_assumptions`) → `economics.json`
- [x] 4. `GET /api/economics` + testler
- [x] 5. Arayüz "Değer" sekmesi
- [x] 6. Operasyon maliyeti (kollar, şelale, manşet, ölçek) ve LLM senaryoları; ajan başına model (`Services.create`)
- [x] 7. `cost.py` günlük çağrılara `orchestrator`, `ask_orchestrator`, `harvest`, `harvest_answer` (hafıza profili); `economics.yaml` `agent_model` ve senaryolara `orchestrator`, `harvest`; `presentation_figures.py` yeniden üretildi

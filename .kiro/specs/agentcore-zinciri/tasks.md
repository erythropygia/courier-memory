# Uygulama planı: AgentCore zinciri

- [x] 1. `api/live.py`: koşu türü (`kind`) ve `runner()`; `hello`/`snapshot` `kind` taşır
  - _Gereksinimler: 1.2, 1.3_
- [x] 2. `api/agentcore_client.py`: ARN'yi adla bulma, InvokeAgentRuntime akışı, yeniden denemesiz, gösterilebilir hatalar
  - _Gereksinimler: 1.4, 3.1–3.3_
- [x] 3. `api/agentcore_chain.py`: altı adım, `cm_trace` eşlemesi, yedek iz, sonuç kartı verisi
  - _Gereksinimler: 1.1, 2.1, 2.3_
- [x] 4. `POST /api/live/start?chain=agentcore`, `CM_AGENTCORE_CHAIN=0` → 501
  - _Gereksinimler: 1.2, 4.1_
- [x] 5. `ui/flow/index.html`: "AgentCore zinciri" düğmesi, ajan rozetleri, girinti, ret biçimi, şerit
  - _Gereksinimler: 2.2, 4.1_
- [x] 6. `deploy/web/ecs_deploy.py`: görev rolüne `agentcore-supervisor` politikası, ortam
  - _Gereksinimler: 4.2_
- [x] 7. Kabul testi `api/tests/test_agentcore_chain.py`
  - _Gereksinimler: 1.1–1.4, 2.1, 2.3, 3.1–3.3, 4.1, 4.2_
- [ ] 8. Dağıtımda dene: runtime `cm_trace` yazınca ECS'ye dağıt, sunum ekranında altı adımı uçtan uca koştur
  - _Gereksinimler: 1.1, 2.1, 2.2_

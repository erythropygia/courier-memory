# Uygulama planı: Amazon Quick köprüsü

1–4 repoda yapıldı ve AWS'ye gitmeden sınandı. 5–7 dağıtım hesabında, `agentcore-runtime` görev 12'den sonra yapılır.

- [x] 1. `deploy/quick/bridge_lambda.py`: araç adı ve soru denetimi, sabit kimlik (`QUICK_ACTOR_ID`), yeni oturum, `parse_stream`, yeniden denemesiz güvenli hata
  - _Gereksinimler: 1.3, 3.1, 3.2, 4.1–4.7_
- [x] 2. `deploy/quick/quick_bridge_setup.py`: iki IAM rolü (en az yetki), Lambda, Cognito (client credentials), Gateway (`CUSTOM_JWT`) ve hedef; tekrar çalıştırmak güvenli; değerler yalnız `~/.courier-memory/quick-bridge.json`'a; `--test`
  - _Gereksinimler: 1.1, 1.2, 2.1–2.3, 5.1–5.3, 6.1–6.5_
- [x] 3. `deploy/quick/README.md`: kurulum, Quick tarafı, kimlik, sınırlar
  - _Gereksinimler: 3.3, 7.1–7.3_
- [x] 4. Testler: `deploy/quick/tests/test_bridge_lambda.py` (4 test); `pyproject.toml` → `testpaths`
  - _Gereksinimler: 3.1, 4.1, 4.2, 4.4–4.6_
- [x] 5. Kurulum hesapta: `AWS_PROFILE=… AWS_REGION=us-east-1 python deploy/quick/quick_bridge_setup.py --test`; `tools/list` `ask_courier_memory`'yi gösterir, `tools/call` Supervisor'ın cevabını döndürür
  - _Gereksinimler: 1.1, 1.3, 6.1–6.5_
- [ ] 6. Quick tarafı: MCP connector (servisler arası OAuth) ve chat ajanı; "Bugünün planını gerekçesiyle özetle" ve bir geçmiş veri sorusu cevaplanır
  - _Gereksinimler: 1.2, 7.1, 7.2_
- [ ] 7. İz kontrolü: `agentcore traces runtime list` Quick'ten gelen isteği `cm.actor_id = MUDUR-QUICK` ile gösterir; jetonsuz MCP çağrısı Gateway'de reddedilir
  - _Gereksinimler: 2.1, 3.1_

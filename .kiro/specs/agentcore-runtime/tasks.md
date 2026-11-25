# Uygulama planı: AgentCore Runtime'da Courier Memory ajanı

1–8b repoda yapıldı ve Bedrock'a gitmeden sınandı. 9–14 dağıtım hesabında yapılır.

- [x] 1. Yük ayrıştırma ve alan servislerinin tembel kurulumu (`cm/payload.py`, `cm/backend.py`, `role_of`)
  - _Gereksinimler: 4.2, 4.4, 5.1_
- [x] 2. Dokuz Strands `@tool` ve erişim sınıfları (`cm/tools.py`)
  - _Gereksinimler: 3.1, 3.2, 3.3, 3.4_
- [x] 3. Kimlik sınırı: `decide()` ve `CourierScope` kancası (`cm/scope.py`)
  - _Gereksinimler: 5.1–5.6_
- [x] 4. Sistem istemi, kimliğe göre "bu istek" bölümü (`cm/prompt.py`)
  - _Gereksinimler: 5.5_
- [x] 5. AgentCore Memory oturum yöneticisi ve model yükleyici (`cm/memory.py`, `cm/model.py`)
  - _Gereksinimler: 6.1–6.4, 7.1–7.3_
- [x] 6. Giriş noktası (`main.py`): çalışma zamanı içe aktarımı, `_get_agent`, akış, hata olayı, iz öznitelikleri
  - _Gereksinimler: 2.3, 4.1–4.6_
- [x] 7. Testler: betikli sahte modelle uçtan uca (`deploy/agentcore/tests/test_runtime.py`)
  - _Gereksinimler: 8.4_
- [x] 8. `bootstrap.sh` ve `verify.sh`; sahte iskele üzerinde denendi (kopya kendi başına çalışıyor, tekrar çalıştırma güvenli)
  - _Gereksinimler: 1.4, 2.1, 8.1–8.3_
- [x] 8a. Çekirdek araç takımı (`cm/core.py`) ve arka uç seçimi (`cm/backend.py`: `CM_TOOLSET`, `auto` düşüşü); testler iki takım için parametreli (21 test)
  - _Gereksinimler: 11.1–11.7_
- [x] 8b. Projenin MCP sunucusu (`deploy/mcp/cm_mcp_server.py`), ve çalışma alanı ayarı (`.kiro/settings/mcp.json`)
  - _Gereksinimler: 12.1–12.3_
- [ ] 9. İskele ve yerleştirme: `deploy/agentcore/bootstrap.sh` (içinde `agentcore create --name CourierMemory --template agent-python-strands`); `.cm/main.template.py` ile `main.py` karşılaştırılır, şablonun hafıza ya da yük kablolaması farklıysa uyarlanır; `verify.sh` yeşil
  - _Gereksinimler: 1.1, 8.1_
- [ ] 10. Model kimliği: güncel Claude Sonnet kimliğini keşfet, `app/agent/model/load.py` içinde çıkarım profili önekiyle doğrula
  - _Gereksinimler: 7.1_
- [ ] 11. Yerel deneme: `agentcore dev --port 8081` + `agentcore invoke --runtime agent --local --port 8081` (kurye, müdür, konuk)
  - _Gereksinimler: 3.5, 5.1–5.4_
- [ ] 12. Dağıtım: `agentcore deploy`; `agentcore status` çalışma ortamını ve `agentMemory`'yi dağıtılmış gösterir
  - _Gereksinimler: 1.2, 6.1_
- [ ] 13. Dağıtımın üç kontrolü: `deploy/agentcore/verify.sh CourierMemory --deployed` (durum · araç çağrısı · log grubu ve izler)
  - _Gereksinimler: 1.2, 2.1, 2.2, 3.5_
- [ ] 14. Kimlik ve hafıza sınaması dağıtılmış ajanda: O02 kendi brifingi · O02'nin K07 isteği reddedilir, oturum sürer · iki oturumlu hatırlama (`agentcore memory record list`)
  - _Gereksinimler: 5.1–5.4, 6.2, 6.4_
- [ ] 15. (Sonraki adım) Kalıcı adres hafızası: DynamoDB + Lambda, MCP Gateway hedefi; araçlar Gateway üzerinden, kimlik sınırı korunur
  - _Gereksinimler: 9.1–9.3_
- [ ] 16. (Sonraki adım) Sohbet arayüzü: Amazon ECS Fargate üzerinde; kimlik seçici
  - _Gereksinimler: 10.1, 10.2_

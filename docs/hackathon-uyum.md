# Atölye şartlarına uyum

Kaynak: "Ship Production Agents on Amazon Bedrock AgentCore with Kiro" atölyesi (hackathon biçimi: Lab 7, kendi kullanım alanın). Bu belge her şartın bizde nerede karşılandığını ve **durumunu** söyler.

Durum etiketleri: **Hazır** = repoda, yerelde sınandı · **Etkinlikte** = AWS hesabı ve AgentCore CLI gerekir, komutu hazır · **Esnetme** = şart değil, spec'i yazıldı, yapılmadı.

## Lab 7'nin değişmez şartları

| Şart | Bizde | Durum | Kanıt / komut |
|---|---|---|---|
| **Deploy:** `agentcore create` ile kurulmuş, adı `CustomerServiceAgent` olmayan proje, `agentcore deploy` ile AgentCore Runtime'da | Proje `CourierMemory`, şablon `agent-python-strands` | **Etkinlikte** | `deploy/agentcore/bootstrap.sh` → `agentcore deploy` → `agentcore status` |
| **Observability:** çalışma ortamının `envVars` listesinde `UNIFIED_TRACES_DESTINATION_ENABLED = true` | `bootstrap.sh` yazar, `verify.sh` denetler | **Hazır** (dosya); iz **Etkinlikte** | `agentcore traces runtime list --since 15m` |
| **Tool:** en az bir araç (Gateway hedefi, MCP sunucusu ya da yerel `@tool`) | 9 Strands `@tool` | **Hazır** | `deploy/agentcore/runtime/cm/tools.py`; test `test_tools_return_domain_data` |
| **Kayıt:** nasıl yapıldığını anlatan spec klasörü | `.kiro/specs/agentcore-runtime/` (+ 10 spec daha) | **Hazır** | `deploy/kiro_sync.sh` çalışma alanına taşır |

Üç kontrolün tek komutu: `deploy/agentcore/verify.sh CourierMemory --deployed`.

## Dağıtım yönergesinin kuralları

| Kural | Bizde | Durum |
|---|---|---|
| Klasör yapısı elle kurulmaz, `agentcore create` | `bootstrap.sh` iskeleyi CLI'ya kurdurur, sonra dosya yerleştirir | Etkinlikte |
| `from bedrock_agentcore.runtime import BedrockAgentCoreApp` | `runtime/main.py`; test `test_entrypoint_contract` | Hazır |
| Tembel kurulum (30 sn sınırı) | `_get_agent`; modül içe aktarımı ~0,2 sn ölçüldü | Hazır |
| `@app.entrypoint` ile akış döndüren asenkron işleyici, `app.run()` `__main__` altında | `runtime/main.py` | Hazır |
| Gövdeden `prompt` ve `actorId` | `cm/payload.py`; test `test_parse_request` | Hazır |
| Model kimliği çıkarım profili biçiminde, önce keşfet | `cm/model.py` şablonun `model/load.py` dosyasını kullanır, öneksiz kimliği reddeder; keşif skill'in 3. adımı | Hazır (kod); keşif Etkinlikte |
| `pyproject.toml`: yalnız çalışma zamanı bağımlılıkları | numpy, scipy, pydantic, pyyaml eklenir; `pytest` girmez (`verify.sh` denetler) | Hazır |
| ARM64 | Eklenen dört paketin ARM64 Linux tekerleği var | Hazır (derleme Etkinlikte) |
| Rol izni elle verilmez (`additionalPolicies`) | Araçlar AWS API'si çağırmıyor; gerek yok | Hazır |
| Yerel sunucu 8081, 8080'e dokunulmaz | Skill ve README 8081 kullanır; yerel API 8000 | Hazır |

## Rehberli laboratuvarların yetenekleri (Lab 7 için esnetme)

| Lab | Yetenek | Bizde | Durum |
|---|---|---|---|
| 1 | Strands ajanı + araç | Strands ajanı, 9 araç; bilgi kaynağı Knowledge Base değil şubenin hafızası ve teslim kayıtları | Hazır |
| 2 | AgentCore Memory (kısa ve uzun süreli) | `cm/memory.py`: şablonun `agentMemory` hafızası, `/users/{actorId}/facts` en çok 5 kayıt | Hazır (kod); iki oturumlu sınama Etkinlikte |
| 3 | AgentCore Gateway, MCP araçları | Spec'te gereksinim 9: kalıcı adres hafızası (DynamoDB + Lambda) Gateway hedefi | Esnetme |
| 4 | Kimlik: veri erişimi isteğin kimliğine bağlı | `cm/scope.py` `BeforeToolCallEvent` kancası: kurye ↔ kurye, kurye ↔ müdür, konuk. Atölyedeki müşteri yalıtımının kurye karşılığı | Hazır; testler iki araç takımında |
| 5 | Observability: izler ve loglar | `envVars` + iz öznitelikleri `cm.actor_role`, `cm.actor_id` | Hazır (ayar); iz okuma Etkinlikte |
| 6 | Sohbet arayüzü, ECS Fargate | Atölyenin hazır `build-chat-ui`, `deploy-chat-ui-to-ecs` skill'leriyle; spec'te gereksinim 10 | Esnetme |

Ek olarak yerelde iki arayüz var (AgentCore değil, yerel API): hikaye (`/story/`) ve nasıl çalışır (`/flow/`). İkisi de Kiro IDE Browser'ın `/proxy/<port>/` adresi altında çalışır.

## Kiro'nun çalışma biçimi

| Atölyenin beklediği | Bizde | Durum |
|---|---|---|
| Spec: niyet → gereksinim (sınanabilir kabul kriteri) → tasarım → görev; onaydan sonra kod | 11 spec. Altısı Kiro ile fazlar boyunca yazıldı; beşi (`durak-kartlari`, `oz-degerlendirme-bolge`, `gercek-gun`, `akis-arayuzu`, `agentcore-runtime`) EARS kalıbında | Hazır |
| Her şart bir kabul kriteri | `agentcore-runtime/requirements.md` gereksinim 1–3 üç şartı taşır | Hazır |
| Görev listesi şartları kapsar (kur, gözlemle, araç, dağıt) | `agentcore-runtime/tasks.md` görev 2, 8, 9, 12, 13 | Hazır |
| Steering: her oturumda okunan kurallar | 7 dosya, `inclusion: always`. Atölyenin iki dosyası (`agentcore-deployment.md`, `strands-agent-coding.md`) Getting Started'da ayrıca yazılır; bizimkiler onlarla çelişmez, proje kararlarını ekler | Hazır |
| Skill: istenince çalışan yönerge | 4 skill | Hazır |
| Hook: kaydetmede otomasyon | 5 hook | Hazır; Kiro'da yüklenişi Etkinlikte doğrulanacak |
| MCP sunucuları | Atölyeninkiler (kullanıcı ayarı) + projenin kendi sunucusu (çalışma alanı ayarı) | Hazır; stdio el sıkışması yerelde sınandı |


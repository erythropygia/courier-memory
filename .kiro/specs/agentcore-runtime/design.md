# Tasarım: AgentCore Runtime'da Courier Memory ajanı

## Genel bakış

```
kurye / müdür                                       agentcore invoke · Amazon Quick köprüsü (quick-koprusu)
   │  {"prompt", "actorId", "day"?}
   ▼
Amazon Bedrock AgentCore Runtime  (proje CourierMemory, ARM64; beş runtime, tek kod paketi)
   agent  (CM_AGENT_ROLE=supervisor)
   main.py  BedrockAgentCoreApp · @app.entrypoint (akış) · _get_agent (tembel)
      ├─ Strands Agent ── Amazon Bedrock (Claude, çıkarım profili kimliği)
      │     ├─ kanca: cm/scope.py  BeforeToolCallEvent → kimlik sınırı (erken ret)
      │     ├─ oturum: cm/memory.py → AgentCore Memory "agentMemory"
      │     └─ araçlar: ask_planner · ask_courier_agent · ask_memory_keeper · ask_analyst  (cm/roles.py; kimlik kapanışta)
      │            └─ cm/delegate.py → InvokeAgentRuntime {"prompt", "actorId", "day"?}, oturum <oturum>-<rol>
      ▼
   planner        plan_day · morning_review · region_report              ┐ her biri: aynı main.py, kendi istemi,
   courier        courier_briefing · stop_cards · approaching_stop       │ aynı kimlik kancası, aynı agentMemory
   memory_keeper  leave_note · branch_memory_summary ·                   │
                  real_day_evidence · harvest_questions                  │
   analyst        query_history → Amazon Athena (athena-analiz)          ┘
      │
      └─ alan araçları → agents.Services (Orkestratör, Atama, Brifing, Hafıza, Değerlendirme, Bölge, Hasat; kurallı yol)
                             └─ cm_sim.routing_memory · data/demo_run · data/real_day
   OpenTelemetry → CloudWatch  (her runtime'da UNIFIED_TRACES_DESTINATION_ENABLED=true)
```

`CM_MULTI_AGENT=0` ile yapı tek runtime'a döner: `agent` on alan aracının hepsini taşır (Athena yok), yönlendirme yoktur.

İlke değişmez (`tech.md`): **LLM karar verir, hesap araçta.** Strands ajanları hangi aracı (ya da uzmanı) çağıracağına ve nasıl anlatacağına karar verir; rota, atama, kart seçimi, öz-değerlendirme deterministik Python'dur ve yerel API ile aynı fonksiyonlardır. Bu yüzden dağıtılmış ajanın söylediği sayı, simülasyonda ölçülen sayıyla aynıdır.

## Neden Strands sarmalayıcı, neden alan ajanlarını doğrudan taşımıyoruz

- Alan ajanlarının kendi döngüsü (`agents/llm.py`) Bedrock Mantle istemcisini ve bu modele özgü istek kurallarını kullanır. AgentCore çalışma ortamının rolü `bedrock:InvokeModel*` verir ve çıkarım profili kimliği ister.
- Strands şablonu hafızayı, yük ayrıştırmayı ve izlemeyi hazır getirir.
- Alan ajanlarının her biri zaten "aynı araçlarla kurallı yedek" taşır. Çalışma ortamında bu yol kullanılır (`CM_LLM_MODE=mock`); Strands ajanları üst katmanda karar verir. Böylece modele yalnız runtime ajanları gider, maliyet öngörülebilir kalır.
- Yerel API alan ajanlarıyla birlikte demo arayüzleri (`/story/`, `/flow/`) için çalışmaya devam eder; `CM_BEDROCK_CLIENT=invoke` ile o da çıkarım profili kimliğiyle Bedrock'a gidebilir.

## Neden çok ajan

- **Kısa istem, doğru araç:** her uzman üç-dört araç görür; tek ajanda on araç ve Athena şeması aynı istemdeydi.
- **Ayrı iz ve ayrı izin:** her uzmanın izi `cm.agent_role` ile ayrılır; AWS izni yalnız gereken runtime'a verilir (Athena yalnız `analyst`'te).
- **Tek kod paketi:** beş runtime aynı `app/agent` klasöründen dağıtılır, yalnız `CM_AGENT_ROLE` farklıdır; bakım tek yerdedir.
- **Bedeli:** Supervisor üzerinden her istek en az iki model çağrısıdır (Supervisor + uzman); yanıt biraz daha geç gelir. Uzmanlar doğrudan da çağrılabilir (`agentcore invoke --runtime planner`).

## Dosyalar

| Repoda | Projede (`$CM_WORKSPACE/CourierMemory/`, varsayılan `../CourierMemory/`) | Ne |
|---|---|---|
| `deploy/agentcore/runtime/main.py` | `app/agent/main.py` | Giriş noktası (şablonunki `.cm/main.template.py` olarak saklanır); ajan kimlik + oturum başına kurulur |
| `deploy/agentcore/runtime/cm/payload.py` | `app/agent/cm/` | `parse_request`: `prompt`, `actorId`, `day` |
| `…/cm/backend.py` | 〃 | İki arka uç, tembel kurulum: `FullBackend` (`agents.Services`) ve `CoreBackend`; `CM_TOOLSET` = `auto` \| `full` \| `core`; `role_of(actorId)` → courier / manager / guest |
| `…/cm/core.py` | 〃 | Çekirdek takım: `CoreStore` (veri dosyaları, standart kütüphane), sınıflandırıcı, hassas veri ayıklama, kart, yaklaşma |
| `…/cm/tools.py` | 〃 | On alan aracı (ince sarmalayıcı; hesabı arka uç yapar); `COURIER_TOOLS`, `MANAGER_TOOLS`, `PUBLIC_TOOLS` |
| `…/cm/roles.py` | 〃 | `CM_AGENT_ROLE` → `agent_role()`; `SPECIALIST_TOOLS`; `tools_for(rol, actorId, oturum)`; Supervisor'ın dört `ask_*` aracı |
| `…/cm/delegate.py` | 〃 | Uzman çağrısı: `resolve_arn`, `specialist_session`, `parse_stream`, `invoke_specialist`; `DelegationError` |
| `…/cm/athena.py` | 〃 | `query_history` ve SQL denetimi (`athena-analiz`) |
| `…/cm/scope.py` | 〃 | `decide()` (saf) + `CourierScope` kancası; Supervisor araçları için erken ret |
| `…/cm/prompt.py` | 〃 | Ortak ilkeler + rol bölümü (`AGENT_SECTIONS`) + kimliğe göre "bu istek" bölümü |
| `…/cm/memory.py` | 〃 | `AgentCoreMemorySessionManager` (varsa `MEMORY_AGENTMEMORY_ID`) |
| `…/cm/model.py` | 〃 | Şablonun `model/load.py` yükleyicisi → yoksa `CM_AGENT_MODEL_ID` |
| `deploy/agentcore/agentcore_config.py` | `agentcore/agentcore.json`, `supervisor-policy.json`, `analyst-policy.json` | Çok ajanlı yapılandırma dönüşümü (saf fonksiyon); `bootstrap.sh` çağırır |
| `agents/`, `sim/cm_sim/`, `sim/config/` | `app/agent/agents/`, `cm_sim/`, `config/` | Alan kodu (kopya) |
| `data/demo_run`, `data/real_day`, `data/map` | `app/agent/data/…` | Veri (kopya, ~28 MB) |
| `deploy/agentcore/bootstrap.sh`, `verify.sh` | — | Kurulum ve kontrol |

Kopyalar tek yönlüdür: düzenleme repoda yapılır, `bootstrap.sh` projeye yazar.

## Çok ajanlı yapılandırma (`agentcore_config.py`)

| Runtime | `CM_AGENT_ROLE` | Araçlar | Ek `envVars` | Ek politika |
|---|---|---|---|---|
| `agent` | `supervisor` | `ask_planner`, `ask_courier_agent`, `ask_memory_keeper`, `ask_analyst` | `CM_RUNTIME_PREFIX=<Proje>_<hedef>_` | `supervisor-policy.json` |
| `planner` | `planner` | `plan_day`, `morning_review`, `region_report` | — | — |
| `courier` | `courier` | `courier_briefing`, `stop_cards`, `approaching_stop` | — | — |
| `memory_keeper` | `memory_keeper` | `leave_note`, `branch_memory_summary`, `real_day_evidence`, `harvest_questions` | — | — |
| `analyst` | `analyst` | `query_history` | `CM_ATHENA_DATABASE=courier_memory`, `CM_ATHENA_WORKGROUP=courier-memory` | `analyst-policy.json` |

- Uzmanlar şablonun `agent` runtime'ından kopyalanır (kod yeri, derleme, ağ ayarları aynı); adı ve rolü değişir. Kullanıcının `agent`'a eklediği `envVars` (ör. `CM_AGENT_MODEL_ID`) ve politikalar uzmanlara da geçer.
- Yönetilen anahtarlar (`CM_AGENT_ROLE`, `CM_RUNTIME_PREFIX`, `CM_ATHENA_*`, `UNIFIED_TRACES_DESTINATION_ENABLED`) her çalıştırmada yeniden yazılır; yinelenmez. Şablonda olmayan başka runtime'lar dokunulmadan kalır.
- CDK runtime adı `<Proje>_<hedef>_<runtime>` biçimindedir (ör. `CourierMemory_default_planner`). Önek hedefi de içerir: başka bir hedefin uzmanı seçilmez.
- `CM_MULTI_AGENT=0`: yalnız `agent` kalır, rolü `all` (on araç); politika dosyaları silinir.

## Uzman çağrısı

```
ask_planner(question, day?)              model yalnız bunları görür
  └─ kapanış: actor_id, session_id       istekten; model değiştiremez
       └─ delegate.invoke_specialist("planner", question, actor_id, session_id, day)
            ├─ _arn: CM_PLANNER_RUNTIME_ARN ya da ListAgentRuntimes → "<önek>planner" (tek eşleşme), önbellek
            ├─ InvokeAgentRuntime  oturum "<oturum>-planner" (≥ 33 karakter), okuma 120 sn, yeniden deneme yok
            └─ parse_stream: "data: {...}" satırları → metin; messageStart yeni mesaj; "error" → DelegationError
```

- Uzman cevabı Supervisor'a araç sonucu olarak döner; Supervisor birden fazla uzmanı aynı istekte çağırabilir ve cevapları birleştirir.
- AWS hatası (`ClientError`, `BotoCoreError`) log'a ayrıntısıyla, modele kısa bir metinle gider ("planner uzmanına şu an ulaşılamıyor (<kod>)"); o rolün ARN'si önbellekten silinir (runtime yeniden kurulduysa sonraki çağrı yeniden bulur).
- Akış her durumda kapatılır (`finally: body.close()`).

## İki araç takımı

| | Tam | Çekirdek |
|---|---|---|
| Kaynak | `agents.Services` (alan ajanları, hafızalı rota, gerçek gün kapsamı) | `cm/core.py`: `meta.json`, `couriers.json`, `addresses.json`, `memory/<gün>.json`, `snapshots/D/<gün>.json` |
| Bağımlılık | numpy, scipy, pydantic, pyyaml | yalnız standart kütüphane |
| Araç | 10 | 6 (müdür araçları, `harvest_questions` dahil, açıklayıcı hata döndürür) |
| Rota sırası | hafızalı sıra (brifingle aynı) | simülasyon planının sırası |
| Not | Hafıza Ajanı (kurallı yol) + `MemoryBook` | aynı kuralların küçük kopyası; oturum dosyasına yazar |

Çok ajanlı yapıda araç takımı her uzmanın kendi sürecinde ayrı seçilir; izde `cm.toolset` görünür.

## Erişim modeli

| Araç sınıfı | Araçlar | kurye | müdür | konuk |
|---|---|---|---|---|
| `COURIER_TOOLS` | `courier_briefing`, `stop_cards`, `approaching_stop`, `leave_note` | yalnız kendi `courier_id` | herkes için | yok |
| `MANAGER_TOOLS` | `plan_day`, `morning_review`, `region_report`, `harvest_questions` | yok | var | yok |
| `PUBLIC_TOOLS` | `branch_memory_summary`, `real_day_evidence` | var | var | var |
| Analiz | `query_history` | yok | var | yok |
| Supervisor, müdür | `ask_planner`, `ask_analyst` | yok (erken ret) | var | yok (erken ret) |
| Supervisor, kimlikli | `ask_courier_agent` | var (uzman kendi kimliğini denetler) | var | yok (erken ret) |
| Supervisor, açık | `ask_memory_keeper` | var | var | var (uzman araç sınırını uygular) |

`role_of`: `actorId` şubenin kuryelerindense kurye; `MUDUR` / `MGR` / `MANAGER` ile başlıyorsa müdür; değilse konuk. Üretimde kimlik, çalışma ortamındaki JWT doğrulayıcının (AgentCore Identity) onayladığı bir talepten gelir; burada istek gövdesinden okunur ki CLI ile sınanabilsin. Amazon Quick köprüsü kimliği Lambda ortamından sabit verir (`MUDUR-QUICK`).

Kanca `event.cancel_tool = "<ret metni>"` yazar; Strands bunu hata durumlu araç sonucu olarak modele verir. Ret metni kimin neyi göremeyeceğini söyler, veri içermez. Supervisor'daki erken ret yalnız boşa runtime ve model çağrısını önler; asıl sınır her uzmanın kendi kancasıdır.

## İzinler

| Runtime | Ek izin | Kaynak |
|---|---|---|
| `agent` (Supervisor) | `bedrock-agentcore:InvokeAgentRuntime` | `arn:aws:bedrock-agentcore:*:*:runtime/<Proje>_<hedef>_*` |
| | `bedrock-agentcore:ListAgentRuntimes` | `*` (kaynak düzeyinde kısıtlanamaz) |
| `analyst` | Athena sorgu, Glue katalog okuma, S3 veri okuma, sonuç klasörüne yazma | ayrıntı `athena-analiz` tasarımı |
| `planner`, `courier`, `memory_keeper` | yok | — |

Politikalar `agentcore/` klasörüne yazılır ve `additionalPolicies` içinde `../../agentcore/<dosya>` olarak anılır (CDK yolu `codeLocation`'a göre çözer). Modeli çağırma izni şablonun rolündedir.

## Hafıza: iki ayrı şey

| | Adres hafızası (`MemoryBook`) | Konuşma hafızası (AgentCore Memory) |
|---|---|---|
| Ne tutar | Adresin püf noktası ve bilgi kartı; kişiyi değil adresi anlatır | Kimin ne sorduğu, ne söylediği |
| Kapsam | Şube (bütün kuryeler okur) | `actorId` başına; çok ajanlı yapıda her uzmanın oturumu ayrı (`<oturum>-<rol>`) |
| Çalışma ortamında | Oturumun geçici dosyası (demo tohumu + oturumdaki notlar); her runtime'ın kendi kopyası, not `memory_keeper`'da yazılır | Yönetilen, oturumlar arası kalıcı; her runtime'a bağlı |
| Kalıcılık planı | Gereksinim 9 (DynamoDB + Gateway); web uygulamasının DynamoDB deposu ayrıca `aws-dagitim` spec'inde | hazır |

## Model

- Kimlik çıkarım profili biçimindedir; öneksiz kimlik `check_model_id` ile reddedilir.
- Öncelik: şablonun `model/load.py` → `CM_AGENT_MODEL_ID` → `cm/model.py` içindeki yedek varsayılan (`global.anthropic.claude-sonnet-4-6`).
- Test ve demo için hesapta izinli profil `global.anthropic.claude-sonnet-5`'tir (`.env.example` → `CM_AGENT_MODEL_ID`). `agent`'a verilen değer uzmanlara geçer. Opus kullanılmaz.
- Şablonun `model/load.py` dosyası hesabın izin listesinde olmayan bir modeli yazabilir; `bootstrap.sh` `CM_AGENT_MODEL_ID` verildiğinde oradaki `model_id`'yi bu değerle değiştirir (biçim denetimiyle). CI aynı değeri her dağıtımda verir (`aws-dagitim`).

## Hata yönetimi

- Araç içi hata (bilinmeyen kurye, geçersiz gün) Strands tarafından hata sonucu olarak modele döner; ajan kullanıcıya açıklar.
- Uzman hatası (`DelegationError`) Supervisor'a araç sonucu olarak döner; Supervisor kullanıcıya hangi uzmana ulaşılamadığını söyler, konuşma sürer.
- Ajan düzeyi hata (model erişimi, kimlik bilgisi) akışa `{"error": "<tür>: <mesaj>"}` olarak yazılır; `agentcore invoke` çıktısında ve köprüde görünür.
- Model erişimi hatası (`AccessDeniedException … Marketplace`) kod sorunu değildir: hesapta Anthropic model erişimi bir kez açılır.

## Test stratejisi

- `deploy/agentcore/tests/test_runtime.py` (21 test; araç ve kimlik senaryoları iki takım için ayrı ayrı koşar, alan kodu yoksa tam takımınkiler atlanır): sözleşme (içe aktarma yolu, tembel kurulum), yük ayrıştırma, araçların alan verisi döndürmesi, `decide()` tablosu, uçtan uca üç kimlik senaryosu (kurye kendi aracı · başka kurye reddi ve oturumun sürmesi · konuk), not akışında şifre ayıklama, hatanın akışa yazılması, model kimliği biçimi. Model betikli sahte bir `strands.models.Model`'dir; Bedrock'a gidilmez.
- `deploy/agentcore/tests/test_multi_agent.py` (17 test): uzmanların araçları çakışmasız böldüğü, `CM_AGENT_ROLE` ayrıştırması, rol başına istem, akış ayrıştırma ve mesaj ayrımı, ARN'nin önek + hedefle seçilmesi, önek yokken ve belirsizlikte ret, uzmana kimliğin gitmesi ve akışın kapanması, AWS ayrıntısının gizlenmesi ve ARN'nin unutulması, oturum uzunluğu; sahte uzmanla uçtan uca: Supervisor kimlikle yönlendirir · model kimlik taklit edemez · kuryenin müdür uzmanı isteği uzman çağrılmadan reddedilir · uzman hatası raporlanır · uzman runtime'ı kimlik sınırını korur.
- `deploy/agentcore/tests/test_agentcore_config.py` (6 test): beş runtime aynı kodla, politika bu proje ve hedefe dar, analiste Athena ortamı ve salt okunur politika, tekrar çalıştırma aynı sonuç, tek runtime'a dönüş, kullanıcı `envVars` ve politikalarının korunması.
- `deploy/agentcore/tests/test_athena.py` (24 test): SQL denetimi ve `query_history` (`athena-analiz`), analist runtime'ının tek araç ve şemalı istemle kurulması, `harvest_questions`'ın iki takımdaki davranışı ve kimlik sınırı.
- `verify.sh`: dağıtımdan önce dosya ve yapılandırma denetimi; dağıtımdan sonra dağıtımın üç kontrolü.
- Çalışma ortamı kopyasının kendi başına çalıştığı, sahte bir iskele üzerinde `bootstrap.sh` + yalıtık içe aktarma ile denendi (`main` içe aktarımı ~0,2 sn; plan aracı ~0,5 sn).

## Açık riskler

- Şablonun `main.py`, `parse.py`, `memory/session.py` içeriği `agentcore create` çalışmadan bilinmez. Giriş noktamız şablonun yerine geçer ve yalnız `model/load.py`'ye yumuşak bağlıdır; şablon farklı bir hafıza kablolaması getirdiyse `.cm/main.template.py` ile karşılaştırılır (görev 9).
- CDK'nın runtime adlandırması (`<Proje>_<hedef>_<runtime>`) ve `agentMemory`'nin her runtime'a bağlanması ilk dağıtımda doğrulanır; ad farklıysa `CM_<ROL>_RUNTIME_ARN` ile ARN verilir.
- Çalışma ortamının Python sürümü 3.12 ya da üstü olmalıdır (alan kodu 3.12 sözdizimi kullanır).
- Supervisor + uzman zinciri yanıt süresini uzatır; uzun plan isteklerinde uzman okuma sınırı 120 sn'dir.
- Adres hafızası her runtime'da ayrı bir geçici dosyadır: `memory_keeper`'da bırakılan not `courier`'ın kartlarına ve `planner`'ın hafızalı rotasına kalıcı depo (Gereksinim 9) gelene dek yansımaz. Notun aynı oturumda kartta görünmesi demoda gerekiyorsa tek runtime (`CM_MULTI_AGENT=0`) kullanılır.
- Testler betikli sahte modelle ve sahte AWS istemcisiyle çalışır; canlı doğrulama dağıtılmış ajanda yapılır (görev 13, 14a).

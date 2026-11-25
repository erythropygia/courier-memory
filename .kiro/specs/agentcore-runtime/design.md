# Tasarım: AgentCore Runtime'da Courier Memory ajanı

## Genel bakış

```
kurye / müdür
   │  {"prompt", "actorId"}                       agentcore invoke · sohbet arayüzü (esnetme)
   ▼
Amazon Bedrock AgentCore Runtime  (proje CourierMemory, çalışma ortamı "agent", ARM64)
   main.py  BedrockAgentCoreApp · @app.entrypoint (akış) · _get_agent (tembel)
      │
      ├─ Strands Agent ── Amazon Bedrock (Claude, çıkarım profili kimliği)
      │     ├─ kanca: cm/scope.py  BeforeToolCallEvent → kimlik sınırı
      │     ├─ oturum: cm/memory.py → AgentCore Memory "agentMemory" (/users/{actorId}/facts, /episodes/{actorId}/{sessionId})
      │     └─ araçlar: cm/tools.py (9 × @tool)
      │            └─ agents.Services  (Orkestratör, Brifing, Hafıza, Değerlendirme, Bölge; kurallı yol)
      │                   └─ cm_sim.routing_memory · data/demo_run · data/real_day
      └─ OpenTelemetry → CloudWatch  (UNIFIED_TRACES_DESTINATION_ENABLED=true)
```

İlke değişmez (`tech.md`): **LLM karar verir, hesap araçta.** Strands ajanı hangi aracı çağıracağına ve nasıl anlatacağına karar verir; rota, atama, kart seçimi, öz-değerlendirme deterministik Python'dur ve yerel API ile aynı fonksiyonlardır. Bu yüzden dağıtılmış ajanın söylediği sayı, simülasyonda ölçülen sayıyla aynıdır.

## Neden Strands sarmalayıcı, neden beş ajanı doğrudan taşımıyoruz

- Beş alan ajanının kendi döngüsü (`agents/llm.py`) Bedrock Mantle istemcisini ve bu modele özgü istek kurallarını kullanır. Atölye hesabında çalışma ortamı rolü `bedrock:InvokeModel*` verir ve çıkarım profili kimliği ister.
- Strands, atölyenin varsayılan çatısıdır; şablon hafızayı, yük ayrıştırmayı ve izlemeyi hazır getirir.
- Alan ajanlarının her biri zaten "aynı araçlarla kurallı yedek" taşır. Çalışma ortamında bu yol kullanılır; Strands ajanı üst katmanda karar verir. Böylece tek bir LLM çağrı zinciri izlenir ve maliyet öngörülebilir kalır.
- Yerel API beş ajanla birlikte demo arayüzleri (`/story/`, `/flow/`) için çalışmaya devam eder; `CM_BEDROCK_CLIENT=invoke` ile o da çıkarım profili kimliğiyle Bedrock'a gidebilir.

## Dosyalar

| Repoda | Projede (`~/environment/CourierMemory/`) | Ne |
|---|---|---|
| `deploy/agentcore/runtime/main.py` | `app/agent/main.py` | Giriş noktası (şablonunki `.cm/main.template.py` olarak saklanır) |
| `deploy/agentcore/runtime/cm/payload.py` | `app/agent/cm/` | `parse_request`: `prompt`, `actorId`, `day` |
| `…/cm/backend.py` | 〃 | İki arka uç, tembel kurulum: `FullBackend` (`agents.Services`) ve `CoreBackend`; `CM_TOOLSET` = `auto` \| `full` \| `core`; `role_of(actorId)` → courier / manager / guest |
| `…/cm/core.py` | 〃 | Çekirdek takım: `CoreStore` (veri dosyaları, standart kütüphane), sınıflandırıcı, hassas veri ayıklama, kart, yaklaşma |
| `…/cm/tools.py` | 〃 | Dokuz `@tool` (ince sarmalayıcı; hesabı arka uç yapar); `COURIER_TOOLS`, `MANAGER_TOOLS`, `PUBLIC_TOOLS` |
| `…/cm/scope.py` | 〃 | `decide()` (saf) + `CourierScope` kancası |
| `…/cm/prompt.py` | 〃 | Sistem istemi + kimliğe göre "bu istek" bölümü |
| `…/cm/memory.py` | 〃 | `AgentCoreMemorySessionManager` (varsa `MEMORY_AGENTMEMORY_ID`) |
| `…/cm/model.py` | 〃 | Şablonun `model/load.py` yükleyicisi → yoksa `CM_AGENT_MODEL_ID` |
| `agents/`, `sim/cm_sim/`, `sim/config/` | `app/agent/agents/`, `cm_sim/`, `config/` | Alan kodu (kopya) |
| `data/demo_run`, `data/real_day`, `data/map` | `app/agent/data/…` | Veri (kopya, ~28 MB) |
| `deploy/agentcore/bootstrap.sh`, `verify.sh` | — | Kurulum ve kontrol |

Kopyalar tek yönlüdür: düzenleme repoda yapılır, `bootstrap.sh` projeye yazar.

## İki araç takımı

| | Tam | Çekirdek |
|---|---|---|
| Kaynak | `agents.Services` (alan ajanları, hafızalı rota, gerçek gün kapsamı) | `cm/core.py`: `meta.json`, `couriers.json`, `addresses.json`, `memory/<gün>.json`, `snapshots/D/<gün>.json` |
| Bağımlılık | numpy, scipy, pydantic, pyyaml | yalnız standart kütüphane |
| Araç | 9 | 6 (müdür araçları açıklayıcı hata döndürür) |
| Rota sırası | hafızalı sıra (brifingle aynı) | simülasyon planının sırası |
| Not | Hafıza Ajanı (kurallı yol) + `MemoryBook` | aynı kuralların küçük kopyası; oturum dosyasına yazar |


## Erişim modeli

| Araç sınıfı | Araçlar | kurye | müdür | konuk |
|---|---|---|---|---|
| `COURIER_TOOLS` | `courier_briefing`, `stop_cards`, `approaching_stop`, `leave_note` | yalnız kendi `courier_id` | herkes için | yok |
| `MANAGER_TOOLS` | `plan_day`, `morning_review`, `region_report` | yok | var | yok |
| `PUBLIC_TOOLS` | `branch_memory_summary`, `real_day_evidence` | var | var | var |

`role_of`: `actorId` şubenin kuryelerindense kurye; `MUDUR` / `MGR` / `MANAGER` ile başlıyorsa müdür; değilse konuk. Üretimde kimlik, çalışma ortamındaki JWT doğrulayıcının (AgentCore Identity) onayladığı bir talepten gelir; burada atölyedeki gibi istek gövdesinden okunur ki CLI ile sınanabilsin.

Kanca `event.cancel_tool = "<ret metni>"` yazar; Strands bunu hata durumlu araç sonucu olarak modele verir. Ret metni kimin neyi göremeyeceğini söyler, veri içermez.

## Hafıza: iki ayrı şey

| | Adres hafızası (`MemoryBook`) | Konuşma hafızası (AgentCore Memory) |
|---|---|---|
| Ne tutar | Adresin püf noktası ve bilgi kartı; kişiyi değil adresi anlatır | Kimin ne sorduğu, ne söylediği |
| Kapsam | Şube (bütün kuryeler okur) | `actorId` başına |
| Çalışma ortamında | Oturumun geçici dosyası (demo tohumu + oturumdaki notlar) | Yönetilen, oturumlar arası kalıcı |
| Kalıcılık planı | Gereksinim 9 (DynamoDB + Gateway) | hazır |

## Hata yönetimi

- Araç içi hata (bilinmeyen kurye, geçersiz gün) Strands tarafından hata sonucu olarak modele döner; ajan kullanıcıya açıklar.
- Ajan düzeyi hata (model erişimi, kimlik bilgisi) akışa `{"error": "<tür>: <mesaj>"}` olarak yazılır; `agentcore invoke` çıktısında ve sohbet arayüzünde görünür.
- Model erişimi hatası (`AccessDeniedException … Marketplace`) kod sorunu değildir: atölye hesabında `enable_anthropic_models` bir kez çalıştırılır.

## Test stratejisi

- `deploy/agentcore/tests/test_runtime.py` (21 test; araç ve kimlik senaryoları iki takım için ayrı ayrı koşar, alan kodu yoksa tam takımınkiler atlanır): sözleşme (içe aktarma yolu, tembel kurulum), yük ayrıştırma, araçların alan verisi döndürmesi, `decide()` tablosu, uçtan uca üç kimlik senaryosu (kurye kendi aracı · başka kurye reddi ve oturumun sürmesi · konuk), not akışında şifre ayıklama, hatanın akışa yazılması, model kimliği biçimi. Model betikli sahte bir `strands.models.Model`'dir; Bedrock'a gidilmez.
- `verify.sh`: dağıtımdan önce dosya ve yapılandırma denetimi; dağıtımdan sonra Lab 7'nin üç kontrolü.
- Çalışma ortamı kopyasının kendi başına çalıştığı, sahte bir iskele üzerinde `bootstrap.sh` + yalıtık içe aktarma ile denendi (`main` içe aktarımı ~0,2 sn; plan aracı ~0,5 sn).

## Açık riskler

- Şablonun `main.py`, `parse.py`, `memory/session.py` içeriği hazırlıkta görülemedi (CLI yerelde yoktu). Giriş noktamız şablonun yerine geçer ve yalnız `model/load.py`'ye yumuşak bağlıdır; şablon farklı bir hafıza kablolaması getirdiyse `.cm/main.template.py` ile karşılaştırılır (görev 9).
- Çalışma ortamının Python sürümü 3.12 ya da üstü olmalıdır (alan kodu 3.12 sözdizimi kullanır).
- Canlı Bedrock ile hiçbir çağrı yapılmadı; ilk canlı deneme etkinlik hesabındadır.

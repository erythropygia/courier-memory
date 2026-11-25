---
inclusion: always
---
# Teknik yığın ve kurallar

## Temel ilke: LLM karar verir, hesap araçta

- Ajanlar neyin yapılacağına karar verir, sonucu açıklar, istisnaları yönetir.
- Sayısal işler LLM'e yaptırılmaz: atama optimizasyonu, olasılık ve skor hesabı, rota, metrik. Bunlar deterministik Python fonksiyonlarıdır. Ajanlar onları araç (tool) olarak çağırır.
- Aynı araçlar simülatörde de kullanılır. Böylece simülasyonda ölçülen sonuç, ajanın kullandığı hesapla birebir aynıdır. Örnek: hafızalı rota `cm_sim/routing_memory.py` içindeki saf fonksiyonlarla hesaplanır; kol D de Orkestratör'ün `compute_route` aracı da aynısını çağırır (canlı hafıza simülasyonun o günkü hafızasıyken sıra 408/408 rotada birebir aynı; test). Aynı ilke teslim zamanı analizine de uzanır: bulgu ve zaman onarımı `cm_sim/delivery_time.py` + `routing_memory.repair_times` saf fonksiyonlarıdır; ajan rotası simülatör rotasıyla 408/408 aynıdır. Analiz yalnız hedef günden önceki kayıtları sayar (`counts_from_log(..., before_day)`): gelecekten sızıntı yok; hangi bulguların plana gireceğine LLM karar verir, sayı ve seçim araçtadır.

Sert kısıt ilkesi: **onarım rotayı uzatmaz, fazla mesai satın almaz** (`RepairLimits`: süre ≤ +`repair_max_extra_min` (0), km ≤ +`repair_max_extra_km` (0,5; zaman hamlesinde 0), bant ve vardiya bitişi aşılmaz). Kısıt yüzünden kaydırılamayan bulgu müdüre alternatif olur (`cm_sim.routing_memory.time_alternatives`: aktarma / ertesi gün / akşam teslim noktası + SMS; simülatör ve ajan aynı fonksiyon, karar müdürde).

## Dil ve kütüphaneler

- **Python 3.12.**
- **Simülasyon:** `numpy`, `scipy` (`scipy.optimize.linear_sum_assignment` Hungarian için), `pydantic` v2 (yapılandırma ve veri modelleri), `pyyaml`.
- **Test:** `pytest`.
- **API:** `fastapi` + `uvicorn`. Arayüz ile ajanlar ve simülatör arasındaki katman.
- **Arayüz:** Hikaye arayüzü (`ui/story/`): vanilla JS, derleme yok; harita MapLibre GL'nin **yerel kopyası** + **yerel vektör karolar ve yazı tipleri** (internetsiz; karo yoksa çevrimiçi OpenFreeMap), WebGL yoksa 2D tuval; grafikler SVG. API'ye ulaşamazsa kayıtlı yanıtları oynatır. Eski tek sayfa (`ui/`, `/legacy`): tamamen SVG, dış bağımlılık yok.
- **Ses:**
  - P0: tarayıcının `speechSynthesis` (tr-TR) özelliği.
  - P1: Amazon Polly ve Amazon Transcribe.

## LLM: Amazon Bedrock üzerinde Claude

- **İstemci:** `anthropic` Python SDK'sının Bedrock Mantle istemcisi:
  ```python
  from anthropic import AnthropicBedrockMantle
  client = AnthropicBedrockMantle(aws_region=os.environ["AWS_REGION"])
  ```
- **Model:** Koddaki varsayılan `anthropic.claude-opus-5-5`, `CM_MODEL_ID` ortam değişkeniyle değiştirilebilir. Model kimliğine tarih eki eklenmez.
- **Test ve demo modeli: Sonnet ya da Haiku, Opus değil.** Opus kredi tüketir; yalnız bilinçli olarak seçilir. `.env.example`, web dağıtımı ve AgentCore aynı izinli profili kullanır: `CM_BEDROCK_CLIENT=invoke`, `CM_MODEL_ID=global.anthropic.claude-sonnet-5` (AgentCore'da `CM_AGENT_MODEL_ID`). Hafif ajanlar (Hafıza, Brifing) için ajan başına Haiku yeter (`CM_MODEL_MEMORY`, `CM_MODEL_BRIEFING`). Web container'ının görev rolü yalnız izinli Sonnet ve Haiku modellerini çağırabilir.
- **Ajan döngüsü:** Bedrock'ta Anthropic'in yönetilen ajan servisi (Managed Agents) yok. Döngüyü biz kurarız: SDK'nın tool runner yardımcısı ya da elle yazılmış `stop_reason == "tool_use"` döngüsü. Araçlar bizim Python fonksiyonlarımızdır.
- **İstemci seçimi (`CM_BEDROCK_CLIENT`):** `mantle` (varsayılan, yukarıdaki) ya da `invoke` (`anthropic.AnthropicBedrock`, Bedrock Runtime InvokeModel). `invoke` ile model kimliği **çıkarım profili biçiminde** olmalıdır (`CM_MODEL_ID=global.anthropic.claude-sonnet-...`); öneksiz kimlik reddedilir. AgentCore çalışma ortamında izinli yol budur.
- **Barındırma:**
  - Yerel FastAPI süreci: beş alan ajanı + demo arayüzleri (hikaye, nasıl çalışır).
  - Aynı süreç bulutta: kökteki `Dockerfile` ile tek container, Amazon ECS Fargate + Application Load Balancer (`deploy/web/`; spec `aws-dagitim`, yapım aşamasında). App Runner bu hesapta kuruluş politikasıyla kapalı. `main`'e push'ta GitHub Actions (`.github/workflows/ci-cd.yml`) test eder ve değişen parçayı dağıtır; AWS kimliği OIDC ile gelir.
  - Amazon Bedrock AgentCore Runtime: Supervisor + dört uzman (Planlama, Kurye, Hafıza, Analiz), beş runtime tek kod paketi; Strands ajanları alan fonksiyonlarını `@tool` olarak çağırır (`deploy/agentcore/`; kurallar `agentcore.md`).
  - Amazon Quick: chat ajanı → AgentCore Gateway (MCP, Cognito client credentials JWT) → Lambda → Supervisor; sabit kimlik `MUDUR-QUICK` (`deploy/quick/`; spec `quick-koprusu`).


### Bu modelde 400 hatası veren eski kalıplar (kullanma)

- **Zorunlu araç seçimi:** `tool_choice: {"type": "any"}` ve `{"type": "tool", ...}` 400 hatası verir. Yerine `{"type": "auto"}` kullanılır. Araç tanımına `strict: true` eklenir, hangi aracın kullanılacağı istemde açıkça yazılır. Sadece JSON almak için structured outputs (`output_config.format`) kullanılır.
- **Düşünmeyi kapatmak:** `thinking: {"type": "disabled"}` ve `budget_tokens` 400 hatası verir. Derinlik `output_config.effort` ile ayarlanır (`low` | `medium` | `high` | `xhigh` | `max`). Varsayılan `medium`; her çağrıda açıkça yazılır.
- **Örnekleme parametreleri:** `temperature`, `top_p`, `top_k` gönderilmez.
- **Assistant prefill:** Yanıtın başını önceden doldurmak yok. Çıktı biçimi structured outputs ya da sistem istemiyle sağlanır.

### Uyulacak kurallar

- İçerik okunmadan önce `stop_reason` kontrol edilir: `refusal`, `max_tokens`, `tool_use`, `end_turn`.
- Araç girdisi her zaman `json.loads` / pydantic ile ayrıştırılır ve şemaya göre doğrulanır.
- Sabit sistem istemleri ve araç listesi başa konur; prompt caching açılır. Değişken içerik (tarih, gün verisi) sona gelir.
- SDK'nın tipli hata sınıfları kullanılır (`RateLimitError`, `APIStatusError`, `APIConnectionError`). Hata mesajı metin olarak eşleştirilmez.

## Ajan izi ve akış

- Orkestratör ve Hasat Ajanı her adımı `agents/trace.py` olayı olarak yazar (`basla, karar, arac, sonuc, …, awaiting_approval`). Canlı yolda modelin metin blokları `decision` olur (`run_agent(on_text=)`); araç sarmalayıcıları `tool`/`result` yazar.
- Mock (kurallı yedek) aynı araçları aynı sırayla çağırır ve aynı olay biçimini üretir; yalnız `source` alanı farklıdır (`llm | kural | insan`). İzde saat damgası yoktur: mock iz deterministiktir.
- Akış API'den SSE (`/api/orchestrator/session/{id}/stream`) ya da poll (`?after=n`) ile alınır. İnsan onayı ayrı uç noktadır; plan onaysız kesinleşmez.

## Canlı demo güvencesi: kayıt-oynat modu

Canlı demoda ağ, kimlik ya da kota sorunu olabilir. Her LLM çağrısı `CM_LLM_MODE` ortam değişkenine göre çalışır:

- `live`: Bedrock'a gider.
- `record`: Bedrock'a gider ve yanıtı `cassettes/` altına kaydeder.
- `replay`: Ağa çıkmadan kayıttan oynatır.

Demo senaryosu sunumdan önce `record` modunda bir kez koşulur.

## Analiz: Amazon Athena

- Analiz Ajanı geçmiş teslim verisini Athena'da sorgular (`deploy/athena/athena_setup.py` kurar; spec `athena-analiz`). Veritabanı `courier_memory`: `deliveries`, `addresses`, `daily_metrics`, `couriers`. Kurye adı ve serbest metin notlar yüklenmez.
- İlke aynıdır: **LLM karar verir, hesap araçta.** Model soruyu SQL'e çevirir, sayıyı Athena hesaplar. `query_history` yalnız tek bir `SELECT` çalıştırır (en çok 200 satır, 60 sn); çalışma grubu `courier-memory` sorgu başına 100 MB tarar; runtime rolü salt okunurdur.
- Athena verisi `data/demo_run`'ın kopyasıdır, çalışma durumu değildir: yeniden üretimden sonra kurulum betiği yeniden çalıştırılır.

## Depolama

- **P0 (bugün):** Yerel JSON dosyaları (`data/`): canlı adres hafızası `CM_MEMORY_FILE` (`live_memory.json`), ajan akışı aynı klasörde `agent_feed.json`, kullanım kaydı `CM_USAGE_LOG` (`usage.jsonl`). Container'da `/tmp/cm/`; görev yeniden başlayınca demo tohumuna döner.
- **P1 (planlanan, spec `aws-dagitim`):** `CM_STORAGE=dynamodb` ile üçü de bir DynamoDB tablosunda (`CM_DYNAMODB_TABLE`, varsayılan `courier-memory`). `CM_STORAGE=file` varsayılan kalır; testler AWS'siz koşar. Tablo seçilip ulaşılamazsa açılış hatası; sessizce dosyaya düşülmez.
- Hafıza katmanı bir arayüz arkasındadır; P0'dan P1'e geçişte ajan kodu değişmez.
- Konuşma hafızası (AgentCore Memory) ve analiz verisi (Athena) bu depodan ayrıdır.

## Ortam değişkenleri

`AWS_REGION`, `CM_MODEL_ID`, `CM_BEDROCK_CLIENT`, `CM_LLM_MODE`, `CM_RUN_DIR`, ajan başına `CM_MODEL_ASSIGNMENT / MEMORY / BRIEFING / ORCHESTRATOR / HARVEST`; depo `CM_STORAGE`, `CM_DYNAMODB_TABLE`, `CM_MEMORY_FILE`, `CM_USAGE_LOG`; AgentCore `CM_WORKSPACE`, `CM_MULTI_AGENT`, `CM_TARGET`, `CM_AGENT_MODEL_ID` (runtime'ta `CM_AGENT_ROLE`, `CM_RUNTIME_PREFIX`, `CM_ATHENA_DATABASE`, `CM_ATHENA_WORKGROUP`; bunları `agentcore_config.py` yazar). Tam liste açıklamalarıyla `.env.example`'da: `cp .env.example .env`, sonra `uvicorn api.main:app --env-file .env`. `.env` git'e ve image'a girmez. Windows'ta `PYTHONUTF8=1` (konsol kodlaması). Kimlik bilgisi koda ya da repoya yazılmaz; AWS kimliği standart AWS zinciriyle gelir (profil, SSO, görev rolü). `CM_BEDROCK_API_KEY` yalnız yerel `.env`'de durur.

## Komutlar

- Kurulum: `python -m venv .venv`, sonra `. .venv/bin/activate` (Windows: `.venv\Scripts\activate`) ve `pip install -e ".[dev]"` (AgentCore, Athena ve Quick testleri için `".[dev,agentcore]"`)
- Test: `pytest -q` (197 hızlı test, 76'sı `deploy/` altında; yavaşlar: `pytest -q -m slow`, 5 test; toplam 202). Yalnız dağıtım testleri: `pytest -q deploy`. Kalibrasyon: `python -m cm_sim.calibration` → 14/14
- Simülasyon: `python -m cm_sim.run --demo --out runs`, ardından `python -m cm_sim.publish`
- Hedef 1 deneyi: `python -m cm_sim.learning --seeds 12` (~50 sn). Hafızanın parça parça katkısı: `python -m cm_sim.ablation --seeds 3` (~70 sn; varyantlar `no_time`, `full_g60`, `no_time_g60`; sert kısıt: `full_tol5`, `no_time_tol5`, `unconstrained`, `no_time_unconstrained` dahil)
- Sağlamlık taraması: `python -m cm_sim.sweep --seeds 2` (~10 dk; `sweep.json → manset`)
- Yeniden üretim sırası: `cm_sim.run --demo` → `cm_sim.run --scenario long_term --no-snapshots` → `cm_sim.learning` → `cm_sim.ablation` → `cm_sim.sweep` → `cm_sim.publish` → `agents.cost` → `agents.economics` → `agents.presentation_figures`
- API + arayüz: `uvicorn api.main:app --port 8000` → http://localhost:8000 (hikaye; eski tek sayfa `/legacy`). Arayüz yedekleri (mock API açıkken): `python ui/story/tools/record_trace.py http://127.0.0.1:8000` ve `python ui/story/tools/record_fallback.py http://127.0.0.1:8000`
- Bedrock kontrolü: `python -m agents.check`. Hafıza Ajanı ölçümü: `python -m agents.evaluate`
- Container: `docker build -t courier-memory .` ve `docker run -p 8000:8000 courier-memory` (mock, AWS'siz). Bulutta: `python deploy/web/ecs_deploy.py` (spec `aws-dagitim`)
- AgentCore: `deploy/agentcore/bootstrap.sh` → `verify.sh` → `agentcore deploy` → `verify.sh CourierMemory --deployed` (`agentcore.md`)
- Athena: `python deploy/athena/athena_setup.py` (Analiz Ajanı'ndan önce; yeniden üretimden sonra tekrar). Quick köprüsü: `python deploy/quick/quick_bridge_setup.py --test` (Supervisor dağıtıldıktan sonra)

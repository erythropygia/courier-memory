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
- **Model:** Varsayılan `anthropic.claude-opus-5-5`, `CM_MODEL_ID` ortam değişkeniyle değiştirilebilir. Model kimliğine tarih eki eklenmez.
- **Ajan döngüsü:** Bedrock'ta Anthropic'in yönetilen ajan servisi (Managed Agents) yok. Döngüyü biz kurarız: SDK'nın tool runner yardımcısı ya da elle yazılmış `stop_reason == "tool_use"` döngüsü. Araçlar bizim Python fonksiyonlarımızdır.
- **İstemci seçimi (`CM_BEDROCK_CLIENT`):** `mantle` (varsayılan, yukarıdaki) ya da `invoke` (`anthropic.AnthropicBedrock`, Bedrock Runtime InvokeModel). `invoke` ile model kimliği **çıkarım profili biçiminde** olmalıdır (`CM_MODEL_ID=global.anthropic.claude-sonnet-...`); öneksiz kimlik reddedilir. AgentCore çalışma ortamında izinli yol budur.
- **Barındırma:**
  - Yerel FastAPI süreci: beş alan ajanı + demo arayüzleri (hikaye, nasıl çalışır).
  - Amazon Bedrock AgentCore Runtime: Strands ajanı, alan fonksiyonlarını `@tool` olarak çağırır (`deploy/agentcore/`; kurallar `agentcore.md`).

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

## Depolama

- **P0:** Yerel JSON ya da SQLite dosyaları (`data/`).
- **P1:** Adres hafızası için DynamoDB.
- Hafıza katmanı bir arayüz arkasındadır; P0'dan P1'e geçişte ajan kodu değişmez.

## Ortam değişkenleri

`AWS_REGION`, `CM_MODEL_ID`, `CM_LLM_MODE`, `CM_RUN_DIR`, ajan başına `CM_MODEL_ASSIGNMENT / MEMORY / BRIEFING / ORCHESTRATOR / HARVEST` (tam liste: `README.md` → "Ortam değişkenleri"). Windows'ta `PYTHONUTF8=1` (konsol kodlaması). Kimlik bilgisi koda ya da repoya yazılmaz; AWS kimliği standart AWS zinciriyle gelir.

## Komutlar

- Kurulum: `python -m venv .venv`, sonra `. .venv/bin/activate` (Windows: `.venv\Scripts\activate`) ve `pip install -e ".[dev]"`
- Test: `pytest -q` (142 hızlı test; yavaşlar: `pytest -q -m slow`, 5 test; toplam 147). Kalibrasyon: `python -m cm_sim.calibration` → 14/14
- Simülasyon: `python -m cm_sim.run --demo --out runs`, ardından `python -m cm_sim.publish`
- Hedef 1 deneyi: `python -m cm_sim.learning --seeds 12` (~50 sn). Hafızanın parça parça katkısı: `python -m cm_sim.ablation --seeds 3` (~70 sn; varyantlar `no_time`, `full_g60`, `no_time_g60`; sert kısıt: `full_tol5`, `no_time_tol5`, `unconstrained`, `no_time_unconstrained` dahil)
- Sağlamlık taraması: `python -m cm_sim.sweep --seeds 2` (~10 dk; `sweep.json → manset`)
- Yeniden üretim sırası: `cm_sim.run --demo` → `cm_sim.run --scenario long_term --no-snapshots` → `cm_sim.learning` → `cm_sim.ablation` → `cm_sim.sweep` → `cm_sim.publish` → `agents.cost` → `agents.economics` → `agents.presentation_figures`
- API + arayüz: `uvicorn api.main:app --port 8000` → http://localhost:8000 (hikaye; eski tek sayfa `/legacy`). Arayüz yedekleri (mock API açıkken): `python ui/story/tools/record_trace.py http://127.0.0.1:8000` ve `python ui/story/tools/record_fallback.py http://127.0.0.1:8000`
- Bedrock kontrolü: `python -m agents.check`. Hafıza Ajanı ölçümü: `python -m agents.evaluate`

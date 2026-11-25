# Courier Memory

Son-mil teslimatta kuryelerin yazılı olmayan adres bilgisini şubenin ortak hafızasına dönüştüren ve bölgeyi bilmeyen kuryeye doğru anda veren agentic AI uygulaması: çalışan demo ve sunum.

**Simülasyon, ajanlar ve tüm rakamlar uygulama katmanından gelen 1 aylık geçmiş veri ile çalışır** (`.kiro/steering/veri-kurallari.md`). Hikaye arayüzünün harita konumları (Sahne 1'in bölgeleri ve teslim noktaları, sim adreslerinin eşlendiği noktalar) Beykoz saha verisinden türetilmiştir; barkod, kurye kimliği, bölge kodu ve şirket içi adlar yoktur.

## Canlı sistem (AWS, us-east-1)

**https://d21h79c269fwie.cloudfront.net** · sunum ekranı `/flow/?sunum=1` (**Günü planla** ve **AgentCore zinciri**), izleme `/flow/`, hikaye `/story/`, QR demo izi `/demo/`, API `/docs`.

12 ajan: 7 alan ajanı web uygulamasında (Amazon ECS Fargate, CloudFront → ALB) canlı Claude ile; Supervisor + 4 uzman Amazon Bedrock AgentCore Runtime'da, aynı alan ajanlarını araç olarak çağırır. Ortak durum Amazon DynamoDB'de, geçmiş veri Amazon Athena'da, ses Amazon Transcribe ve Amazon Polly ile; Amazon Quick ve Kiro AgentCore Gateway (MCP) üzerinden bağlanır; `main`'e her push GitHub Actions + OIDC ile dağıtılır. Mimari: `docs/mimari/aws-altyapi.gif`, `docs/mimari/mimari-akis.gif`. İnceleyenler için kanıt tablosu: `AGENTS.md`.

## Hızlı başlangıç

```bash
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
export CM_LLM_MODE=mock PYTHONUTF8=1  # Windows PowerShell: $env:CM_LLM_MODE="mock"; $env:PYTHONUTF8="1"
pytest -q                            # 337 hızlı test, ~2 dk (AgentCore ve DynamoDB testleri için: pip install -e ".[dev,agentcore]"); yavaşlar: pytest -q -m slow (5 test) → toplam 342
uvicorn api.main:app --port 8000     # http://localhost:8000 → hikaye arayüzü (/story/); eski tek sayfa /legacy
```

Ayarlar ve kimlik bilgileri: `cp .env.example .env` (`.env` git'e ve Docker image'ına girmez), sonra `uvicorn api.main:app --env-file .env`. Canlı Bedrock için `CM_LLM_MODE=live`, `CM_BEDROCK_CLIENT=invoke`, `CM_MODEL_ID=global.anthropic.claude-sonnet-5`; deneme ve demoda Opus yerine Sonnet ya da Haiku.

macOS + Python 3.13 ve üstü: `ModuleNotFoundError: No module named 'cm_sim'` alırsanız neden, Masaüstü gibi eşitlenen klasörlerde `.pth` dosyasının gizli işaretlenmesi ve Python'un gizli `.pth` dosyalarını atlamasıdır. Çözüm: `chflags nohidden .venv/lib/python*/site-packages/*.pth` ya da komutların başına `PYTHONPATH=sim:.`. Testler etkilenmez (`pyproject.toml` yolu kendisi ekler).

Varsayılan mod `mock`: AWS gerekmez, her şey çalışır. Windows'ta komut çıktısı boruya giderse konsol kodlaması (cp1254) `✓` gibi karakterlerde çöker; `PYTHONUTF8=1` bunu önler.

## Ne var

| Parça | Klasör | Ne yapar |
|---|---|---|
| Simülatör | `sim/` (`cm_sim`) | Şube; dört kol (A sabit bölge, B geçmişe bakmadan atama, C uyum, D çekirdek bölge + hafıza; hafıza planı ve rotayı değiştirir). Ortak rastgele sayılar, karşı-olgu (hafızasız / yalnız ipucu / hafızalı), sağlamlık taraması, `learning` (Hedef 1) ve `ablation` (hafızanın parça parça katkısı). Şubede sabah: kurye mesai başı + sabah süresinden sonra çıkar (bugün ~10:30, ayrıştırma indirme okutmasına gömülünce ~09:30; şube beyanı), fazla mesai vardiya bitişinden (17:48) sayılır. |
| Orkestratör | `agents/orchestrator.py`, `trace.py`, `route.py` | Günü yöneten ajan: hacim → kapasite açığı → komşu şubeden "kim gitsin" (sınır sokak tanıklığıyla adaylar eşitsiz) → çekirdek bölgeli atama → hafızalı rota → müdüre gerekçeli öneri → insan onayı. Her adım canlı iz (SSE). Hesap deterministik araçlarda; rota, simülatörle aynı `cm_sim/routing_memory.py` fonksiyonlarını kullanır. |
| Ajanlar | `agents/` | Atama, Hafıza, Brifing ve Hasat ajanları (Hasat: kıdemlinin bilgisini hedefli sorularla toplar, `harvest.py`). Teslim zamanı analizi (`delivery_time.py`): kayıtlardan "bu adreste şu saatte kimse yok" örüntüsü, Orkestratör hangi bulgunun rotaya gireceğine karar verir. Onarım rotayı uzatmaz (süre ve km artmaz, fazla mesai yok, vardiya bitişi aşılmaz); kısıt yüzünden kaydırılamayan durak için müdüre alternatif önerilir (başka kuryeye aktarma / ertesi gün / akşam teslim noktası + alıcıya SMS), karar müdürdedir. Bedrock'ta Claude; `mock / live / record / replay` modları. Rotayı etkilemeyen bilgi türleri (park, bina erişimi, adres tarifi, hayvan, diğer; şifre asla kaydedilmez), durak bilgi kartları ve konuma göre "şimdi söyle" tetiği (`cards.py`). Değerlendirme Ajanı (sabah öz-değerlendirme, geri alınabilir düzeltmeler, `review.py`), Bölge Ajanı (durak · küme · şube, `region_agent.py`), ajan akışı (`feed.py`). Gerçek 5 Mayıs servisi (`real_day.py`: hafıza kapsamı, kurye aktarımı). Token ölçümü ve ekonomi hesabı (`cost.py`, `economics.py`, `economics.yaml`). |
| API | `api/` | FastAPI: simülasyon verisi, ajanlar, orkestratör (SSE iz), hasat, rota, teslim zamanı, ekonomi, durak kartları, Değerlendirme/Bölge ajanları, ajan akışı, gerçek 5 Mayıs |
| Hikaye arayüzü | `ui/story/` | Demo + sunumun tamamı tek ekranda, 8 sahne (Sorun · Sabah · Onay · Kapıda · Hasat · Öğrenme · Değer · Kapanış); sunucu → ile ilerler, her adım canlı API'ye bağlı. MapLibre + yerel karolar (internetsiz), API yoksa kayıtlı yanıtlar (`data/trace_fallback.json`, `data/fallback.json`). Sahne 1 gerçek veri (yukarıdaki istisna) |
| Canlı zincir | `ui/flow/` (`/flow/`), `api/live.py`, `api/agentcore_chain.py` | Zincir sunucuda bir kez çalışır, her olay sırayla bütün izleyicilere yayınlanır (SSE). `/flow/?sunum=1` sunum ekranı: **Günü planla** (8 adım: Orkestratör → acil durum kapısı → Brifing → Hafıza → durak kartları → Hasat → Değerlendirme → Bölge) ve **AgentCore zinciri** (6 adım: Supervisor → uzman → alan aracı → sonuç; plan, brifing, not, hasat, Athena analizi, kimlik reddi). `/flow/` yalnız izler (QR hedefi) |
| Eski tek sayfa | `ui/legacy/` (`/legacy`) | Şube, Kurye, Simülasyon, Değer sekmeleri; ayrıntı ekranı, dış bağımlılık yok |
| AgentCore Runtime | `deploy/agentcore/` | Tek kod paketinden beş runtime (`CM_AGENT_ROLE`): Supervisor (`agent`) işi `ask_*` araçlarıyla uzmana verir; Planlama, Kurye, Hafıza ve Analiz uzmanları 10 alan aracını ve Athena SQL'i (`query_history`) kullanır. Kimlik sınırı (`BeforeToolCallEvent`; kimlik istekten gelir), AgentCore Memory, CloudWatch izleri ve uzmandan Supervisor'a akan `cm_trace` olayları. `bootstrap.sh` yerleştirir, `agentcore_config.py` runtime'ları ve en az yetkili politikaları yazar, `verify.sh` dağıtımı denetler. Spec: `agentcore-runtime`, `agentcore-zinciri` |
| AWS dağıtımı | `deploy/web/`, `deploy/quick/`, `deploy/athena/`, `deploy/dynamodb/`, `deploy/ci/`, `.github/workflows/` | Web: kökteki `Dockerfile` → ECR → ECS Fargate, ALB yalnız CloudFront'a açık (`ecs_deploy.py`, `cloudfront_setup.py`). Amazon Quick ve Kiro köprüsü: AgentCore Gateway (MCP, Cognito) → Lambda → Supervisor. Athena tabloları, DynamoDB tablosu. CI/CD: `main`'e push'ta değişen parça dağıtılır (OIDC, secret yok; pipeline test koşmaz). Spec: `aws-dagitim`, `quick-koprusu`, `athena-analiz` |
| Kiro | `.kiro/` | 17 spec, 8 steering dosyası, 4 skill, 5 hook, iki MCP sunucusu (`deploy/mcp/` yerel, `deploy/quick/kiro_mcp_proxy.py` canlı ajanlar). Özet: `AGENTS.md` |
| Hazır veri | `data/demo_run/` | Demo çalıştırması, uzun dönem (60 gün), sağlamlık taraması, kalibrasyon, token ve ekonomi |
| Belgeler | `docs/` | `sozlesmeler.md` (parçalar arası arayüz; §6 hafıza ve rota, §7 teslim zamanı, §8 sert kısıt ve alternatifler, §9 hikaye arayüzü, §10 sabah, §11 durak kartları, §12 Değerlendirme/Bölge ajanları, §13 gerçek gün), `veri-haritasi.md` (her veri dosyasının kaynağı, okuyanı, gerçek/uygulama verisi, yeniden üretim zinciri), `sunum.md` (sunum ve demo metni) |

## Sık komutlar

```bash
python -m cm_sim.calibration                    # uygulama verisi ↔ saha verisinden türetilmiş toplu hedefler (14/14)
python -m cm_sim.run --demo --out runs          # demo senaryolarıyla simülasyon (~40 sn) + rapor
python -m cm_sim.run --scenario long_term --no-snapshots --out runs   # 60 iş günü (~1,5 dk)
python -m cm_sim.learning --seeds 12             # Hedef 1: işe alım deneyi, yeni kuryenin öğrenme eğrisi (~50 sn) → runs/learning/
python -m cm_sim.ablation --seeds 3             # hafızanın katkısı parça parça: ipucu / hasat / rota / zaman (+60 gün geçmiş) (~2 dk) → runs/ablation/
python -m cm_sim.sweep --seeds 2                # sağlamlık taraması (~10 dk, 81 kombinasyon)
python -m cm_sim.publish                        # demo + uzun dönem + tarama + kalibrasyon + öğrenme + ablasyon → data/demo_run/
python -m agents.cost                        # ajan çağrısı başına token (tahmin; canlı ölçüm varsa ölçüm)
python -m agents.economics                        # token maliyeti ↔ kazanç → data/demo_run/economics.json
python -m agents.check                        # Bedrock bağlantı kontrolü (canlı)
curl -s -X POST localhost:8000/api/orchestrator/plan -H 'content-type: application/json' -d '{"day": 32}'   # günün planı + iz
curl -s localhost:8000/api/route/32/O02          # hafızasız ↔ hafızalı rota, değişikliklerin nedeni
curl -s localhost:8000/api/orchestrator/candidates/32   # "kim gitsin": adaylar, tanıdık pay, gerekçe (LLM yok)
curl -s -X POST localhost:8000/api/harvest/plan -H 'content-type: application/json' -d '{"day": 32}'   # Hasat Ajanı: günün soruları + iz
curl -s localhost:8000/api/time/example                # Teslim zamanı: adres geçmişi (saat → sonuç), bulgu, rota değişikliği, sonuç
curl -s localhost:8000/api/time/32/alternatives     # kısıt yüzünden kaydırılamayan duraklar için aktarma / ertesi gün / SMS önerisi (karar müdürde)
curl -s localhost:8000/api/cards/32/O02             # durak bilgi kartları (yaklaşırken / kapıda, kaynak sayısı, teyit)
curl -s -X POST localhost:8000/api/approach -H 'content-type: application/json' -d '{"day": 32, "courier": "O02", "lat": 39.0232, "lng": 35.0163}'   # konuma göre şimdi söylenecek kartlar
curl -s -X POST localhost:8000/api/review/run -H 'content-type: application/json' -d '{"day": 32}'   # Değerlendirme Ajanı: sabah öz-değerlendirme
curl -s -X POST localhost:8000/api/region/run -H 'content-type: application/json' -d '{"day": 32}'   # Bölge Ajanı: şube raporu, boşluğa soru
curl -s localhost:8000/api/feed                     # ajan akışı
curl -s localhost:8000/api/real-day/2026-05-05/memory   # gerçek 5 Mayıs: hafıza kapsamı, beklenen başarısız (tanıdık %3,0 · yabancı %11,9)
curl -s localhost:8000/api/real-day/2026-05-05/transfer # kurye aktarımı: yeniden dengeleme (yaklaşık) → bilgi kaybı + hafıza
curl -s localhost:8000/api/learning              # Hedef 1 eğrisi (önlenebilir başarısız / 100 durak, iş gününe göre)
curl -s localhost:8000/api/morning/32             # ayrıştırma planı (raf, yükleme sırası), rota başına çıkış ↔ bugünkü sabah
curl -s -X POST localhost:8000/api/morning/scan -H 'content-type: application/json' -d '{"day": 32, "shipment": "G32-38507-1"}'   # indirme okutması → raf talimatı
python -m agents.evaluate --n 60             # Hafıza Ajanı doğruluğu (gizli karşılıkla)
CM_LLM_MODE=record python -m agents.record      # demo akışını kayıt-oynat için kaydet
python ui/story/tools/prepare.py                               # hikaye sahne verisi (pip install -e ".[story]"; veri yeniden üretilince ŞART)
python ui/story/tools/record_trace.py http://127.0.0.1:8000     # (mock API açıkken) Sahne 2 kayıtlı iz
python ui/story/tools/record_fallback.py http://127.0.0.1:8000  # (mock API açıkken) Sahne 3–7 kayıtlı yanıtlar + demo seçimleri
```

Rakamları yeniden üretme sırası (kod ya da parametre değişince):

```bash
python -m cm_sim.run --demo --out runs
python -m cm_sim.run --scenario long_term --no-snapshots --out runs
python -m cm_sim.learning --seeds 12
python -m cm_sim.ablation --seeds 3
python -m cm_sim.sweep --seeds 2
python -m cm_sim.publish
python -m agents.cost && python -m agents.economics && python -m agents.presentation_figures
python ui/story/tools/prepare.py   # sonra mock API açıkken: tools/record_fallback.py ve tools/record_trace.py
```

## Ortam değişkenleri

Tam liste ve açıklamaları: `.env.example`.

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `CM_LLM_MODE` | `mock` | `mock \| live \| record \| replay` |
| `CM_BEDROCK_CLIENT` | `mantle` | `mantle` ya da `invoke` (Bedrock Runtime; model kimliği çıkarım profili biçiminde, ör. `global.anthropic.claude-sonnet-5`). Canlı dağıtım `invoke` kullanır |
| `CM_MODEL_ID` | `anthropic.claude-opus-5-5` | Bedrock model kimliği (canlı dağıtımda `global.anthropic.claude-sonnet-5`) |
| `CM_MODEL_ASSIGNMENT` / `CM_MODEL_MEMORY` / `CM_MODEL_BRIEFING` / `CM_MODEL_ORCHESTRATOR` / `CM_MODEL_HARVEST` | — | Ajan başına model (ör. optimize senaryo: Hafıza/Brifing `anthropic.claude-haiku-5-5`) |
| `AWS_REGION` | `us-east-1` | Bedrock bölgesi |
| `CM_BEDROCK_API_KEY` / `AWS_PROFILE` | — | İsteğe bağlı kimlik |
| `CM_RUN_DIR` | `data/demo_run` | Çalıştırma klasörü |
| `CM_MEMORY_FILE` | `data/live_memory.json` | Canlı hafıza dosyası |
| `CM_POLLY` | `0` | `1`: `/api/speech` Amazon Polly kullanır (mock modda kapalı; hata/kapalıyken 501, arayüz tarayıcı sesine düşer) |
| `CM_POLLY_VOICE` / `CM_POLLY_ENGINE` | `Burcu` / `neural` | Polly tr-TR sesi ve motoru. Burcu yalnız `neural`, Filiz yalnız `standard`; motor boşsa sese göre seçilir |
| `CM_TRANSCRIBE` | `0` | `1`: sesli not `/api/transcribe` ile Amazon Transcribe Streaming'de (tr-TR) çözülür; kapalıyken 501, arayüz tarayıcının ses tanımasını kullanır. Bölge `AWS_REGION`; IAM: `transcribe:StartStreamTranscription` |
| `CM_TRANSCRIBE_TIMEOUT` | `30` | Transcribe çağrısı zaman aşımı (sn); aşılırsa 504 |
| `CM_AUTO_CACHE` | `1` | Otomatik prompt önbelleği (üst düzey `cache_control`) |
| `CM_USAGE_LOG` | `data/usage.jsonl` | Canlı token kullanım günlüğü |
| `CM_STORAGE` | `file` | Çalışma durumu deposu: `file` (JSON dosyaları; `CM_MEMORY_FILE`, `agent_feed.json`, `CM_USAGE_LOG`) \| `dynamodb` (canlı hafıza, ajan akışı ve token kullanımı tek DynamoDB tablosunda; web uygulaması ve AgentCore çalışma ortamları aynı durumu paylaşır, kullanım dosyaya da yazılır). Bölge `AWS_REGION` / `AWS_DEFAULT_REGION`. Anahtar düzeni: `agents/storage/dynamo_keys.py` |
| `CM_DYNAMODB_TABLE` | `courier-memory` | `CM_STORAGE=dynamodb` iken tablo adı. Kurulum, taşıma ve en az yetki politikası: `python deploy/dynamodb/create_table.py [--migrate] [--print-policy]` |
| `CM_DYNAMODB_SYNC_SECONDS` | `0` | DynamoDB hafıza önbelleğinin sürüm kontrol aralığı; `0` her okumada kontrol eder (süreçler arası tam tutarlı). Örn. `1`: diğer süreçlerin yazımları en çok 1 sn gecikmeyle görünür, okuma başına istek düşer; yazımlar her zaman tazeler |

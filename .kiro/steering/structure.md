---
inclusion: always
---
# Repo yapısı

```
sim/                      Dünya + simülatör (spec: dunya-simulator)
  config/default.yaml     Tüm parametreler, gerekçe yorumlarıyla (sabah bölümü dahil)
  config/scenarios/*.yaml Senaryo katmanları (leave_wave, turnover, borrowed_courier, volume_shock, normal, long_term, hiring)
  config/sweep.yaml       Sağlamlık taraması ızgarası
  cm_sim/
    config.py rng.py world.py couriers.py demand.py planning.py
    history.py            Gözlemlenebilir geçmiş + HistoryReader
    outcome.py notes.py estimation.py
    delivery_time.py      Teslim zamanı analizi (5 dilim, Beta-Binomial büzme, pencere/teyit bulguları); saf, kol D ve agents/delivery_time.py aynısını çağırır
                          (+ alternative_text, REASON_TEXT, OPTION_NAME)
    routing_memory.py     Hafıza → rota kısıtı (planda erteleme, servis düzeltmesi, pencere onarımı, zaman onarımı `repair_times`); saf fonksiyonlar, kol D ve agents/route.py aynısını çağırır
                          RepairLimits (onarım rotayı uzatmaz), time_blocked, time_alternatives (aktarma / ertesi gün / akşam teslim noktası + SMS)
    policies/base.py      Arayüzler ve *View tipleri
    policies/simple.py    BlindPolicy (B), FitAssignPolicy (C/D)
    policies/memory_oracle.py  Deterministik hafıza (D)
    engine.py             Isınma → çatallama → dört kol (D: kendi planı, hasat, karşı-olgu); şubeden çıkış (sabah), vardiya bitişinden fazla mesai, current_morning karşı-olgusu
    export.py run.py sweep.py publish.py
    learning.py            Hedef 1: işe alım deneyi (senaryo hiring), öğrenme eğrisi
    ablation.py           Hafızanın katkısı parça parça (ipucu / hasat / rota)
  tests/
agents/                   Ajanlar (spec: ajanlar)
  llm.py                  Bedrock istemcisi + ajan döngüsü + kayıt-oynat
  rundata.py memorybook.py guardrails.py tr.py
  assignment.py memory.py briefing.py
  harvest.py                Hasat Ajanı: HarvestTools, HarvestAgent, HarvestStore, SeniorSimulator (+ prompts/harvest.md)
  delivery_time.py        TimeData, TimeSource, parse_confirmation (+ Orkestratör araçları delivery_time_analysis, apply_time_constraint, time_alternatives; Hasat time_confirmations)
  orchestrator.py          Orkestratör: DayTools (araçlar; sorting_plan), plan/ask/apply_decision, SessionStore
  trace.py                   Ajan izi (olay sırası; docs/sozlesmeler.md §5)
  route.py                 RoutePlanner + EtaModel + MemoryConstraints; cm_sim.routing_memory'yi import eder (tek fonksiyon, iki kullanıcı)
                          repair_limits(rc), day_alternatives, time_unshiftable[], comparison.route_constraint
  cards.py                Durak bilgi kartları ve yaklaşma tetiği (StopCards; bilgi türleri rotaya girmez)
  feed.py                 Ajan akışı: ajanların her işi zaman sıralı (AgentFeed)
  review.py               Değerlendirme Ajanı: sabah öz-değerlendirme, geri alınabilir düzeltmeler (ReviewStore)
  region.py region_agent.py  Bölge Ajanı: blok zorluğu, küme kartı, şube raporu, boşluğa soru
  real_day.py stop_order.py  Gerçek 5 Mayıs: hafıza kapsamı, küme rotası, kurye aktarımı
  prompts/*.md            Türkçe sistem istemleri
  evaluate.py check.py record.py
  tests/
api/main.py               FastAPI (spec: api-arayuz; /api/orchestrator/*, /api/route, /api/harvest/*, /api/learning, /api/time/*, /api/time/{gün}/alternatives; /api/morning/{gün}, /api/morning/scan)
api/tests/
ui/                       Arayüzler (hepsi API'den sunulur)
ui/legacy/                Eski tek sayfa demo (index.html, app.js, style.css); /legacy adresinde ayrıntı ekranı
ui/story/                 Hikaye arayüzü (demo + sunumun tamamı, 8 sahne; spec api-arayuz Gereksinim 7); / → /story/
  js/stage.js common.js chart.js   Harita/durum altyapısı, API (kayıt yedekli), ajan izi, ses, SVG grafikler
  js/narration.js           Her adımın açıklama satırı: Ne oluyor · Ekranda · Veri (A tuşu)
  js/scene1.js … scene8.js            Sorun · Sabah · Onay · Kapıda · Hasat · Öğrenme · Değer · Kapanış
  data/                   scene1.json (gerçek veri istisnası, veri-kurallari.md), scene2.json, sim_mapping.json, trace_fallback.json, fallback.json
  tools/                  prepare.py (sahne verisi), record_trace.py (Sahne 2 yedeği), record_fallback.py (Sahne 3–7 yedeği), download_tiles.py
  vendor/ tiles/ fonts/   MapLibre, yerel vektör karolar, yazı tipleri (internetsiz)
ui/flow/                  "Nasıl çalışır" arayüzü (/flow/): bir günün akışı 8 adımda, ajan izi ve API çağrıları (spec: akis-arayuzu)
ui/direction/             Tasarım yönü demosu (tek dosya)
deploy/agentcore/         Amazon Bedrock AgentCore Runtime: Supervisor + dört uzman, beş runtime tek kod (spec: agentcore-runtime)
  runtime/main.py         Giriş noktası: BedrockAgentCoreApp, tembel _get_agent, akış döndüren @app.entrypoint
  runtime/cm/             Strands araçları (tools.py), kimlik sınırı kancası (scope.py), istem (prompt.py), AgentCore Memory, model
    roles.py              CM_AGENT_ROLE → runtime'ın araçları; Supervisor'ın ask_* araçları (kimlik kapanışta)
    delegate.py           Supervisor → uzman: InvokeAgentRuntime, ARN'yi adla bulma, uzman oturumu, akış ayrıştırma
    athena.py             Analiz Ajanı'nın query_history aracı: tek SELECT, 200 satır, 60 sn (spec: athena-analiz)
  agentcore_config.py     agentcore.json dönüşümü: beş runtime, envVars, supervisor-policy.json, analyst-policy.json
  bootstrap.sh verify.sh  `agentcore create` iskelesine kodu yerleştirir · yerel ön kontrol + dağıtımın üç kontrolü
  tests/                  Betikli sahte model ve sahte AWS istemcisiyle testler (Bedrock'a ve AWS'ye gitmez)
deploy/athena/            Athena kurulumu: athena_setup.py (S3, çalışma grubu, courier_memory veritabanı, dört tablo) + tests/ (spec: athena-analiz)
deploy/quick/             Amazon Quick köprüsü: bridge_lambda.py (Gateway hedefi → Supervisor), quick_bridge_setup.py, README.md, tests/ (spec: quick-koprusu)
deploy/web/               Web container'ı ECS Fargate + ALB'ye: ecs_deploy.py, README.md (spec: aws-dagitim; yapım aşamasında)
deploy/ci/                github_oidc_setup.py: GitHub Actions için anahtarsız (OIDC) dağıtım rolü (spec: aws-dagitim)
deploy/mcp/               Projenin MCP sunucusu (şube hafızası, salt okunur); Kiro .kiro/settings/mcp.json ile yükler
.github/workflows/ci-cd.yml  Her push ve PR'da test; main'de değişen parçaya göre web, AgentCore ve Quick köprüsü dağıtımı
Dockerfile .dockerignore  FastAPI + arayüzler tek container (python:3.12-slim, kök olmayan kullanıcı, varsayılan mock)
.env.example              Bütün ortam değişkenleri açıklamalı; gizli değer yok (.env git'e ve image'a girmez)
.kiro/                    steering/ (her oturumda), specs/ (özellik başına gereksinim · tasarım · görev), skills/ (istenince çalışan
                          yönergeler), hooks/ (kaydetmede/araçta çalışan otomasyon), settings/mcp.json
data/real_day/ data/map/  Gerçek 5 Mayıs günü ve yol bacakları (docs/veri-haritasi.md)
data/demo_run/            Hazır çalıştırma (uygulama verisi, 1 aylık geçmiş) (+ sweep.json, learning.json, ablation.json, harvest.json, delivery_log.json, time.json)
cassettes/                Kayıt-oynat LLM yanıtları
docs/                     sozlesmeler.md, sunum.md, sunum_rakamlari.md, veri-haritasi.md
runs/                     Simülasyon çıktıları: yayımlanan iki çalıştırma + deney çıktıları (docs/veri-haritasi.md)
```

## Adlandırma

- **Kod İngilizce:** Değişken, fonksiyon, sınıf, modül ve dosya adları, API yolları, JSON alanları, enum değerleri, CSS sınıfları ve DOM kimlikleri, ortam değişkenleri, senaryo ve yapılandırma anahtarları İngilizcedir (eski ad → yeni ad: `docs/ad-eslemesi.tsv`).
- **Türkçe kalanlar:** Kullanıcıya görünen metin, ajan istemleri (`agents/prompts/*.md`; dosya adları ajan adıyla İngilizce), yorumlar ve docstring'ler, dokümanlar (`docs/`, `.kiro/`, dosya adlarıyla) ve serbest metinde aranan Türkçe anahtar kelimeler (ör. `agents/memory.py → KEYWORDS` değerleri, `agents/delivery_time.py` teyit kalıpları).
- **Domain terimleri kodda:**
  - `courier` (kurye), `stop` (durak = farklı teslim noktası), `shipment` (gönderi), `block` (~300 m blok), `cluster` (günlük dinamik küme), `zone` (sabit bölge), `arm` (simülasyon kolu A–D)
  - `quirk` (adresin gizli püf noktası), `note` (kurye notu), `memory_entry` (hafıza kaydı), `hint` (kapı ipucu), `fit` (kurye–bölge uyumu), `familiar` / `unfamiliar` (tanıdık / yabancı sokak)
  - Ajanlar: `assignment` (atama), `memory` (hafıza), `briefing` (brifing), `harvest` (hasat), `orchestrator` (orkestratör); `session` (orkestratör koşusu), `trace` (ajan izi), `tool` (ajan aracı), `decision` (karar), `proposal` (öneri), `approval` (onay), `rationale` (gerekçe)
  - Plan ve rota: `route` (rota), `band` (vardiya bandı), `overtime` (fazla mesai), `shift_end` (vardiya bitişi), `deferral` (erteleme), `window` (kapalı pencere), `transfer` (aktarma), `next_day` (ertesi gün)
  - Teslim zamanı: `delivery_time` (teslim zamanı analizi), `finding` (bulgu), `confirmation` (teyit), `slot` (saat dilimi), `unshiftable` (kısıt yüzünden kaydırılamayan), `presence` (bulunabilirlik)
  - Sabah: `morning` (sabah akışı), `sorting` (ayrıştırma), `scan` (okutma), `shelf` (raf), `departure` (şubeden çıkış), `presorted` (ayrıştırması indirme okutmasına gömülü)
  - Ölçüm: `fails` (başarısız teslim sayısı), `preventable` (bilgiyle önlenebilir), `counterfactual` (karşı-olgu), `calibration` (kalibrasyon), `learning` (Hedef 1 deneyi), `ablation` (ablasyon), `sweep` (sağlamlık taraması), `economics` (ekonomi)
  - Senaryolar: `leave_wave` (izin dalgası), `turnover` (ayrılan kıdemli + yeni kurye), `borrowed_courier` (ödünç kurye), `volume_shock` (hacim şoku), `hiring` (işe alım), `long_term` (uzun dönem), `normal`
  - Arayüz: `ui/story/` (hikaye arayüzü, `/story/`), `ui/flow/` (nasıl çalışır, `/flow/`), `ui/legacy/` (eski tek sayfa, `/legacy`), `scene` (sahne), `fallback` (kayıtlı yanıt)
  - `card` (durak kartı), `moment` (`approaching` / `at_door`), `approach` (yaklaşma tetiği), `feed` (ajan akışı), `review` (Değerlendirme Ajanı), `region` (Bölge Ajanı), `real_day` (gerçek gün)
  - AgentCore: `actorId` (istek kimliği: kurye, müdür ya da konuk), `scope` (kimlik sınırı), `runtime` (AgentCore çalışma ortamı), `agent_role` (runtime'ın rolü), `supervisor` (yönlendiren ajan), `specialist` (uzman ajan: `planner`, `courier`, `memory_keeper`, `analyst`), `delegate` (uzmana yönlendirme), `harvest_questions` (hafıza hasadı aracı)
  - Analiz ve dağıtım: `query_history` (salt okunur SQL aracı), `workgroup` (Athena çalışma grubu), `bridge` (Quick köprüsü), `storage` (çalışma durumunun deposu: `file` / `dynamodb`)
- **Takma bölge adları:** "B01", "B02"… Gerçek bölge kodları kullanılmaz.

## Gizli gerçek ile gözlemlenebilir veri ayrımı

- `cm_sim` iki tür nesne tutar:
  - **Gizli gerçek:** kurye becerisi, adres püf noktaları, blok zorluğu.
  - **Gözlemlenebilir veri:** geçmiş teslimatlar, notlar, ziyaretler.
- Politikalar ve ajanlar **yalnızca gözlemlenebilir görünümleri** alır. Gizli gerçek sadece sonuç modeli ve değerlendirme metrikleri tarafından okunur.

# Tasarım: AWS'de web uygulaması ve kalıcı durum

## Genel bakış

```
GitHub (main)  ── .github/workflows/ci-cd.yml
   │  test (mock) ─► değişen dosyalar ─┬─ web:       docker build linux/amd64 → ECR → yeni görev tanımı → ECS
   │                                   ├─ agentcore: bootstrap.sh + verify.sh → agentcore deploy (5 runtime + hafıza)
   │                                   └─ quick:     köprü Lambda kodu
   │  OIDC → courier-memory-github-deploy (yalnız bu deponun main dalı)
   ▼
Amazon ECR  courier-memory-web   (yüklemede tarama, son 10 image)
   ▼
internet ──► ALB courier-memory-web  HTTP 80, boşta 300 sn ──► hedef grup (ip) · sağlık /api/status
                                                                  ▼
Amazon ECS  cluster courier-memory · servis courier-memory-web  (Fargate, 1 vCPU / 2 GB, 1 görev, varsayılan VPC)
   container "web": uvicorn api.main:app :8000  (kök olmayan kullanıcı; yalnız ALB güvenlik grubundan erişim)
      ├─ /story/ · /flow/ · /legacy · /docs     arayüzler (yerel karo ve yazı tipleri)
      ├─ /api/*                                 alan ajanları (agents.Services)
      │     └─ Amazon Bedrock  InvokeModel  global.anthropic.claude-sonnet-5   ← courier-memory-web-task rolü
      ├─ log → CloudWatch Logs /ecs/courier-memory-web (14 gün)
      └─ depo (CM_STORAGE)
            file      /tmp/cm/live_memory.json · agent_feed.json · usage.jsonl   (görev ömrü kadar)
            dynamodb  Amazon DynamoDB  CM_DYNAMODB_TABLE (courier-memory)       (kalıcı)   [planlanan]
```

Bütün kaynaklar projenin bölgesindedir (`AWS_REGION`; bugün `us-east-1`). AgentCore Runtime, Athena ve Quick köprüsü bu dağıtımdan bağımsızdır; CI yalnız onların kodunu günceller.

## Neden ECS Fargate

- İlk plan AWS App Runner'dı (tek container, hazır TLS ve yük dengeleme). Bu hesapta App Runner kuruluş politikasıyla kapalıdır.
- ECS Fargate + ALB aynı tek container'ı çalıştırır; sunucu yönetimi yoktur. ALB'nin boşta kalma süresi 300 sn'ye çekilir: ajan izi SSE ile akar (`/api/orchestrator/session/{id}/stream`), varsayılan 60 sn uzun planı keserdi.
- Tek görev, `minimumHealthyPercent: 0`, `maximumPercent: 100`: dağıtımda eski görev durur, yenisi açılır (kısa kesinti). Dosya deposunda iki görev aynı anda farklı hafıza görürdü. Tablo deposuna geçilince görev sayısı artırılabilir (Gereksinim 7.5 sağlandıktan sonra).

## Dosyalar

| Dosya | Durum | Ne |
|---|---|---|
| `Dockerfile` | repoda | `python:3.12-slim`; bağımlılık katmanı (numpy, scipy, pydantic, pyyaml, fastapi, uvicorn, anthropic[bedrock]); `sim/cm_sim`, `sim/config`, `agents`, `api`, `data`, `ui` kopyalanır; kullanıcı `app` (uid 10001); `HEALTHCHECK` `/api/status`; varsayılan `CM_LLM_MODE=mock` |
| `.dockerignore` | repoda | `.git`, `.venv`, `.env*`, `docs`, `deploy`, `.kiro`, `**/tests`, `runs`, `ui/story/tools`, yerel durum dosyaları |
| `.env.example` | repoda | Bütün ortam değişkenleri, açıklamalı; gizli değer yok (`.gitignore` → `!.env.example`) |
| `deploy/web/ecs_deploy.py` | yazılıyor | ECR, güvenlik grupları, ALB + hedef grup + dinleyici, iki IAM rolü, log grubu, görev tanımı, cluster ve servis; `--skip-build`, `--image-tag`, `--env`, `--extra-policy` |
| `deploy/web/README.md` | yazılıyor | İlk kurulum, sonraki dağıtımlar, yerelde çalıştırma |
| `deploy/ci/github_oidc_setup.py` | yazılıyor | GitHub OIDC sağlayıcısı ve `courier-memory-github-deploy` rolü |
| `.github/workflows/ci-cd.yml` | yazılıyor | `test`, `changes`, `deploy-web`, `deploy-agentcore`, `deploy-quick` |
| `agents/storage.py` (ad öneri) | planlanan | Depo arayüzü ve iki gerçekleme (`file`, `dynamodb`); `CM_STORAGE` seçimi |
| `deploy/dynamodb/create_table.py` | planlanan | Tablo kurulumu (tekrar çalıştırmak güvenli) |

## Web dağıtımı

| Kaynak | Ad | Ayar |
|---|---|---|
| ECR deposu | `courier-memory-web` | `scanOnPush`, yaşam döngüsü: son 10 image |
| Güvenlik grubu | `courier-memory-web-alb` | giriş: her yerden TCP 80 |
| Güvenlik grubu | `courier-memory-web-task` | giriş: yalnız ALB güvenlik grubundan TCP 8000 |
| ALB | `courier-memory-web` | internete açık, varsayılan VPC'nin alt ağları, boşta kalma 300 sn, dinleyici HTTP 80 |
| Hedef grup | `courier-memory-web` | `ip`, HTTP 8000, sağlık `/api/status` (15 sn, 2 sağlıklı / 5 sağlıksız), kayıt silme gecikmesi 15 sn |
| IAM rolü | `courier-memory-web-exec` | `AmazonECSTaskExecutionRolePolicy` (image çekme, log) |
| IAM rolü | `courier-memory-web-task` | satır içi `bedrock-allowed-models`; `--extra-policy` ile eklenenler |
| Log grubu | `/ecs/courier-memory-web` | 14 gün |
| Görev tanımı | `courier-memory-web` | Fargate, `awsvpc`, X86_64, 1 vCPU / 2 GB, container `web` |
| ECS | cluster `courier-memory`, servis `courier-memory-web` | 1 görev, genel IP, sağlık bekleme 120 sn, devre kesici + geri alma |

- **Model izni:** `bedrock:InvokeModel` ve `InvokeModelWithResponseStream`, yalnız `global.` ve `us.` çıkarım profilleri ile Sonnet 5 ve Haiku 4.5 temel modelleri için. Opus izinli değildir: demo ve test krediyi tüketmez.
- **Ortam:** `CM_LLM_MODE=live`, `CM_BEDROCK_CLIENT=invoke`, `CM_MODEL_ID=global.anthropic.claude-sonnet-5`, `CM_AUTO_CACHE=1`, `CM_RUN_DIR=data/demo_run`, `AWS_REGION`. `CM_BEDROCK_API_KEY` kullanılmaz; kimlik görev rolündendir.
- **Erişim:** bugün HTTP 80. Alan adı ve TLS (ACM sertifikası + HTTPS dinleyici) demo dışı kullanım için sonraki adımdır.

## Sürekli dağıtım

| İş | Ne zaman | Ne yapar |
|---|---|---|
| `changes` | PR dışında | `dorny/paths-filter` ile `web`, `agentcore`, `quick` çıktıları |
| `deploy-web` | `main`, `web` değiştiyse ya da el ile | ECR girişi → `<commit[:12]>` etiketiyle derle, yükle → mevcut görev tanımını yeni image'la kaydet → servisi güncelle, kararlılığı bekle |
| `deploy-agentcore` | `main`, `agentcore` değiştiyse ya da el ile | AgentCore CLI (sabit sürüm) → `CM_WORKSPACE=<geçici>` + `CM_AGENT_MODEL_ID` ile `bootstrap.sh` → `verify.sh` → `agentcore deploy` |
| `deploy-quick` | `main`, köprü kodu değiştiyse | Lambda kodunu güncelle, güncellemenin bitmesini bekle |

Dağıtım rolü (`courier-memory-github-deploy`):

| Sid | İzin |
|---|---|
| `EcrLogin`, `EcrPushWeb` | yetki jetonu; yalnız `courier-memory-web` deposuna katman ve image yükleme |
| `EcsTaskDefinitions`, `EcsWebService` | görev tanımı okuma ve kaydetme; yalnız `courier-memory/courier-memory-web` servisini güncelleme |
| `PassWebRoles` | yalnız iki web rolünü, yalnız `ecs-tasks.amazonaws.com`'a |
| `QuickBridgeCode` | yalnız `courier-memory-quick-bridge` kodunu güncelleme ve okuma |
| `CdkBootstrapRoles`, `CdkBootstrapVersion` | CDK önyükleme rollerini üstlenme (CloudFormation dağıtımını onlar yapar), sürüm parametresi |
| `AgentCoreCliRead` | CloudFormation, AgentCore, X-Ray ve Logs okuma çağrıları |

Güven ilişkisi: `token.actions.githubusercontent.com`, `aud = sts.amazonaws.com`, `sub = repo:<depo>:ref:refs/heads/main`. Pull request'ten dağıtım yapılamaz.

## Depo arayüzü (planlanan)

```
Services.create(..., storage=CM_STORAGE)
   ├─ MemoryBook(run, store)     upsert · feedback · flag_for_confirmation · undo · drop · summary · reset · ensure
   ├─ AgentFeed(store)           add · update · items(after, agent, status) · reset
   └─ LLM(usage=store)           _log_usage → append
store = dosya deposu (bugünkü dosyalar)  |  DynamoDB deposu (CM_DYNAMODB_TABLE)
```

- Arayüz bugünkü sınıfların okuma ve yazma noktalarına oturur; sınıfların kuralları (kişisel veri reddi, kaynak sayısı, teyit, düşürme) değişmez. Bu yüzden iki depo aynı işlem dizisinde aynı hafızayı verir; eşitlik testi iki depoda aynı senaryoyu koşar (DynamoDB için sahte istemci).
- Dosya deposu bugünkü atomik dosya yazımını ve `threading.Lock`'u korur.
- DynamoDB deposu kayıt başına koşullu yazma kullanır (sürüm alanı); çakışmada okur, yeniden uygular. Böylece birden çok görev aynı kaydı kaybetmeden günceller.
- `CM_STORAGE=dynamodb` seçilip tablo yoksa ya da izin yoksa açılış hatası verilir; dosyaya düşüş yoktur (demo sırasında sessiz durum ayrılığı olmasın).

## Tablo (planlanan)

Tek tablo, `pk` + `sk` anahtarları; kayıt türü anahtar önekinden okunur. Başlangıç önerisi (görev 11'de kesinleşir):

| Kayıt | `pk` | `sk` | Alanlar |
|---|---|---|---|
| Hafıza kaydı | `MEM#<run_id>` | `ENTRY#<kayıt kimliği>` | `MemoryBook` kaydının alanları + `version` |
| Hafıza üst bilgisi | `MEM#<run_id>` | `META` | `seed_day`, tohum durumu |
| Akış olayı | `FEED` | `<sıra, sıfır dolgulu>` | `AgentFeed` olayı |
| Kullanım kaydı | `USAGE#<gün>` | `<zaman>#<kısa kimlik>` | ajan, model, süre, token sayıları |

- İsteğe göre ödemeli kapasite, sunucu tarafı şifreleme. Kişisel veri ve ham not tabloya yazılmaz (ayıklama `MemoryBook`'ta yazmadan önce).
- Akış sırası tek bir sayaç kaydıyla (atomik artırma) verilir; `items(after=n)` `sk > n` sorgusudur.

## Ortam değişkenleri

| Değişken | Varsayılan | Ne |
|---|---|---|
| `CM_STORAGE` | `file` | `file` \| `dynamodb` |
| `CM_DYNAMODB_TABLE` | `courier-memory` | Tablo adı |
| `CM_MEMORY_FILE` | `data/live_memory.json` (container'da `/tmp/cm/live_memory.json`) | Dosya deposunda hafıza; akış dosyası aynı klasörde |
| `CM_USAGE_LOG` | `data/usage.jsonl` | Dosya deposunda kullanım kaydı |
| `CM_LLM_MODE`, `CM_BEDROCK_CLIENT`, `CM_MODEL_ID` | `mock`, `mantle`, `anthropic.claude-opus-5-5` (kod) | Serviste `live`, `invoke`, `global.anthropic.claude-sonnet-5` |

Tam liste ve açıklamalar `.env.example`'dadır.

## Test stratejisi

- Depo arayüzü: iki depoda aynı senaryo (tohum → not → geri bildirim → düşürme → sıfırlama) aynı özeti verir; DynamoDB tarafı sahte istemciyle, AWS'siz.
- Koşullu yazma: aynı kayda iki eşzamanlı güncelleme ikisini de korur (`api/tests/test_concurrency.py` deseni).
- `CM_STORAGE` geçersiz değer ve ulaşılamayan tablo açılış hatası verir.
- Image: `docker build` + `docker run` (mock) → `/api/status` 200, `/story/` açılır.
- Pipeline yalnız dağıtım yapar, test koşmaz; testler push'tan önce yerelde çalıştırılır. `main`'e push'ta yalnız değişen parçanın işi koşar.
- Dağıtım: `ecs_deploy.py` sonrası Gereksinim 11'in dört kontrolü.

## Açık riskler

- Dosya deposunda görev yeniden başlayınca ya da yeniden dağıtılınca canlı hafıza demo tohumuna döner; DynamoDB deposu gelene dek bu bilinen sınırdır.
- Tek görev ve `minimumHealthyPercent: 0`: her dağıtımda kısa bir kesinti olur; demo sırasında dağıtım yapılmaz.
- Görev ve ALB her zaman açıktır; demo bitince servis durdurulmazsa saatlik ücret işler. Durdurma ve silme adımı README'ye yazılır.
- Erişim HTTP'dir; demo dışı kullanımda TLS gerekir.
- Pipeline dosyası hesap kimliğini ve rol adını açık taşır; gizli değildir ama depo herkese açıksa bilinmelidir.
- AgentCore'daki `memory_keeper`'ın adres hafızası (`agentcore-runtime` Gereksinim 9) ile web uygulamasının tablosunun aynı tablo olup olmayacağı henüz kararlaştırılmadı; iki yazar aynı tabloya yazarsa kayıt biçimi ortak olmalıdır.
- `data/` image'ın içindedir (~28 MB); yeniden üretimden sonra image yeniden derlenmezse servis eski demo verisini sunar.

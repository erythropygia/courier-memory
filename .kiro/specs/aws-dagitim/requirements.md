# Gereksinimler: AWS'de web uygulaması ve kalıcı durum

## Giriş

Yerel FastAPI süreci (alan ajanları + hikaye, nasıl çalışır ve eski tek sayfa arayüzleri) bugün bir dizüstünde çalışıyor; canlı adres hafızası (`MemoryBook`), ajan akışı (`AgentFeed`) ve kullanım kaydı yerel JSON dosyalarında. Bu spec üç şeyi tanımlar:

1. **Web dağıtımı:** FastAPI ve arayüzler tek bir container'da (kökteki `Dockerfile`), image Amazon ECR'da, servis **Amazon ECS Fargate** üzerinde, önünde bir **Application Load Balancer**. Container'ın kimliği görev rolüdür; yalnız izinli Bedrock modellerini çağırır. İlk plan AWS App Runner'dı; bu hesapta kuruluş politikasıyla kapalı olduğu için ECS kullanılır.
2. **Sürekli dağıtım:** `main`'e her push'ta GitHub Actions değişen parçaya göre web'i, AgentCore ajanlarını ve Quick köprüsünü günceller. AWS kimliği OIDC ile gelir; GitHub'da secret yoktur.
3. **Kalıcı durum:** çalışma durumu `CM_STORAGE=dynamodb` ile bir **Amazon DynamoDB** tablosuna (`CM_DYNAMODB_TABLE`) taşınır. `CM_STORAGE=file` (varsayılan) bugünkü davranıştır; testler AWS'siz çalışır.

İlke (`tech.md` → Depolama): hafıza katmanı bir arayüz arkasındadır; dosyadan tabloya geçişte ajan kodu değişmez. AgentCore Runtime ayrı bir dağıtımdır (`agentcore-runtime`); bu spec yerel API'nin bulut karşılığıdır.

Durum: yapım aşamasında. `Dockerfile`, `.dockerignore` ve `.env.example` repoda; `deploy/web/`, `deploy/ci/` ve `.github/workflows/ci-cd.yml` yazılıyor; DynamoDB deposu henüz yok.

## Gereksinimler

### Gereksinim 1: Container image
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, demoyu herhangi bir makinede tek komutla aynı biçimde çalıştırmak istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL kökteki `Dockerfile` ile FastAPI'yi ve arayüzleri (`/story/`, `/flow/`, `/legacy`, `/docs`) tek container'da sunmalıdır; taban `python:3.12-slim`, port 8000.
2. THE SYSTEM SHALL bağımlılıkları koddan ayrı bir katmanda kurmalıdır (kod değişince yeniden kurulmaz) ve yalnız çalışma zamanı paketlerini almalıdır.
3. THE SYSTEM SHALL uygulamayı kök olmayan bir kullanıcıyla çalıştırmalıdır; yazma yalnız `/tmp/cm` ve `/app/data` altındadır.
4. THE SYSTEM SHALL varsayılan olarak AWS'siz açılmalıdır (`CM_LLM_MODE=mock`, `CM_MEMORY_FILE=/tmp/cm/live_memory.json`); canlı mod ortam değişkeniyle seçilir.
5. THE SYSTEM SHALL `/api/status` üzerinden sağlık denetimi taşımalı ve vekil başlıklarını kabul etmelidir (`--proxy-headers`).
6. THE SYSTEM SHALL `.dockerignore` ile `.env`, `.git`, `.kiro`, `deploy`, `docs`, `runs`, testleri, sahne üretim araçlarını ve yerel durum dosyalarını (`live_memory.json`, `agent_feed.json`, `usage.jsonl`) image dışında tutmalıdır.

### Gereksinim 2: Image deposu
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, her dağıtımın hangi image'la yapıldığını bilmek ve eski image'ların birikmemesini istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL image'ı `courier-memory-web` adlı bir ECR deposuna etiketli olarak yüklemelidir; image `linux/amd64` için derlenir.
2. THE SYSTEM SHALL depoda yüklemede güvenlik taramasını açmalı ve yalnız son 10 image'ı tutmalıdır.

### Gereksinim 3: ECS Fargate servisi ve yük dengeleyici
**Kullanıcı hikayesi:** Bir şube müdürü olarak, demoyu bir adresten açmak istiyorum; bir dizüstüne bağlı kalmasın.

#### Kabul kriterleri
1. WHEN `deploy/web/ecs_deploy.py` çalıştırıldığında THE SYSTEM SHALL image'ı derleyip yüklemeli, ağ kaynaklarını, yük dengeleyiciyi, rolleri, görev tanımını ve servisi kurmalı ya da güncellemelidir; `--skip-build --image-tag <etiket>` ile ECR'daki image doğrudan dağıtılır.
2. THE SYSTEM SHALL internete açık tek kapıyı yük dengeleyicinin 80 numaralı portu yapmalıdır; container'ın 8000 portu yalnız yük dengeleyicinin güvenlik grubundan erişilebilir.
3. THE SYSTEM SHALL hedef grubun sağlık denetimini `/api/status` ile yapmalı ve yük dengeleyicinin boşta kalma süresini 300 sn yapmalıdır (canlı ajan akışları kesilmesin).
4. THE SYSTEM SHALL görevi Fargate'te 1 vCPU / 2 GB ile çalıştırmalıdır.
5. WHILE durum dosyadayken (`CM_STORAGE=file`) THE SYSTEM SHALL tek görevle çalışmalıdır; durum tek yerde kalır.
6. IF yeni görev tanımı sağlıklı açılmazsa THEN THE SYSTEM SHALL dağıtımı durdurmalı ve önceki tanıma geri dönmelidir (devre kesici + geri alma).
7. THE SYSTEM SHALL container loglarını CloudWatch Logs'a (`/ecs/courier-memory-web`, 14 gün saklama) yazmalıdır.
8. THE SYSTEM SHALL betiği tekrar çalıştırmayı güvenli kılmalıdır (aynı adlı kaynak güncellenir); servis kararlı olana dek beklenir ve sonunda servis adresi yazdırılır.

### Gereksinim 4: Container kimliği ve model
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, container'ın anahtar taşımamasını ve yalnız izinli modelleri çağırmasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL container'a AWS kimliğini görev rolüyle (`courier-memory-web-task`) vermelidir; erişim anahtarı ya da Bedrock API anahtarı image'a ve görev tanımına yazılmaz.
2. THE SYSTEM SHALL image çekme ve log yazmayı ayrı bir yürütme rolüne (`courier-memory-web-exec`) vermelidir.
3. THE SYSTEM SHALL görev rolüne yalnız izinli modellerin çıkarım profilleri ve temel modelleri için `bedrock:InvokeModel` ve `bedrock:InvokeModelWithResponseStream` iznini vermelidir (Sonnet ve Haiku; Opus yok).
4. WHEN ek izin gerektiğinde (ör. `CM_STORAGE=dynamodb`) THE SYSTEM SHALL bunu `--extra-policy <dosya>` ile görev rolüne satır içi politika olarak eklemelidir; tablo izni yalnız `CM_DYNAMODB_TABLE` tablosuyla sınırlıdır.
5. THE SYSTEM SHALL serviste canlı modu şu ortamla açmalıdır: `CM_LLM_MODE=live`, `CM_BEDROCK_CLIENT=invoke`, `CM_MODEL_ID=global.anthropic.claude-sonnet-5`, `CM_AUTO_CACHE=1`, `CM_RUN_DIR=data/demo_run`, `AWS_REGION`; ek değişken `--env KEY=VALUE` ile verilir.

### Gereksinim 5: Sürekli dağıtım
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, `main`'e birleşen her değişikliğin elle komut çalıştırmadan, yalnız ilgili parçası güncellenerek yayına çıkmasını istiyorum.

#### Kabul kriterleri
1. WHEN bir push ya da pull request geldiğinde THE SYSTEM SHALL hızlı test takımını mock modda, AWS'siz koşmalıdır.
2. WHEN `main`'e push edildiğinde THE SYSTEM SHALL değişen dosyalara göre yalnız ilgili işleri çalıştırmalıdır: web (container'a giren kod ve veri), AgentCore (`deploy/agentcore/**`, alan kodu, veri), Quick köprüsü (`deploy/quick/bridge_lambda.py`); el ile tetiklemede web ve AgentCore birlikte dağıtılır.
3. THE SYSTEM SHALL pipeline'da test koşmamalı; testler push'tan önce yerelde çalıştırılmalıdır (`CM_LLM_MODE=mock pytest -q`).
4. WHEN web dağıtılırken THE SYSTEM SHALL image'ı commit kimliğiyle etiketlemeli, mevcut görev tanımını yeni image'la yeniden kaydetmeli ve servisin kararlı olmasını beklemelidir.
5. WHEN AgentCore dağıtılırken THE SYSTEM SHALL projeyi geçici bir çalışma alanında `bootstrap.sh` ile kurmalı (`CM_AGENT_MODEL_ID` ile), `verify.sh` ile denetlemeli ve `agentcore deploy` ile beş runtime'ı ve hafızayı dağıtmalıdır.
6. WHEN Quick köprüsü değiştiğinde THE SYSTEM SHALL yalnız köprü Lambda'sının kodunu güncellemelidir.
7. THE SYSTEM SHALL AWS'ye GitHub OIDC ile girmelidir; dağıtım rolünü (`courier-memory-github-deploy`) yalnız bu deponun `main` dalı üstlenebilir ve GitHub'da AWS anahtarı tutulmaz.
8. THE SYSTEM SHALL dağıtım rolünün izinlerini pipeline'ın dokunduğu kaynaklarla sınırlamalıdır: ECR'da yalnız `courier-memory-web`'e yükleme, ECS'te yalnız `courier-memory-web` servisini güncelleme ve iki web rolünü yalnız ECS görevlerine verme, Lambda'da yalnız köprünün kodunu güncelleme, AgentCore için CDK önyükleme rollerini üstlenme ve CLI'nin okuma çağrıları.
9. THE SYSTEM SHALL OIDC sağlayıcısını ve dağıtım rolünü `deploy/ci/github_oidc_setup.py` ile tekrar çalıştırmaya güvenli biçimde kurmalıdır.

### Gereksinim 6: Depo seçimi
**Kullanıcı hikayesi:** Bir geliştirici olarak, yerelde dosyayla, bulutta tabloyla aynı kodu çalıştırmak istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL çalışma durumunun yerini `CM_STORAGE` ile seçmelidir: `file` (varsayılan) ya da `dynamodb`.
2. IF `CM_STORAGE` başka bir değer alırsa ya da `dynamodb` seçilip tabloya ulaşılamazsa THEN THE SYSTEM SHALL açılışta nedenini söyleyen bir hata vermelidir; sessizce dosyaya düşmez.
3. THE SYSTEM SHALL depoyu bir arayüz arkasında tutmalıdır; `MemoryBook`, `AgentFeed` ve kullanım kaydını kullanan ajan ve API kodu depo seçiminden habersizdir.
4. WHEN `CM_STORAGE=file` iken THE SYSTEM SHALL bugünkü dosyaları ve davranışı aynen korumalıdır (`CM_MEMORY_FILE`, `agent_feed.json`, `CM_USAGE_LOG`); hızlı test takımı AWS'siz geçer.

### Gereksinim 7: DynamoDB'de canlı adres hafızası
**Kullanıcı hikayesi:** Bir kurye olarak, bıraktığım notun servis yeniden başladığında da şubenin hafızasında kalmasını istiyorum.

#### Kabul kriterleri
1. WHEN `CM_STORAGE=dynamodb` iken THE SYSTEM SHALL `MemoryBook` kayıtlarını `CM_DYNAMODB_TABLE` tablosunda tutmalıdır; görev yeniden başlayınca ya da yeniden dağıtılınca kayıtlar kalır.
2. THE SYSTEM SHALL tablo boşken hafızayı bugünkü gibi demo tohumundan kurmalı ve `/api/memory/reset` ile aynı tohuma dönebilmelidir.
3. THE SYSTEM SHALL kişisel veri ve kapı şifresi kuralını tabloda da uygulamalıdır: ayıklama yazmadan önce yapılır, tabloya ham not yazılmaz.
4. THE SYSTEM SHALL kaydın alanlarını ve sonuçlarını dosya deposuyla aynı tutmalıdır (upsert, geri bildirim, teyit işareti, geri alma, düşürme, özet); aynı işlem dizisi iki depoda aynı hafızayı verir.
5. WHEN iki istek aynı kaydı aynı anda değiştirdiğinde THE SYSTEM SHALL birinin değişikliğini sessizce kaybetmemelidir.

### Gereksinim 8: DynamoDB'de ajan akışı ve kullanım kaydı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, ajanların dün ne yaptığını ve ne kadar model çağrısı yapıldığını servis yeniden başlasa da görmek istiyorum.

#### Kabul kriterleri
1. WHEN `CM_STORAGE=dynamodb` iken THE SYSTEM SHALL ajan akışı olaylarını tabloda sıra numarasıyla tutmalıdır; `/api/feed?after=n` sırayı ve süzgeçleri (`agent`, `status`) aynen korur.
2. THE SYSTEM SHALL model kullanım kaydını (çağrı başına ajan, model, zaman, süre ve token sayıları; bugünkü `usage.jsonl` satırıyla aynı alanlar) tabloya eklemelidir; kayıt yalnız eklenir, değiştirilmez.
3. THE SYSTEM SHALL bu kayıtlarda istem ya da yanıt metni tutmamalıdır.

### Gereksinim 9: Tablo kurulumu
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, tabloyu tek komutla kurmak istiyorum.

#### Kabul kriterleri
1. WHEN `deploy/dynamodb/create_table.py` çalıştırıldığında THE SYSTEM SHALL `CM_DYNAMODB_TABLE` (varsayılan `courier-memory`) tablosunu projenin bölgesinde kurmalıdır; tablo varsa dokunmaz.
2. THE SYSTEM SHALL tabloyu sunucu tarafı şifrelemeyle ve isteğe göre ödemeli kapasiteyle kurmalıdır.
3. THE SYSTEM SHALL tek bir tabloda üç kayıt türünü (hafıza kaydı, akış olayı, kullanım kaydı) anahtar önekiyle ayırmalıdır.
4. THE SYSTEM SHALL tablo iznini yalnız bu tabloya okuma ve yazma veren bir politikayla, görev rolüne `ecs_deploy.py --extra-policy` ile vermelidir.

### Gereksinim 10: Ortam değişkenleri ve gizli değerler
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, hangi değişkenin ne işe yaradığını tek dosyadan öğrenmek ve gizli değeri repoya koymamak istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL bütün ortam değişkenlerini açıklamalarıyla `.env.example` dosyasında listelemelidir; dosyada gizli değer yoktur.
2. THE SYSTEM SHALL `.env` dosyasını git'in ve image'ın dışında tutmalı, `.env.example`'ı git'e almalıdır.
3. THE SYSTEM SHALL `.env.example`'da test ve demo için Sonnet ya da Haiku modelini önermelidir (`CM_MODEL_ID=global.anthropic.claude-sonnet-5`); Opus kredi tüketir.

### Gereksinim 11: Dağıtım sonrası doğrulama
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, dağıtımın gerçekten çalıştığını kontrollerle görmek istiyorum.

#### Kabul kriterleri
1. WHEN servis kararlı olduğunda THE SYSTEM SHALL yük dengeleyicinin adresinde `/api/status` için 200 dönmelidir.
2. WHEN adreste `/` açıldığında THE SYSTEM SHALL hikaye arayüzüne (`/story/`) yönlendirmeli ve arayüz yerel kopyalarla (harita karoları, yazı tipleri) açılmalıdır.
3. WHEN canlı modda Orkestratör planı istendiğinde THE SYSTEM SHALL Bedrock'a görev rolüyle gitmeli, izi SSE ile kesilmeden göstermelidir.
4. WHEN `CM_STORAGE=dynamodb` iken bir not bırakılıp servis yeniden dağıtıldığında THE SYSTEM SHALL notu kartta göstermeye devam etmelidir.

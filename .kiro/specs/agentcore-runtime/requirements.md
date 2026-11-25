# Gereksinimler: AgentCore Runtime'da Courier Memory ajanı

## Giriş

Courier Memory'nin alan mantığı (hafıza, kart, rota, plan, öz-değerlendirme) bugün yerel bir FastAPI sürecinde çalışıyor. Bu spec onu **Amazon Bedrock AgentCore Runtime**'a taşır: bir Strands ajanı alan fonksiyonlarını araç olarak çağırır, kimlik sınırını kodda zorlar, konuşmayı AgentCore Memory'de hatırlar ve izlerini CloudWatch'a yollar.

**Brif**

| Girdi | Değer |
|---|---|
| Kullanım alanı | Kuryelerin yazılı olmayan adres bilgisini şubenin ortak hafızasına taşıyan ve bölgeyi bilmeyen kuryeye doğru anda veren asistan. **Asla** kişisel veri ya da kapı şifresi kaydetmez ve söylemez; kuryeyi puanlamaz; planı müdür onayı olmadan uygulamaz |
| Kullanıcı | Kurye (telefonda, sürüş sırasında kısa cevap) ve şube müdürü (sabah planı, değerlendirme, bölge raporu) |
| Bilgi kaynağı | Şubenin adres hafızası ve teslim kayıtları (`data/demo_run`, uygulama verisi, 1 aylık geçmiş) + gerçek 5 Mayıs günü (`data/real_day`). Belge tabanlı Knowledge Base gerekmez: cevaplar araçlardan gelir |
| Araçlar | Dokuz Strands `@tool`: `courier_briefing`, `stop_cards`, `approaching_stop`, `leave_note`, `plan_day`, `morning_review`, `region_report`, `branch_memory_summary`, `real_day_evidence` |
| Çatı | Strands, şablon `agent-python-strands` |

Çerçeve kuralları `.kiro/steering/agentcore.md` dosyasındadır.

## Gereksinimler

### Gereksinim 1: Dağıtım
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, ajanın yönetilen bir çalışma ortamında yayında olmasını istiyorum; böylece demo bir dizüstüne bağlı kalmaz.

#### Kabul kriterleri
1. THE SYSTEM SHALL `$CM_WORKSPACE` içinde (varsayılan: reponun üst klasörü) `agentcore create --name CourierMemory --template agent-python-strands` ile kurulmuş bir projede yaşamalıdır; klasör yapısı elle kurulmaz.
2. WHEN `agentcore deploy` çalıştırıldığında THE SYSTEM SHALL AgentCore Runtime'a dağıtılmalı ve `agentcore status` çalışma ortamını ARN'siyle dağıtılmış göstermelidir.
3. THE SYSTEM SHALL çalışma zamanı bağımlılıklarını yalnız `app/agent/pyproject.toml` → `[project].dependencies` içinde tutmalıdır (numpy, scipy, pydantic, pyyaml); test araçları oraya girmez.

### Gereksinim 2: Gözlemlenebilirlik
**Kullanıcı hikayesi:** Bir geliştirici olarak, ajanın hangi aracı ne kadar sürede çağırdığını izlerden görmek istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL `agentcore/agentcore.json` içinde çalışma ortamının `envVars` listesinde `UNIFIED_TRACES_DESTINATION_ENABLED` girdisini `true` değeriyle taşımalıdır.
2. WHEN dağıtılmış ajan bir kez çağrıldığında THE SYSTEM SHALL `/aws/bedrock-agentcore/runtimes/<agent-id>-DEFAULT` log grubunu oluşturmuş ve `agentcore traces runtime list --since 15m` o çağrının izini listelemiş olmalıdır.
3. THE SYSTEM SHALL her ajan izine `cm.actor_role` ve `cm.actor_id` özniteliklerini eklemelidir (kimin adına çalıştığı izde görünür).

### Gereksinim 3: Araçlar
**Kullanıcı hikayesi:** Bir kurye ya da müdür olarak, ajanın tahmin etmesini değil şubenin verisine bakmasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL en az bir aracı Strands `@tool` olarak açmalıdır; bu spec dokuz araç tanımlar (brif tablosu).
2. WHEN bir araç çağrıldığında THE SYSTEM SHALL sayıları ve adres bilgisini `agents.Services` içindeki deterministik fonksiyonlardan almalı ve JSON metni döndürmelidir; model hesap yapmaz.
3. WHEN `leave_note` kişisel veri ya da kapı şifresi içeren bir notla çağrıldığında THE SYSTEM SHALL bunları ayıklamalı, hafızaya yazmamalı ve sonuçta `personal_data_redacted: true` bildirmelidir.
4. IF araç geçersiz gün ya da bilinmeyen kurye ile çağrılırsa THEN THE SYSTEM SHALL hatayı araç sonucu olarak modele vermeli ve konuşma kesilmemelidir.
5. WHEN `agentcore invoke` ile "kullanım alanını anlat ve bir aracını çağır" istenirse THE SYSTEM SHALL akışta en az bir araç çağrısı ve aracın döndürdüğü veriyi içeren bir cevap üretmelidir.

### Gereksinim 4: Giriş noktası sözleşmesi
**Kullanıcı hikayesi:** Bir geliştirici olarak, çalışma ortamının 30 saniyelik başlangıç sınırını aşmamasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL `BedrockAgentCoreApp`'i `bedrock_agentcore.runtime` modülünden içe aktarmalıdır (paket kökünden değil).
2. THE SYSTEM SHALL modeli, alan servislerini ve hafıza oturumunu ilk istekte kurmalıdır (`_get_agent`); modül içe aktarımı ağ ya da veri yüklemesi yapmaz.
3. THE SYSTEM SHALL isteği `@app.entrypoint` ile süslü, akış döndüren asenkron bir üreteçle karşılamalı ve `app.run()` çağrısını yalnız `__main__` altında yapmalıdır.
4. WHEN istek gövdesi geldiğinde THE SYSTEM SHALL `prompt` ve `actorId` alanlarını okumalıdır; `actorId` yoksa çağıran konuk (`default`) sayılır.
5. THE SYSTEM SHALL akışa yalnız JSON'a çevrilebilir ham model olaylarını (`{"event": …}`) yazmalıdır.
6. IF istekte `prompt` yoksa ya da ajan hata verirse THEN THE SYSTEM SHALL akışa `{"error": …}` olayı yazmalı ve bağlantıyı düzgün kapatmalıdır.

### Gereksinim 5: Kimlik sınırı (kurye yalnız kendi verisini görür)
**Kullanıcı hikayesi:** Bir kurye olarak, rotamın ve notlarımın başka kuryeye açılmamasını; bir müdür olarak da şube planının kuryeye açılmamasını istiyorum.

#### Kabul kriterleri
1. WHEN bir kurye kimliğiyle gelen istekte ajan, `courier_id` girdisi o kimlikten farklı bir kurye aracı çağırdığında THE SYSTEM SHALL çağrıyı araç çalışmadan iptal etmeli ve modele "erişim reddedildi" sonucunu vermelidir.
2. WHEN kurye ya da konuk kimliğiyle gelen istekte ajan bir müdür aracı (`plan_day`, `morning_review`, `region_report`) çağırdığında THE SYSTEM SHALL çağrıyı iptal etmelidir.
3. WHEN kimliksiz (konuk) istekte ajan bir kurye aracı çağırdığında THE SYSTEM SHALL çağrıyı iptal etmeli; herkese açık araçlar (`branch_memory_summary`, `real_day_evidence`) çalışmalıdır.
4. WHEN bir çağrı reddedildiğinde THE SYSTEM SHALL konuşmayı sürdürmeli ve aynı oturumda çağıranın kendi verisi erişilebilir kalmalıdır.
5. THE SYSTEM SHALL sınırı kodda (`BeforeToolCallEvent` kancası) zorlamalıdır; sistem istemi kimliği ayrıca söyler ama tek savunma değildir.
6. THE SYSTEM SHALL reddedilen çağrının sonucunda başka kuryeye ait hiçbir veri taşımamalıdır.

### Gereksinim 6: Konuşma hafızası (AgentCore Memory)
**Kullanıcı hikayesi:** Bir kurye olarak, dün söylediğimi bugün yeniden anlatmak istemiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL şablonun tanımladığı `agentMemory` hafızasını (SEMANTIC + EPISODIC) korumalı, ikinci bir hafıza açmamalıdır.
2. WHEN `MEMORY_AGENTMEMORY_ID` ortamda varsa THE SYSTEM SHALL oturum yöneticisini isteğin `actorId` ve oturum kimliğiyle kurmalıdır; olgular `/users/{actorId}/facts` ad alanından en çok 5 kayıtla geri çağrılır.
3. IF `MEMORY_AGENTMEMORY_ID` yoksa (yerel deneme) THEN THE SYSTEM SHALL hafızasız çalışmalı ve hata vermemelidir.
4. THE SYSTEM SHALL bir kuryenin konuşma olgularını başka kuryeye getirmemelidir (ad alanı `actorId` ile ayrılır).

### Gereksinim 7: Model
**Kullanıcı hikayesi:** Bir geliştirici olarak, dağıtılmış ajanın model hatasıyla düşmemesini istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL çıkarım profili biçiminde bir model kimliği kullanmalıdır (`global.` ya da bölge önekli).
2. IF öneksiz bir kimlik verilirse THEN THE SYSTEM SHALL açık bir hata vermelidir.
3. THE SYSTEM SHALL şablonun `model/load.py` yükleyicisini kullanmalı; o yoksa `CM_AGENT_MODEL_ID` ortam değişkenine düşmelidir.

### Gereksinim 8: Tekrarlanabilir kurulum ve doğrulama
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, dağıtımı el yordamıyla değil tek betikle yapmak istiyorum.

#### Kabul kriterleri
1. WHEN `deploy/agentcore/bootstrap.sh` çalıştırıldığında THE SYSTEM SHALL iskele yoksa `agentcore create` ile kurmalı, çalışma kodunu ve veriyi `app/agent/` içine kopyalamalı, bağımlılıkları ve `envVars` girdisini yazmalı ve şablonun `main.py` dosyasını yedeklemelidir.
2. THE SYSTEM SHALL betiği tekrar çalıştırmayı güvenli kılmalıdır (aynı sonuç, yinelenen girdi yok).
3. WHEN `deploy/agentcore/verify.sh` çalıştırıldığında THE SYSTEM SHALL yukarıdaki şartları dağıtımdan önce denetlemeli; `--deployed` ile dağıtımın üç kontrolünü (durum, araç çağrısı, log grubu ve izler) yürütmelidir.
4. THE SYSTEM SHALL araçları, kimlik sınırını ve giriş noktasını Bedrock'a gitmeden sınayan testler taşımalıdır (betikli sahte model).

### Gereksinim 9 (sonraki adım): Kalıcı adres hafızası, AgentCore Gateway üzerinden
**Kullanıcı hikayesi:** Bir kurye olarak, bıraktığım notu yarın başka bir oturumda başka bir kuryenin duymasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL adres hafızası kayıtlarını bir DynamoDB tablosunda tutan Lambda işlevini, MCP protokollü bir AgentCore Gateway'e `lambdaFunctionArn` hedefi olarak bağlamalıdır (gateway adı ≤ 12 karakter).
2. WHEN ajan not yazdığında ya da kart okuduğunda THE SYSTEM SHALL Gateway'in MCP araçlarını kullanmalı; ajan Gateway adresini CDK'nın verdiği ortam değişkeninden okur ve MCP istemcisini tembel açar.
3. THE SYSTEM SHALL Gateway araçlarını da Gereksinim 5'in kimlik sınırına bağlamalıdır.

### Gereksinim 10 (sonraki adım): Sohbet arayüzü, Amazon ECS Fargate üzerinde
**Kullanıcı hikayesi:** Bir şube müdürü olarak, ajanla tarayıcıdan konuşmak istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL Amazon ECS Fargate üzerinde çalışan bir sohbet arayüzü sunmalıdır: port 8888, `/health`, `AGENTCORE_ENDPOINT` ve `AWS_REGION`, akışlı gösterim, göreli yollar.
2. WHEN arayüzde kimlik seçildiğinde THE SYSTEM SHALL isteği o `actorId` ile göndermelidir (kurye ↔ müdür farkı görünür olur).

### Gereksinim 11: Çekirdek araç takımı (alan kodu olmadan çalışır)
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, alan kodu çalışma ortamında yüklenemediğinde de ajanın yayında kalmasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL iki araç takımı sunmalıdır: tam (`agents.Services`, 9 araç) ve çekirdek (yalnız `data/demo_run` dosyaları ve standart kütüphane, 6 araç: `courier_briefing`, `stop_cards`, `approaching_stop`, `leave_note`, `branch_memory_summary`, `real_day_evidence`).
2. WHEN `CM_TOOLSET` `auto` (varsayılan) iken alan kodu yüklenemezse THE SYSTEM SHALL nedenini loglamalı ve çekirdek takımla çalışmalıdır; ajan çökmez.
3. WHEN çekirdek takımda bir müdür aracı çağrıldığında THE SYSTEM SHALL aracın bu dağıtımda kapalı olduğunu açıklayan bir hata sonucu döndürmelidir.
4. THE SYSTEM SHALL çekirdek takımda da aynı kuralları uygulamalıdır: kişisel veri ve kapı şifresi yazılmaz, bilgi türleri için notun temizlenmiş hali yazılır, bir tetikte en çok iki kart, söylenmiş kart tekrar söylenmez, bugüne uymayan kart (Çarşamba günü "Cumartesi kapalı") gösterilmez.
5. THE SYSTEM SHALL çekirdek sınıflandırıcının simülatörün bütün notlarında alan kodundaki sınıflandırıcıyla aynı sonucu verdiğini testle göstermelidir.
6. THE SYSTEM SHALL demo gününde iki takımda aynı sayıları vermelidir: O02 için 45 durak, 16 kartlı durak; şubede 2.295 aktif kayıt.
7. THE SYSTEM SHALL kimlik sınırını (Gereksinim 5) iki takımda da aynı kancayla zorlamalıdır.

### Gereksinim 12: Projenin MCP sunucusu (geliştirme aracı)
**Kullanıcı hikayesi:** Kiro ile çalışan bir geliştirici olarak, spec yazarken şubenin verisine kod okumadan bakmak istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL stdio üzerinden çalışan bir MCP sunucusu sunmalıdır (`deploy/mcp/cm_mcp_server.py`): `branch_memory_summary`, `address_memory`, `courier_stop_cards`, `real_day_evidence`, `demo_context`.
2. THE SYSTEM SHALL bu sunucuda yazma aracı açmamalıdır; not ve müdür kararı yalnız kimlik sınırı olan yollardan geçer.
3. THE SYSTEM SHALL sunucuyu çalışma alanının `.kiro/settings/mcp.json` dosyasında tanımlamalı ve kullanıcı düzeyi MCP sunucularına dokunmamalıdır.


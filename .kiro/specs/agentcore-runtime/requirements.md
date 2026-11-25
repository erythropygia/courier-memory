# Gereksinimler: AgentCore Runtime'da Courier Memory ajanı

## Giriş

Courier Memory'nin alan mantığı (hafıza, kart, rota, plan, öz-değerlendirme) bugün yerel bir FastAPI sürecinde çalışıyor. Bu spec onu **Amazon Bedrock AgentCore Runtime**'a taşır: Strands ajanları alan fonksiyonlarını araç olarak çağırır, kimlik sınırını kodda zorlar, konuşmayı AgentCore Memory'de hatırlar ve izlerini CloudWatch'a yollar.

Varsayılan yapı çok ajanlıdır: kullanıcı tek bir **Supervisor** ajanıyla konuşur; Supervisor işi dört uzmana (Planlama, Kurye, Hafıza, Analiz) yönlendirir ve cevabı birleştirir. Beşi de aynı kod paketidir, rolü `CM_AGENT_ROLE` seçer. Analiz Ajanı'nın verisi ve aracı ayrı spec'tedir (`athena-analiz`); Amazon Quick'ten gelen sorular Supervisor'a `quick-koprusu` spec'indeki köprüyle ulaşır.

**Brif**

| Girdi | Değer |
|---|---|
| Kullanım alanı | Kuryelerin yazılı olmayan adres bilgisini şubenin ortak hafızasına taşıyan ve bölgeyi bilmeyen kuryeye doğru anda veren asistan. **Asla** kişisel veri ya da kapı şifresi kaydetmez ve söylemez; kuryeyi puanlamaz; planı müdür onayı olmadan uygulamaz |
| Kullanıcı | Kurye (telefonda, sürüş sırasında kısa cevap) ve şube müdürü (sabah planı, değerlendirme, bölge raporu, geçmiş veri analizi) |
| Bilgi kaynağı | Şubenin adres hafızası ve teslim kayıtları (`data/demo_run`, uygulama verisi, 1 aylık geçmiş) + gerçek 5 Mayıs günü (`data/real_day`) + aynı geçmişin Athena kopyası (`athena-analiz`). Belge tabanlı Knowledge Base gerekmez: cevaplar araçlardan gelir |
| Ajanlar | `agent` (Supervisor) + `planner` (Planlama Ajanı), `courier` (Kurye Ajanı), `memory_keeper` (Hafıza Ajanı), `analyst` (Analiz Ajanı); `CM_MULTI_AGENT=0` ile tek runtime |
| Araçlar | On alan aracı (Strands `@tool`): `courier_briefing`, `stop_cards`, `approaching_stop`, `leave_note`, `plan_day`, `morning_review`, `region_report`, `harvest_questions`, `branch_memory_summary`, `real_day_evidence`. Analiz Ajanı'nda `query_history`; Supervisor'da dört yönlendirme aracı (`ask_planner`, `ask_courier_agent`, `ask_memory_keeper`, `ask_analyst`) |
| Çatı | Strands, şablon `agent-python-strands` |

Çerçeve kuralları `.kiro/steering/agentcore.md` dosyasındadır.

## Gereksinimler

### Gereksinim 1: Dağıtım
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, ajanın yönetilen bir çalışma ortamında yayında olmasını istiyorum; böylece demo bir dizüstüne bağlı kalmaz.

#### Kabul kriterleri
1. THE SYSTEM SHALL `$CM_WORKSPACE` içinde (varsayılan: reponun üst klasörü, yani `../CourierMemory`) `agentcore create --name CourierMemory --template agent-python-strands` ile kurulmuş bir projede yaşamalıdır; klasör yapısı elle kurulmaz.
2. WHEN `agentcore deploy` çalıştırıldığında THE SYSTEM SHALL AgentCore Runtime'a dağıtılmalı ve `agentcore status` çalışma ortamlarını ARN'leriyle dağıtılmış göstermelidir.
3. THE SYSTEM SHALL çalışma zamanı bağımlılıklarını yalnız `app/agent/pyproject.toml` → `[project].dependencies` içinde tutmalıdır (numpy, scipy, pydantic, pyyaml); test araçları oraya girmez.

### Gereksinim 2: Gözlemlenebilirlik
**Kullanıcı hikayesi:** Bir geliştirici olarak, ajanın hangi aracı ne kadar sürede çağırdığını izlerden görmek istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL `agentcore/agentcore.json` içinde her çalışma ortamının `envVars` listesinde `UNIFIED_TRACES_DESTINATION_ENABLED` girdisini `true` değeriyle taşımalıdır.
2. WHEN dağıtılmış ajan bir kez çağrıldığında THE SYSTEM SHALL `/aws/bedrock-agentcore/runtimes/<agent-id>-DEFAULT` log grubunu oluşturmuş ve `agentcore traces runtime list --since 15m` o çağrının izini listelemiş olmalıdır.
3. THE SYSTEM SHALL her ajan izine `cm.agent_role`, `cm.actor_role`, `cm.actor_id` ve `cm.toolset` özniteliklerini eklemelidir (hangi runtime'ın, kimin adına, hangi araç takımıyla çalıştığı izde görünür).

### Gereksinim 3: Araçlar
**Kullanıcı hikayesi:** Bir kurye ya da müdür olarak, ajanın tahmin etmesini değil şubenin verisine bakmasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL en az bir aracı Strands `@tool` olarak açmalıdır; bu spec on alan aracı ve Supervisor'ın dört yönlendirme aracını tanımlar (brif tablosu); `query_history` `athena-analiz` spec'indedir.
2. WHEN bir alan aracı çağrıldığında THE SYSTEM SHALL sayıları ve adres bilgisini `agents.Services` içindeki deterministik fonksiyonlardan almalı ve JSON metni döndürmelidir; model hesap yapmaz.
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
2. WHEN kurye ya da konuk kimliğiyle gelen istekte ajan bir müdür aracı (`plan_day`, `morning_review`, `region_report`, `harvest_questions`, `query_history`, `ask_planner`, `ask_analyst`) çağırdığında THE SYSTEM SHALL çağrıyı iptal etmelidir.
3. WHEN kimliksiz (konuk) istekte ajan bir kurye aracı ya da `ask_courier_agent` çağırdığında THE SYSTEM SHALL çağrıyı iptal etmeli; herkese açık araçlar (`branch_memory_summary`, `real_day_evidence`) çalışmalıdır.
4. WHEN bir çağrı reddedildiğinde THE SYSTEM SHALL konuşmayı sürdürmeli ve aynı oturumda çağıranın kendi verisi erişilebilir kalmalıdır.
5. THE SYSTEM SHALL sınırı kodda (`BeforeToolCallEvent` kancası) zorlamalıdır; sistem istemi kimliği ayrıca söyler ama tek savunma değildir.
6. THE SYSTEM SHALL reddedilen çağrının sonucunda başka kuryeye ait hiçbir veri taşımamalıdır.

### Gereksinim 6: Konuşma hafızası (AgentCore Memory)
**Kullanıcı hikayesi:** Bir kurye olarak, dün söylediğimi bugün yeniden anlatmak istemiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL şablonun tanımladığı `agentMemory` hafızasını (SEMANTIC + EPISODIC) korumalı, ikinci bir hafıza açmamalıdır; hafıza projedeki her runtime'a bağlanır.
2. WHEN `MEMORY_AGENTMEMORY_ID` ortamda varsa THE SYSTEM SHALL oturum yöneticisini isteğin `actorId` ve oturum kimliğiyle kurmalıdır; olgular `/users/{actorId}/facts` ad alanından en çok 5 kayıtla geri çağrılır.
3. IF `MEMORY_AGENTMEMORY_ID` yoksa (yerel deneme) THEN THE SYSTEM SHALL hafızasız çalışmalı ve hata vermemelidir.
4. THE SYSTEM SHALL bir kuryenin konuşma olgularını başka kuryeye getirmemelidir (ad alanı `actorId` ile ayrılır).

### Gereksinim 7: Model
**Kullanıcı hikayesi:** Bir geliştirici olarak, dağıtılmış ajanın model hatasıyla düşmemesini ve demonun krediyi gereksiz tüketmemesini istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL çıkarım profili biçiminde bir model kimliği kullanmalıdır (`global.` ya da bölge önekli).
2. IF öneksiz bir kimlik verilirse THEN THE SYSTEM SHALL açık bir hata vermelidir.
3. THE SYSTEM SHALL şablonun `model/load.py` yükleyicisini kullanmalı; o yoksa `CM_AGENT_MODEL_ID` ortam değişkenine düşmelidir.
4. THE SYSTEM SHALL test ve demoda hesapta izinli bir Sonnet ya da Haiku çıkarım profili kullanmalıdır (bugün `global.anthropic.claude-sonnet-5`); Opus kullanılmaz.
5. THE SYSTEM SHALL Supervisor'a verilen `CM_AGENT_MODEL_ID` değerini uzman runtime'lara da taşımalıdır (beşi aynı modelle çalışır).
6. WHEN `bootstrap.sh` `CM_AGENT_MODEL_ID` ile çalıştırıldığında THE SYSTEM SHALL şablonun `model/load.py` dosyasındaki model kimliğini bu değerle yazmalıdır (şablon hesabın izin listesinde olmayan bir model yazabilir); değer çıkarım profili biçiminde değilse betik durur.

### Gereksinim 8: Tekrarlanabilir kurulum ve doğrulama
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, dağıtımı el yordamıyla değil tek betikle yapmak istiyorum.

#### Kabul kriterleri
1. WHEN `deploy/agentcore/bootstrap.sh` çalıştırıldığında THE SYSTEM SHALL iskele yoksa `agentcore create` ile kurmalı, çalışma kodunu ve veriyi `app/agent/` içine kopyalamalı, bağımlılıkları yazmalı, `agentcore_config.py` ile çalışma ortamlarını, `envVars` girdilerini ve politikaları (Gereksinim 13, 15) kurmalı ve şablonun `main.py` dosyasını yedeklemelidir.
2. THE SYSTEM SHALL betiği tekrar çalıştırmayı güvenli kılmalıdır (aynı sonuç, yinelenen girdi yok).
3. WHEN `deploy/agentcore/verify.sh` çalıştırıldığında THE SYSTEM SHALL yukarıdaki şartları dağıtımdan önce denetlemeli; `--deployed` ile dağıtımın üç kontrolünü (durum, araç çağrısı, log grubu ve izler) yürütmelidir.
4. THE SYSTEM SHALL araçları, kimlik sınırını, giriş noktasını ve uzman çağrısını Bedrock'a ve AWS'ye gitmeden sınayan testler taşımalıdır (betikli sahte model, sahte istemci).

### Gereksinim 9 (sonraki adım): Kalıcı adres hafızası, AgentCore Gateway üzerinden
**Kullanıcı hikayesi:** Bir kurye olarak, bıraktığım notu yarın başka bir oturumda başka bir kuryenin duymasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL adres hafızası kayıtlarını bir DynamoDB tablosunda tutan Lambda işlevini, MCP protokollü bir AgentCore Gateway'e `lambdaFunctionArn` hedefi olarak bağlamalıdır (gateway adı ≤ 12 karakter).
2. WHEN ajan not yazdığında ya da kart okuduğunda THE SYSTEM SHALL Gateway'in MCP araçlarını kullanmalı; ajan Gateway adresini CDK'nın verdiği ortam değişkeninden okur ve MCP istemcisini tembel açar.
3. THE SYSTEM SHALL Gateway araçlarını da Gereksinim 5'in kimlik sınırına bağlamalıdır.

### Gereksinim 10 (sonraki adım): Sohbet arayüzü, Amazon ECS Fargate üzerinde
**Kullanıcı hikayesi:** Bir şube müdürü olarak, ajanla tarayıcıdan konuşmak istiyorum.

Müdürün sohbet ihtiyacı bugün Amazon Quick köprüsüyle karşılanır (`quick-koprusu`; sabit müdür kimliği). Bu gereksinim kimlik seçicili kendi arayüzümüz için açık kalır.

#### Kabul kriterleri
1. THE SYSTEM SHALL Amazon ECS Fargate üzerinde çalışan bir sohbet arayüzü sunmalıdır: port 8888, `/health`, `AGENTCORE_ENDPOINT` ve `AWS_REGION`, akışlı gösterim, göreli yollar.
2. WHEN arayüzde kimlik seçildiğinde THE SYSTEM SHALL isteği o `actorId` ile göndermelidir (kurye ↔ müdür farkı görünür olur).

### Gereksinim 11: Çekirdek araç takımı (alan kodu olmadan çalışır)
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, alan kodu çalışma ortamında yüklenemediğinde de ajanın yayında kalmasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL iki araç takımı sunmalıdır: tam (`agents.Services`, 10 araç) ve çekirdek (yalnız `data/demo_run` dosyaları ve standart kütüphane, 6 araç: `courier_briefing`, `stop_cards`, `approaching_stop`, `leave_note`, `branch_memory_summary`, `real_day_evidence`).
2. WHEN `CM_TOOLSET` `auto` (varsayılan) iken alan kodu yüklenemezse THE SYSTEM SHALL nedenini loglamalı ve çekirdek takımla çalışmalıdır; ajan çökmez.
3. WHEN çekirdek takımda bir müdür aracı (`harvest_questions` dahil) çağrıldığında THE SYSTEM SHALL aracın bu dağıtımda kapalı olduğunu açıklayan bir hata sonucu döndürmelidir.
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

### Gereksinim 13: Çok ajanlı yapı (Supervisor + dört uzman)
**Kullanıcı hikayesi:** Bir geliştirici olarak, her ajanın yalnız kendi işinin araçlarını görmesini istiyorum; böylece istem kısa kalır, araç seçimi şaşmaz ve her uzman izde ayrı görünür.

#### Kabul kriterleri
1. THE SYSTEM SHALL aynı kod paketinden beş çalışma ortamı kurmalıdır; rolü `CM_AGENT_ROLE` seçer: `agent` (`supervisor`), `planner`, `courier`, `memory_keeper`, `analyst`.
2. THE SYSTEM SHALL alan araçlarını uzmanlar arasında çakışmasız bölmelidir: `planner` → `plan_day`, `morning_review`, `region_report`; `courier` → `courier_briefing`, `stop_cards`, `approaching_stop`; `memory_keeper` → `leave_note`, `branch_memory_summary`, `real_day_evidence`, `harvest_questions`; `analyst` → `query_history`.
3. THE SYSTEM SHALL Supervisor'a alan aracı vermemelidir; Supervisor yalnız `ask_planner`, `ask_courier_agent`, `ask_memory_keeper`, `ask_analyst` ile uzmanı `InvokeAgentRuntime` üzerinden çağırır ve cevapları birleştirir.
4. WHEN Supervisor bir uzmanı ilk kez çağırdığında THE SYSTEM SHALL uzmanın ARN'sini `CM_RUNTIME_PREFIX` (`<Proje>_<hedef>_`) + rol adıyla `ListAgentRuntimes` sonucundan bulmalı ve önbelleğe almalıdır; `CM_<ROL>_RUNTIME_ARN` verilirse arama yapılmaz.
5. IF `CM_RUNTIME_PREFIX` tanımlı değilse ya da aynı adla birden fazla runtime varsa THEN THE SYSTEM SHALL uzmanı seçmemeli ve nedenini söyleyen bir hata vermelidir.
6. IF uzmana ulaşılamazsa ya da uzman akışa `error` yazarsa THEN THE SYSTEM SHALL bunu Supervisor'a AWS ayrıntısı içermeyen bir araç sonucu olarak vermeli, o rolün ARN önbelleğini silmeli ve çağrıyı yeniden denememelidir (`leave_note` yazma işlemidir, not iki kez bırakılmaz).
7. THE SYSTEM SHALL her uzmana kendi oturumunu açmalıdır (`<oturum>-<rol>`, en az 33 karakter); uzmanların konuşma geçmişi birbirine karışmaz.
8. THE SYSTEM SHALL her uzmanın sistem istemini yalnız kendi adını ve araçlarını anlatacak biçimde kurmalıdır; soru başka bir alana aitse uzman bunu kısaca söyler.
9. WHEN kurulum `CM_MULTI_AGENT=0` ile yapıldığında THE SYSTEM SHALL tek çalışma ortamı (`agent`, on alan aracı, Athena yok) kurmalı; uzman runtime'larını ve politika dosyalarını kaldırmalıdır.

### Gereksinim 14: Kimlik uzmana değişmeden gider
**Kullanıcı hikayesi:** Bir kurye olarak, Supervisor üzerinden sorduğumda da yalnız kendi verimi görmek istiyorum; model başka bir kimlik yazarak sınırı aşamamalı.

#### Kabul kriterleri
1. THE SYSTEM SHALL Supervisor'ın yönlendirme araçlarında kimliği ve oturumu kapanışta tutmalıdır; modelin gördüğü şemada yalnız `question` ve `day` vardır.
2. WHEN Supervisor bir uzmanı çağırdığında THE SYSTEM SHALL uzmana isteğin `actorId`'sini göndermelidir; model soruya başka bir kimlik yazsa da gönderilen kimlik değişmez.
3. THE SYSTEM SHALL kimlik sınırını (Gereksinim 5) her uzmanda yeniden uygulamalıdır; Supervisor'daki denetim tek savunma değildir.
4. WHEN kurye ya da konuk `ask_planner` ya da `ask_analyst` çağırdığında THE SYSTEM SHALL çağrıyı Supervisor'da, uzman runtime'ı ve modeli çağrılmadan reddetmelidir (erken ret: boşa model çağrısı yok).
5. WHEN konuk `ask_courier_agent` çağırdığında THE SYSTEM SHALL çağrıyı reddetmelidir; `ask_memory_keeper` herkese açıktır ve Hafıza Ajanı kendi araç sınırını uygular.

### Gereksinim 15: En az yetki
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, her runtime'ın yalnız işinin gerektirdiği AWS iznini taşımasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL Supervisor'ın rolüne yalnız bu proje ve hedefin runtime'larını çağırma iznini (`bedrock-agentcore:InvokeAgentRuntime`, kaynak `runtime/<Proje>_<hedef>_*`) ve `bedrock-agentcore:ListAgentRuntimes` iznini (kaynak düzeyinde kısıtlanamaz) vermelidir (`agentcore/supervisor-policy.json`).
2. THE SYSTEM SHALL Analiz Ajanı'na yalnız salt okunur Athena politikasını vermelidir (`agentcore/analyst-policy.json`, ayrıntı `athena-analiz`); Planlama, Kurye ve Hafıza Ajanı ek AWS izni almaz.
3. THE SYSTEM SHALL izinleri `agentcore.json` → `additionalPolicies` ile vermelidir; IAM rolü elle düzenlenmez.
4. THE SYSTEM SHALL `agentcore_config.py` dönüşümünü saf ve tekrar çalıştırmaya güvenli tutmalıdır: kullanıcının eklediği `envVars` ve politikalar korunur, yönetilen girdiler yinelenmez.

### Gereksinim 16: Hafıza hasadı aracı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, hafızası boş ya da tekrar tekrar başarısız olan adresler için bölgeyi bilen kuryelere hangi soruların sorulacağını ajana sormak istiyorum.

#### Kabul kriterleri
1. WHEN `harvest_questions` tam takımda çağrıldığında THE SYSTEM SHALL Hasat Ajanı'nın planını (`agents/harvest.py`, kurallı yol) döndürmelidir: gün, özet, plan kaynağı, `degraded` ve en çok 15 soru (kurye, adres, neden, soru, durum).
2. THE SYSTEM SHALL aracı müdür aracı saymalıdır (`MANAGER_TOOLS`); kurye ve konuk çağrısı iptal edilir.
3. WHEN araç çekirdek takımda çağrıldığında THE SYSTEM SHALL aracın bu dağıtımda kapalı olduğunu açıklayan bir hata sonucu döndürmelidir.
4. THE SYSTEM SHALL aracı çok ajanlı yapıda Hafıza Ajanı'na, tek runtime'da on alan aracının arasına koymalıdır.
5. THE SYSTEM SHALL bu araçla adres hafızasına kayıt yazmamalıdır; araç soruları üretir, cevaplar mevcut hasat akışından ve Hafıza Ajanı'ndan geçer (`ajanlar` Gereksinim 5).

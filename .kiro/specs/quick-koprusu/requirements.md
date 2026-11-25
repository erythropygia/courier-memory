# Gereksinimler: Amazon Quick köprüsü

## Giriş

Şube müdürü Courier Memory'ye bugün `agentcore invoke` ile ya da yerel arayüzlerden ulaşabiliyor. Bu spec, **Amazon Quick**'teki bir chat ajanından Supervisor'a canlı soru sormayı sağlar: Quick bir MCP aracı çağırır, **AgentCore Gateway** çağrıyı bir Lambda'ya iletir, Lambda soruyu Supervisor runtime'ına (`agent`) gönderir ve metin cevabı döndürür. Supervisor işi uzman ajanlara dağıtır (`agentcore-runtime` Gereksinim 13).

```
Quick chat ajanı ──(MCP, OAuth client credentials)──► AgentCore Gateway ──► Lambda (bridge_lambda.py)
                                                                              └─► Supervisor (agent) ──► uzmanlar
```

Kimlik Quick'ten ya da modelden gelmez: her soru Lambda ortamındaki sabit müdür kimliğiyle (`MUDUR-QUICK`) gider.

## Gereksinimler

### Gereksinim 1: MCP aracı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, Quick'teki sohbetten şubenin planını, hafızasını ve geçmiş verisini sormak istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL Gateway üzerinde tek bir MCP aracı açmalıdır: `ask_courier_memory {question (zorunlu, metin), day (isteğe bağlı, tamsayı)}`.
2. THE SYSTEM SHALL aracın açıklamasında Supervisor'ın neleri cevaplayabildiğini söylemelidir (gün planı ve kapasite, sabah değerlendirmesi, bölge raporu, kurye brifingi ve durak kartları, adres hafızası ve hasat soruları, geçmiş veriden SQL analizi); açıklama Türkçe ve İngilizce cümle taşır.
3. WHEN araç çağrıldığında THE SYSTEM SHALL Supervisor'ın metin cevabını `{"answer": …}` olarak döndürmelidir; Supervisor boş yanıt verirse bunu açıkça söyler.

### Gereksinim 2: Gateway kimlik doğrulaması
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, Gateway'i yalnız bizim Quick bağlantımızın çağırabilmesini istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL Gateway'i MCP protokolüyle ve `CUSTOM_JWT` doğrulayıcıyla kurmalıdır; izinli istemci yalnız köprünün Cognito istemcisidir.
2. THE SYSTEM SHALL bir Cognito user pool (`courier-memory-quick`), alan adı, kaynak sunucusu ve kapsamı (`courier-memory/invoke`) kurmalıdır.
3. THE SYSTEM SHALL makineler arası bir istemci (`quick`) kurmalıdır: gizli anahtarlı, yalnız `client_credentials` akışı, yalnız `courier-memory/invoke` kapsamı, erişim jetonu 60 dk.

### Gereksinim 3: Sabit kimlik
**Kullanıcı hikayesi:** Bir kurye olarak, Quick üzerinden gelen bir sorunun benim kimliğime bürünüp verimi açamamasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL Supervisor'a giden `actorId`'yi yalnız Lambda ortamından (`QUICK_ACTOR_ID`, varsayılan `MUDUR-QUICK`) almalıdır; olaydaki hiçbir alan kimliği değiştiremez.
2. THE SYSTEM SHALL bu kimliği müdür saymalıdır (`MUDUR` öneki); kimlik sınırı Supervisor'da ve uzmanlarda olduğu gibi uygulanır.
3. THE SYSTEM SHALL kurye bazında yetkinin bu köprüyle verilmediğini belgelemelidir; gerekirse Quick'te kullanıcı girişli OAuth ve Lambda'da jetondan kimlik eşlemesi ayrı bir iştir.

### Gereksinim 4: Köprü Lambda'sı
**Kullanıcı hikayesi:** Bir geliştirici olarak, köprünün geçersiz çağrıyı Supervisor'a taşımamasını ve hatayı güvenli bildirmesini istiyorum.

#### Kabul kriterleri
1. IF Gateway'in bildirdiği araç adı (`bedrockAgentCoreToolName`, `___` sonrası) `ask_courier_memory` değilse THEN THE SYSTEM SHALL çağrıyı reddetmelidir.
2. IF soru boşsa ya da 2.000 karakteri aşıyorsa THEN THE SYSTEM SHALL Supervisor'ı çağırmadan hata dönmelidir.
3. WHEN geçerli bir soru geldiğinde THE SYSTEM SHALL Supervisor'ı `InvokeAgentRuntime` ile `{"prompt", "actorId", "day"?}` gövdesi ve her soru için yeni bir oturumla (`quick-<uuid>`) çağırmalıdır.
4. THE SYSTEM SHALL Supervisor akışından (`data: {...}`) metni toplamalı, mesajları satırla ayırmalı ve akışı her durumda kapatmalıdır.
5. IF Supervisor akışa `error` yazarsa THEN THE SYSTEM SHALL "Ajan yanıt veremedi" hatasını dönmelidir.
6. IF AWS çağrısı başarısız olursa THEN THE SYSTEM SHALL ayrıntıyı log'a yazmalı, Quick'e yalnız hata kodunu içeren kısa bir metin dönmelidir.
7. THE SYSTEM SHALL çağrıyı yeniden denememelidir (Supervisor üzerinden not bırakma yazma işlemidir) ve okuma süresini 270 sn ile sınırlamalıdır (Quick her MCP çağrısında 300 sn bekler).

### Gereksinim 5: En az yetki
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, köprünün her parçasının yalnız bir sonraki parçayı çağırabilmesini istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL Lambda rolüne (`courier-memory-quick-lambda`) yalnız Supervisor runtime'ını ve uç noktalarını çağırma iznini ve temel Lambda log iznini vermelidir.
2. THE SYSTEM SHALL Gateway rolüne (`courier-memory-quick-gateway`) yalnız köprü Lambda'sını çağırma iznini vermelidir; rolün güven ilişkisi `bedrock-agentcore.amazonaws.com` ile ve `aws:SourceAccount` koşuluyla sınırlıdır.
3. THE SYSTEM SHALL Gateway hedefine Lambda'yı Gateway'in IAM rolüyle (`GATEWAY_IAM_ROLE`) bağlamalıdır.

### Gereksinim 6: Kurulum betiği
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, köprüyü tek komutla kurmak ve uçtan uca denemek istiyorum.

#### Kabul kriterleri
1. WHEN `deploy/quick/quick_bridge_setup.py` çalıştırıldığında THE SYSTEM SHALL Supervisor runtime'ını adıyla bulmalıdır (varsayılan `CourierMemory_default_agent`, `--runtime-name` ile değişir); bulamazsa önce `agentcore deploy` gerektiğini söyleyip durmalıdır.
2. THE SYSTEM SHALL sırasıyla Lambda rolünü, Lambda'yı (`courier-memory-quick-bridge`, Python 3.13, 280 sn, 256 MB), Cognito'yu, Gateway rolünü, Gateway'i (`courier-memory-quick`) ve hedefi kurmalı ya da güncellemeli; her kaynağın hazır olmasını beklemelidir.
3. THE SYSTEM SHALL betiği tekrar çalıştırmayı güvenli kılmalıdır (aynı adlı kaynak güncellenir, yinelenmez).
4. THE SYSTEM SHALL Quick'e girilecek değerleri (MCP adresi, Client ID, Client Secret, Token URL, kapsam) yalnız `~/.courier-memory/quick-bridge.json` dosyasına yazmalıdır; gizli anahtar repoya ve konsola yazılmaz.
5. WHEN `--test` verildiğinde THE SYSTEM SHALL jeton almalı, `tools/list` ve bir `tools/call` çağrısını uçtan uca yapıp sonucu yazdırmalıdır.

### Gereksinim 7: Quick tarafı ve sınırlar
**Kullanıcı hikayesi:** Bir şube müdürü olarak, Quick'te bağlantıyı belgeden adım adım kurabilmek istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL Quick'te bağlantının nasıl kurulduğunu `deploy/quick/README.md`'de anlatmalıdır: MCP connector, genel ağ, servisler arası OAuth, chat ajanına Actions olarak bağlama.
2. THE SYSTEM SHALL Quick açıklama alanının yalnız harf, rakam, boşluk ve `. , ! ? - _` kabul ettiğini (Türkçe karakter yok) belgelemelidir.
3. THE SYSTEM SHALL her sorunun yeni bir oturum olduğunu belgelemelidir; konuşma bağlamını Quick'in kendi sohbeti taşır.

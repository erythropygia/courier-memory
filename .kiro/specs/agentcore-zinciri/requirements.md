# Gereksinimler: AgentCore zinciri (sunum ekranında dağıtılmış Supervisor)

## Giriş

Canlı akışın ikinci zinciri: aynı demo dağıtılmış AgentCore Supervisor'dan (`CourierMemory_default_agent`, us-east-1) geçer ve sunucu bütün ajanları tek sıralı akışta gösterir: Supervisor → uzman (Planlama, Kurye, Hafıza, Analiz) → alan aracı → sonuç. Altı istek iki kimlikle (müdür `MUDUR-01`, kurye `O02`) gönderilir; sonuncusu kimlik sınırında reddedilir. İç alan ajanları kurallı kalır. Yayın, SSE ve izleyici kuralları canlı akışla aynıdır (`.kiro/specs/canli-akis/`).

## Gereksinimler

### Gereksinim 1: Zincir ve sıra
#### Kabul kriterleri
1. WHEN sunum ekranında "AgentCore zinciri"ne basıldığında THE SYSTEM SHALL altı isteği sırayla, her birini kendi kimliğiyle Supervisor'a göndermelidir (plan → brifing → not → hasat soruları → Athena analizi → ret).
2. WHILE herhangi bir zincir koşarken THE SYSTEM SHALL yeni başlatmayı reddetmelidir (409).
3. THE SYSTEM SHALL olayları canlı akışın yayınıyla (aynı SSE, Last-Event-ID, keep-alive) bütün izleyicilere aynı sırayla iletmelidir.
4. THE SYSTEM SHALL oturum kimliğini koşu + kimlik başına üretmeli (≥ 33 karakter) ve çağrıyı yeniden denememelidir.

### Gereksinim 2: Atlamaların izi
#### Kabul kriterleri
1. WHEN akışta `cm_trace` geldiğinde THE SYSTEM SHALL onu ajan izi olayına çevirip ajanı (`agent`) ve üstünü (`parent`) taşımalıdır.
2. THE SYSTEM SHALL `parent: supervisor` olan atlamayı girintili, reddedileni (`denied`) ayrı biçimde göstermelidir; her atlamada araç adı, girdi, özet ve süre görünür.
3. IF akışta hiç `cm_trace` yoksa (eski dağıtım) THEN THE SYSTEM SHALL Supervisor'ın araç çağrılarını model olaylarından ve son metni göstermelidir; `cm_trace` varken bunları yinelememelidir.

### Gereksinim 3: Hatalar
#### Kabul kriterleri
1. IF AWS kimliği yoksa, izin yoksa (AccessDenied), runtime bulunamazsa ya da bağlantı kurulamazsa THEN THE SYSTEM SHALL adımı Türkçe, anlaşılır bir mesajla başarısız göstermeli ve zinciri durdurmalıdır.
2. IF zaman aşımı, istek sınırı ya da akışta hata olursa THEN THE SYSTEM SHALL yalnız o adımı başarısız göstermeli, zincir sürmelidir.
3. THE SYSTEM SHALL izleyiciye ARN, hesap numarası ya da ham istisna metni göndermemelidir.

### Gereksinim 4: Açma/kapama ve izin
#### Kabul kriterleri
1. WHEN `CM_AGENTCORE_CHAIN=0` olduğunda THE SYSTEM SHALL başlatmayı 501 ile reddetmeli ve sunum ekranında düğmeyi göstermemelidir.
2. THE SYSTEM SHALL web görev rolüne yalnız Supervisor runtime'ı için `InvokeAgentRuntime` ve adla bulmak için `ListAgentRuntimes` vermelidir.

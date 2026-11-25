# Gereksinimler: Athena analizi ve Analiz Ajanı

## Giriş

Şube müdürü "son iki haftada hangi gün en çok başarısız teslim oldu?", "alıcı evde yok nedeni hafızalı yapıda ne kadar düştü?" gibi soruları bugün ancak simülasyon çıktısını okuyarak cevaplayabiliyor. Bu spec simülasyonun 40 günlük geçmişini (uygulama verisi) **Amazon Athena**'ya salt okunur tablolar olarak koyar ve AgentCore'daki **Analiz Ajanı**'na (`analyst` runtime'ı) bu tablolara tek bir `SELECT` çalıştıran bir araç verir.

İlke (`tech.md`): **LLM karar verir, hesap araçta.** Model soruyu SQL'e çevirir ve sonucu anlatır; sayıyı Athena hesaplar. Araç yalnız okuma yapar; sınır üç katmanlıdır: araçtaki SQL denetimi, çalışma grubunun tarama sınırı ve runtime rolünün salt okunur izni.

Çok ajanlı yapı, Supervisor ve kimlik sınırı `agentcore-runtime` spec'indedir (Gereksinim 13–15). Veri kuralları: `.kiro/steering/veri-kurallari.md`.

## Gereksinimler

### Gereksinim 1: Verinin Athena'ya kurulması
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, analiz tablolarını tek komutla ve tekrar tekrar kurabilmek istiyorum.

#### Kabul kriterleri
1. WHEN `deploy/athena/athena_setup.py` çalıştırıldığında THE SYSTEM SHALL hesabın seçili bölgesinde `courier-memory-athena-<hesap>-<bölge>` adlı bir S3 bucket'ı (yoksa) kurmalı ve herkese açık erişimi dört ayarla kapatmalıdır.
2. THE SYSTEM SHALL her tabloyu `data/<tablo>/part-0.json.gz` anahtarına sıkıştırılmış JSON Lines olarak, sunucu tarafı şifrelemeyle (`AES256`) yüklemelidir.
3. THE SYSTEM SHALL `courier_memory` veritabanını ve dört dış tabloyu (`deliveries`, `addresses`, `daily_metrics`, `couriers`) Athena DDL ile tanımlamalıdır (`JsonSerDe`, konum `s3://<bucket>/data/<tablo>/`).
4. THE SYSTEM SHALL betiği tekrar çalıştırmayı güvenli kılmalıdır: veri üzerine yazılır, tablo tanımı silinip yeniden kurulur (S3'teki veri yerinde kalır), yinelenen kaynak açılmaz.
5. WHEN kurulum bittiğinde THE SYSTEM SHALL her tablonun satır sayısını Athena'da `count(*)` ile okuyup yazdırmalıdır.
6. THE SYSTEM SHALL satırları yalnız çalıştırma klasöründen üretmelidir (`--run-dir`, varsayılan `data/demo_run`; `delivery_log.json`, `addresses.json`, `daily.json` + `meta.json`, `couriers.json`).

### Gereksinim 2: Tablolar
**Kullanıcı hikayesi:** Bir şube müdürü olarak, teslim denemelerini, adresleri, günlük şube ölçülerini ve kadroyu aynı yerden sorgulamak istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL `deliveries` tablosunda hafızalı yapının (kol D) her teslim denemesini tutmalıdır: `day`, `address_id`, `minute` (günün dakikası), `absent` (1 = alıcı yoktu).
2. THE SYSTEM SHALL `addresses` tablosunda adresin konumunu, türünü ve harita bloğunu tutmalıdır: `id`, `lat`, `lng`, `kind`, `block`, `label`.
3. THE SYSTEM SHALL `daily_metrics` tablosunda dört yapının (A–D) günlük şube ölçülerini yan yana tutmalıdır; başarısızlık nedenleri ayrı sütunlardır (`fail_recipient_absent`, `fail_address_not_found`, `fail_closed`, `fail_entry_failed`, `fail_recipient_unreachable`, `fail_wrong_deferral`, `fail_other`) ve toplamları `fail`'e eşittir.
4. THE SYSTEM SHALL `couriers` tablosunda yalnız kurye kimliğini, türünü, başlangıç ve bitiş gününü ve izin günü sayısını tutmalıdır.
5. THE SYSTEM SHALL her satırı tablonun sütun sırasıyla üretmelidir; demo çalıştırmasında `deliveries` 92.381, `addresses` 40.000 satırdır.

### Gereksinim 3: Kişisel veri Athena'ya çıkmaz
**Kullanıcı hikayesi:** Bir kurye olarak, adımın ve kapıda bıraktığım serbest metin notların analiz tablolarına girmemesini istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL kurye adını hiçbir tabloya yazmamalıdır.
2. THE SYSTEM SHALL serbest metin kurye notlarını (`notes.json`) hiç yüklememelidir; not tablosu yoktur.
3. THE SYSTEM SHALL bunu AWS'ye gitmeyen bir testle göstermelidir.

### Gereksinim 4: Çalışma grubu
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, kötü yazılmış bir sorgunun maliyet üretmemesini istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL `courier-memory` adlı bir Athena çalışma grubu kurmalı ya da güncellemelidir.
2. THE SYSTEM SHALL çalışma grubunda sonuç yerini `s3://<bucket>/results/` olarak zorlamalıdır (istemci başka yer veremez).
3. THE SYSTEM SHALL sorgu başına taranan veriyi 100 MB ile sınırlamalı ve CloudWatch ölçülerini açmalıdır.

### Gereksinim 5: `query_history` aracı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, ajanın sorumu SQL'e çevirip yalnız okuma yaparak sayıyla cevaplamasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL `query_history(sql)` aracını Strands `@tool` olarak açmalıdır; sorgu `courier_memory` veritabanında ve `courier-memory` çalışma grubunda çalışır (`CM_ATHENA_DATABASE`, `CM_ATHENA_WORKGROUP` ile değişir).
2. THE SYSTEM SHALL yalnız tek bir `SELECT` ya da `WITH … SELECT` sorgusunu kabul etmelidir.
3. IF sorgu noktalı virgül ya da yorum (`--`, `/*`) içerirse, yazma ya da yönetim anahtar kelimesi (`insert`, `drop`, `create`, `unload`, `show`, `describe` …) taşırsa ya da başka bir veritabanının tablosunu anarsa THEN THE SYSTEM SHALL sorguyu Athena'ya göndermeden reddetmeli ve modele nedenini ve "yalnız tek bir SELECT" ipucunu dönmelidir.
4. THE SYSTEM SHALL kabul edilen sorguyu en çok 200 satırla sınırlamalıdır (`SELECT * FROM (<sorgu>) AS q LIMIT 200`); sonuçta `columns`, `rows`, `row_count`, `truncated` ve `scanned_kb` döner.
5. IF sorgu 60 sn içinde bitmezse THEN THE SYSTEM SHALL sorguyu durdurmalı ve modele daha dar bir sorgu yazmasını söyleyen bir hata dönmelidir.
6. IF Athena sorguyu çalıştıramazsa (SQL hatası, iptal) THEN THE SYSTEM SHALL Athena'nın nedenini hata sonucu olarak dönmelidir; model düzeltip yeniden deneyebilir.
7. IF AWS istemcisi hata verirse THEN THE SYSTEM SHALL ayrıntıyı log'a yazmalı, modele yalnız hata kodunu içeren kısa bir metin dönmelidir; konuşma kesilmez.

### Gereksinim 6: Analiz Ajanı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, geçmiş veri sorularımı Supervisor'a sorup Analiz Ajanı'ndan cevap almak istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL Analiz Ajanı'nı ayrı bir AgentCore runtime'ı olarak kurmalıdır (`analyst`, `CM_AGENT_ROLE=analyst`); tek aracı `query_history`'dir.
2. THE SYSTEM SHALL Analiz Ajanı'nın sistem istemine tablo şemasını (sütunlar ve anlamları, yapıların A–D açıklaması) koymalıdır.
3. THE SYSTEM SHALL Analiz Ajanı'na sonucu kısa ve sayılarla anlatmasını, çalıştırdığı sorguyu tek satırda belirtmesini ve verinin simülasyon geçmişi olduğunu, gerçek gün kanıtı olmadığını söylemesini istemde yazmalıdır.
4. WHEN Supervisor'a geçmiş veri sorusu geldiğinde THE SYSTEM SHALL soruyu `ask_analyst` ile Analiz Ajanı'na doğal dille iletmelidir; SQL'i uzman yazar.
5. THE SYSTEM SHALL `query_history` ve `ask_analyst`'i müdür aracı saymalıdır; kurye ya da konuk isteği Supervisor'da uzman çağrılmadan, Analiz Ajanı'nda da araç çalışmadan reddedilir.
6. WHEN yapı tek runtime'a döndürüldüğünde (`CM_MULTI_AGENT=0`) THE SYSTEM SHALL Athena aracını ve politikasını kurmamalıdır.

### Gereksinim 7: Salt okunur izin
**Kullanıcı hikayesi:** Bir ekip üyesi olarak, Analiz Ajanı'nın veriyi değiştirememesini ve başka kaynağa dokunamamasını istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL Analiz Ajanı'nın rolüne `agentcore/analyst-policy.json` politikasını `additionalPolicies` ile vermelidir; politikayı `agentcore_config.py` yazar.
2. THE SYSTEM SHALL Athena izinlerini yalnız `courier-memory` çalışma grubuyla sınırlamalıdır (sorgu başlatma, durum ve sonuç okuma, durdurma, çalışma grubunu okuma).
3. THE SYSTEM SHALL Glue iznini yalnız katalog, `courier_memory` veritabanı ve onun tabloları için okuma ile sınırlamalıdır.
4. THE SYSTEM SHALL S3'te `data/` altında yalnız okuma, `results/` altında sorgu sonucu yazma ve okuma iznini vermelidir; bucket adı `courier-memory-athena-` önekiyle sınırlıdır.
5. THE SYSTEM SHALL kaynak adlarını üç yerde aynı tutmalıdır: `deploy/athena/athena_setup.py`, `deploy/agentcore/agentcore_config.py`, `deploy/agentcore/runtime/cm/athena.py`.

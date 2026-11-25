# Gereksinimler: Gerçek gün (Beykoz, 5 Mayıs)

## Giriş

Sorunun büyüklüğü simülasyonla değil gerçek veriyle gösterilir: sabit bölgede iş yükü dengesizdir, dinamik kümeleme dengeler ama kurye bilmediği sokağa girer, bilmediği sokakta teslim daha sık başarısız olur. Bu spec o günün verisini ve üzerindeki hafıza kapsamı hesabını tanımlar. Sözleşme: `docs/sozlesmeler.md` §13. Veri kuralları: `.kiro/steering/veri-kurallari.md`.

## Gereksinimler

### Gereksinim 1: Gün verisi
**Kullanıcı hikayesi:** Bir jüri üyesi olarak, iddianın gerçek gönderilere dayandığını görmek istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL günün sabit bölgelerini, kurye iş yüklerini, dinamik kümelerini, duraklarını ve gerçek başarısızlık oranlarını (tanıdık ↔ yabancı sokak) tek dosyada sunmalıdır.
2. THE SYSTEM SHALL bu dosyada barkod, bölge kodu, alıcı bilgisi ve kurye kimliği taşımamalıdır; kurye adları takma addır.
3. THE SYSTEM SHALL gerçek veriden gelen her görünümde "Gerçek veri" etiketini korumalıdır.

### Gereksinim 2: Hafıza kapsamı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, kuryenin bilmediği duraklardan kaçında hafızada bilgi olduğunu bilmek istiyorum.

#### Kabul kriterleri
1. WHEN hafıza özeti istenirse THE SYSTEM SHALL bilgi gerektiren yabancı durakların hafızada kapsanan payını döndürmelidir.
2. THE SYSTEM SHALL beklenen başarısız teslimi gönderi sayısı ve gerçek oranlarla hesaplamalı; hafızanın etkisini kapsanan pay kadar saymalı ve bunu VARSAYIM olarak etiketlemelidir.

### Gereksinim 3: Küme ve kurye aktarımı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, bir kuryeyi komşu şubeye verirsem bilgi kaybının ne olacağını görmek istiyorum.

#### Kabul kriterleri
1. WHEN bir küme istenirse THE SYSTEM SHALL kümeleme motorunun sırasıyla durakları, kartları, gerçek yol çizgisini ve Bölge Ajanı'nın küme kartını döndürmelidir.
2. WHEN kurye aktarımı istenirse THE SYSTEM SHALL kalan kümeleri yeniden dengelemeli, yeni yabancı durakları ve hafızanın kapsadığı kısmı bildirmelidir.
3. THE SYSTEM SHALL yeniden dengelemenin yaklaşık olduğunu sonuçta açıkça söylemelidir (gerçek kümeleme motoru bu adımda çalışmaz).

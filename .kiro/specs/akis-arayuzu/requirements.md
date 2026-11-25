# Gereksinimler: "Nasıl çalışır" arayüzü (`/flow/`)

## Giriş

Hikaye arayüzü neden yaptığımızı anlatır; kodun ve işlemlerin nasıl aktığını göstermez. Bu arayüz bir günün akışını sekiz adımda, her adımda gerçek API çağrısı ve ajan iziyle gösterir. Hedef kitle yöneticiler ve teknik değerlendiriciler.

## Gereksinimler

### Gereksinim 1: Akış
**Kullanıcı hikayesi:** Bir yönetici olarak, hangi ajanın hangi sırayla ne yaptığını tek ekranda izlemek istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL günü sekiz adımda sunmalıdır: plan, müdür onayı, brifing, kurye notu, kapıda kart, hasat, sabah değerlendirmesi, bölge raporu.
2. THE SYSTEM SHALL her adımda sorumlu ajanı, ilgili kod dosyalarını ve API ucunu göstermelidir.
3. WHEN bir adım çalıştırıldığında THE SYSTEM SHALL canlı API'yi çağırmalı; kayıtlı ya da gömülü yanıt kullanmaz.
4. THE SYSTEM SHALL adımları tek tek, sırayla ya da baştan sona oynatmaya izin vermelidir.

### Gereksinim 2: İz
**Kullanıcı hikayesi:** Bir teknik değerlendirici olarak, ajanın kararını ve çağırdığı aracı girdisi ve çıktısıyla görmek istiyorum.

#### Kabul kriterleri
1. WHEN bir HTTP isteği yapıldığında THE SYSTEM SHALL yöntemi, yolu, gövdeyi, durum kodunu ve süreyi göstermeli; yanıtın JSON'u açılabilir olmalıdır.
2. WHEN yanıt ajan izi taşıdığında THE SYSTEM SHALL olayları sırasıyla göstermelidir: karar, araç, sonuç, yedek, öneri, onay, bitti.
3. THE SYSTEM SHALL her iz satırında kaynağı (kural ya da LLM) göstermelidir.

### Gereksinim 3: Bağlam
**Kullanıcı hikayesi:** Bir yönetici olarak, adımın sistemin hangi parçalarına dokunduğunu ve hafızada neyi değiştirdiğini görmek istiyorum.

#### Kabul kriterleri
1. WHEN bir adım seçildiğinde THE SYSTEM SHALL mimari şeritte ilgili parçaları vurgulamalı ve veri akışını bir satırda yazmalıdır.
2. WHEN bir adım bittiğinde THE SYSTEM SHALL adımın sonucunu düz dille, şube hafızasının güncel özetini ve ajan akışının son olaylarını göstermelidir.
3. THE SYSTEM SHALL "Baştan" ile demoyu sıfırlamalıdır.

### Gereksinim 4: Çalışma ortamı
#### Kabul kriterleri
1. THE SYSTEM SHALL dış bağımlılık olmadan tek dosya olarak çalışmalıdır.
2. WHEN sayfa bir ters vekilin arkasında (`/proxy/<port>/`) açıldığında THE SYSTEM SHALL API'ye ve yazı tiplerine o önekle ulaşmalıdır (ör. IDE içi tarayıcı vekili).
3. THE SYSTEM SHALL kullanıcıya görünen tür ve durum adlarını Türkçe göstermelidir.

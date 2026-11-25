# Gereksinimler: Demo izi sayfası (QR, `/demo/`)

## Giriş

Sunumun sonunda izleyici bir QR kod okutur ve telefonunda geçmiş bir demo koşusunu görür: her ajan ne aldı, ne düşündü, ne yaptı, ne verdi. Sayfa sunucu, API ya da giriş gerektirmez; açılır ve okunur. Hedef kitle jüri, yöneticiler ve teknik değerlendiriciler.

## Gereksinimler

### Gereksinim 1: Zincir
**Kullanıcı hikayesi:** Bir izleyici olarak, ajanların bir günü hangi sırayla ve birbirine ne aktararak yürüttüğünü telefonumda görmek istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL `/flow/` arayüzüyle aynı sekiz halkayı sırayla göstermelidir: Orkestratör, acil durum kapısı, Brifing, Hafıza, durak kartları, Hasat, Değerlendirme, Bölge.
2. THE SYSTEM SHALL her halkada dört bölüm göstermelidir: ne aldı (girdi), ne düşündü ve ne yaptı (karar ve araç çağrıları, sırasıyla), ne verdi (çıktı).
3. WHEN izleyici bir araç satırına dokunduğunda THE SYSTEM SHALL aracın girdisini ve çıktısını (JSON, kısaltılmış) açmalıdır.
4. THE SYSTEM SHALL her halkada kaynağı göstermelidir: kural, LLM ya da insan.

### Gereksinim 2: Dürüstlük
#### Kabul kriterleri
1. WHEN koşu kurallı modda üretildiyse THE SYSTEM SHALL bunu sayfanın başında söylemelidir (kararlar şablon; araçlar ve sayılar gerçek).
2. THE SYSTEM SHALL zincirin temassız çalıştığını göstermelidir: acil durum kapısı eşikleri, demo gününün kararı (temassız ya da eskale) ve simülasyonda müdürün kaç günde çağrıldığı. İnsan kararı için düşünce uydurulmaz.
3. THE SYSTEM SHALL kurye adlarının ve adreslerin simülasyon olduğunu belirtmelidir.

### Gereksinim 3: Veri kuralları
#### Kabul kriterleri
1. THE SYSTEM SHALL Hafıza Ajanı'nın çıktısında kapı şifresini ve kişisel veriyi göstermemelidir; kuryenin ham notundaki şifre üstü çizili gösterilir.
2. THE SYSTEM SHALL koşudan sonra canlı hafızayı koşu öncesi haline döndürmelidir.

### Gereksinim 4: Çalışma ortamı
#### Kabul kriterleri
1. THE SYSTEM SHALL tek, kendi içinde yeterli bir HTML dosyası olmalıdır (veri gömülü, dış istek yok).
2. THE SYSTEM SHALL telefon ekranında (≥ 360 px) yatay kaydırma olmadan okunmalıdır.
3. WHEN sayfa adresi verildiğinde THE SYSTEM SHALL QR kodunu üretmeli ve hikaye arayüzünün kapanış sahnesinde göstermelidir.

# Gereksinimler: Canlı akış (sunum ekranı + QR izleyicileri)

## Giriş

Sunumda ajan zinciri tek ekranda, canlı çalışır: sunucu "Günü planla"ya basar, sekiz adım (Orkestratör, acil durum kapısı, Brifing, Hafıza, durak kartları, Hasat, Değerlendirme, Bölge) sırayla koşar ve her karar, araç çağrısı ve sonuç ekrana akar. Salondakiler sağ alttaki QR'ı okutup aynı akışı telefonlarında izler; koşu başlatamazlar. Hikayenin eski Sahne 2 iz paneli ve Sahne 3 müdür ekranı panelleri bu akışla değişir.

## Gereksinimler

### Gereksinim 1: Tek koşu, çok izleyici
#### Kabul kriterleri
1. WHEN sunum ekranında "Günü planla"ya basıldığında THE SYSTEM SHALL sekiz adımı sunucuda bir kez, sırayla çalıştırmalıdır.
2. WHILE bir koşu sürerken THE SYSTEM SHALL ikinci başlatmayı reddetmelidir (409).
3. THE SYSTEM SHALL her olayı bağlı bütün izleyicilere aynı sırayla iletmelidir; sonradan bağlanan izleyici o ana kadarki olayları da almalıdır.
4. WHEN bağlantı koptuğunda THE SYSTEM SHALL izleyicinin kaldığı yerden sürmesini sağlamalıdır.
5. THE SYSTEM SHALL her koşuyu aynı başlangıç durumundan (hafıza, ajan akışı ve öğrenilen ayarlar baştan) başlatmalıdır.

### Gereksinim 2: İzleyici (QR) sayfası
#### Kabul kriterleri
1. THE SYSTEM SHALL `/flow/` adresinde koşu başlatma düğmesi göstermemelidir.
2. WHILE koşu yokken THE SYSTEM SHALL izleyiciye akışın sunumla başlayacağını söylemelidir.
3. THE SYSTEM SHALL telefon ekranında (≥ 360 px) yatay kaydırma olmadan tek sütun okunmalıdır; ajan izi kendi kutusunda canlı akmalıdır.
4. WHEN izleyici biten bir adıma dokunduğunda THE SYSTEM SHALL o adımın izini ve sonucunu göstermeli, "Canlıya dön" ile canlı adıma dönmelidir.

### Gereksinim 3: Sunum ekranı ve hikaye
#### Kabul kriterleri
1. THE SYSTEM SHALL hikaye Sahne 3'te akış ekranını sunum modunda göstermeli; yan panel, iz paneli ve müdür ekranı açılmamalıdır.
2. WHEN Sahne 2'de "Günü planla"ya (ya da →) basıldığında THE SYSTEM SHALL Sahne 3'ü açmalı ve koşuyu başlatmalıdır.
3. WHILE akış ekranı odaktayken THE SYSTEM SHALL sunum tuşlarını (→, ←, 1–8, A, Q) hikayeye iletmelidir.

### Gereksinim 4: QR
#### Kabul kriterleri
1. THE SYSTEM SHALL QR'ı sayfanın kendi kökünden (`<kök>/flow/`) tarayıcıda üretmelidir; HTTPS sayfada adres HTTPS olur.
2. THE SYSTEM SHALL QR'ı hikaye Sahne 2–3'te sağ altta göstermeli, Q tuşuyla her sahnede açıp kapatmalıdır; kapanış sahnesinin QR'ı da aynı adrese gitmelidir.

### Gereksinim 5: HTTPS ve veri kuralları
#### Kabul kriterleri
1. WHEN bir arayüz adresi sonda `/` olmadan istendiğinde THE SYSTEM SHALL göreli yönlendirmelidir (CloudFront arkasında http ya da ALB adresine düşmemelidir).
2. THE SYSTEM SHALL hafızaya yazılan ipucunda kapı şifresini göstermemelidir; kuryenin ham notundaki şifre üstü çizili gösterilir.
3. THE SYSTEM SHALL izleyiciye giden araç verisini kırpmalıdır (liste 8 öğe, metin 400 karakter).

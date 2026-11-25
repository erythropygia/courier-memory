# Gereksinimler: Dünya ve simülatör

## Giriş

Tüm demo ve sunum uygulama katmanından gelen 1 aylık geçmiş veri üzerinde çalışır. Bu spec o dünyayı ve dünyanın üzerinde koşan simülatörü tanımlar:

- **Dünya:** Bir şube, bloklar, adresler, adreslerin gizli püf noktaları, kuryeler ve kuryelerin gizli özellikleri, günlük talep.
- **Simülatör:** Aynı günleri dört farklı planlama koluyla oynatır ve sonuçları karşılaştırır:
  - **A:** Sabit bölge (mevcut yapı)
  - **B:** Dinamik planlama + geçmişe bakmadan atama
  - **C:** Dinamik planlama + kurye–bölge uyumuna göre atama
  - **D:** Çekirdek bölge + hafıza. Hafıza yalnız kapı ipucu vermez; planı (planda erteleme, servis süresi düzeltmesi) ve rotayı (pencere onarımı) de değiştirir; D kendi planını kurar, C'nin rotasını kopyalamaz (Gereksinim 15).

Simülatör ajanlar için hem test ortamı hem araç kaynağıdır. Ajanların kullandığı deterministik hesaplar (uyum tahmini, atama) bu pakette yaşar.

Bu spec LLM çağrısı içermez. Ajanlar sonraki spec'lerde aynı politika arayüzünü uygulayarak simülatöre takılır.

## Gereksinimler

### Gereksinim 1: Yapılandırma ve tekrar üretilebilirlik

**Kullanıcı hikayesi:** Bir ekip üyesi olarak, sunumdaki her rakamı tek komutla yeniden üretebilmek istiyorum ki jüri "bu rakam nereden?" diye sorduğunda cevap verebileyim.

#### Kabul kriterleri

1. Simülatör tüm parametreleri tek bir YAML dosyasından okumalıdır. Her parametrenin varsayılan değeri ve kısa bir gerekçe yorumu `sim/config/default.yaml` içinde bulunmalıdır.
2. Komut satırından yapılandırmanın herhangi bir alanı ezilebilmelidir (ör. `--set couriers.count=18`).
3. Aynı yapılandırma ve seed ile iki çalıştırma yapıldığında, simülatör bayt düzeyinde aynı metrik çıktısını üretmelidir.
4. Her çalıştırma bir çalıştırma kimliği almalıdır. Çıktı klasörüne kullanılan yapılandırmanın tam kopyası, seed ve paket sürümü yazılmalıdır.
5. Geçersiz bir yapılandırma verildiğinde simülatör hangi alanın neden geçersiz olduğunu söyleyen bir hatayla durmalıdır.

### Gereksinim 2: Coğrafya, bloklar ve adresler

**Kullanıcı hikayesi:** Bir demo izleyicisi olarak, gerçek bir şubeye benzeyen ama gerçek olmayan bir bölge görmek istiyorum ki sistem inandırıcı olsun ve hiçbir gerçek veri içermesin.

#### Kabul kriterleri

1. Simülatör yapılandırılabilir bir enlem/boylam kutusu içinde bir şube deposu ve ~300 m'lik bloklardan oluşan bir ızgara üretmelidir.
2. Her bloğun bir türü olmalıdır: yoğun konut, site, iş merkezi, sanayi, kırsal. Türlerin oranları ve mekânsal kümelenmesi yapılandırmadan gelmelidir. Yoğun alanlar merkezde, kırsal alan çeperde olur.
3. Her adres bir bloğa ait olmalı ve bir türü olmalıdır: ev, apartman, site, iş yeri, toplu teslim noktası. Adres türü bloğun türüyle tutarlı dağılmalıdır.
4. Her bloğun gizli bir zorluk değeri olmalıdır. Bu değer temel başarısızlık olasılığını ve navigasyon süresini etkilemelidir.
5. Üretilen adres koordinatları kendi bloğunun sınırları içinde kalmalıdır.

### Gereksinim 3: Gizli püf noktaları

**Kullanıcı hikayesi:** Bir ürün sahibi olarak, adreslerin kuryenin bilmediği püf noktalarını taşımasını istiyorum ki hafızanın neyi çözdüğü ölçülebilsin.

#### Kabul kriterleri

1. Adreslere yapılandırılabilir sıklıkta püf noktaları atanmalıdır. En az şu türler desteklenmelidir:
   - arka giriş
   - cumartesi kapalı
   - öğle arası kapalı
   - güvenlik/kart gerekli
   - zil çalışmıyor
   - haritadaki konum hatalı
   - toplu teslim noktası / resepsiyon
2. Her püf noktası türü için şu etkiler yapılandırılmalıdır: bilinmediğinde başarısızlık olasılığına eklenen değer, kapıda geçen süreye eklenen değer, zamana bağlı olup olmadığı (gün/saat penceresi).
3. Kalıcı püf noktaları ile süreli olanlar ayrılmalıdır. Süreli olanlar (ör. yol çalışması, geçici kapanış) simülasyon içinde başlayıp bitmelidir. Bir kısmı simülasyon ortasında değişmelidir (ör. giriş kapısı yer değiştirir); böylece bayat hafıza oluşur.
4. Püf noktaları gizli gerçek olarak saklanmalı, politikalara ve ajanlara verilmemelidir.

### Gereksinim 4: Kurye popülasyonu

**Kullanıcı hikayesi:** Bir ürün sahibi olarak, kuryelerin farklı beceri, hız, kıdem ve bölge bilgisine sahip olmasını istiyorum ki atama kararı anlamlı olsun ve uyum tahmincisinin doğruluğu ölçülebilsin.

#### Kabul kriterleri

1. Her kuryenin gizli özellikleri olmalıdır:
   - beceri çarpanı (başarısızlık olasılığına)
   - hız çarpanı (kapıda geçen süreye)
   - not bırakma eğilimi
   - kıdem
2. Kurye türleri desteklenmelidir:
   - **Kıdemli:** Isınma dönemi boyunca kendi sabit bölgesinde çalışmış.
   - **Yeni:** Isınma geçmişi yok.
   - **Ödünç:** Başka şubeden gelir; bu şubede tanıdıklığı sıfır.
3. Kurye takvimi desteklenmelidir: izin günleri, işten ayrılma tarihi, işe başlama tarihi.
4. Beceri ve hız dağılımları yapılandırmadan gelmelidir. Varsayılan dağılımlar uç değerler üretmemelidir: beceri çarpanı yaklaşık 0,6–1,6 arasında kalır.

### Gereksinim 5: Günlük talep

**Kullanıcı hikayesi:** Bir ekip üyesi olarak, gerçekçi günlük dalgalanmaları olan bir talep istiyorum ki dinamik planlamanın kurye sayısını değiştirmesi görünsün.

#### Kabul kriterleri

1. Her gün her adres için gönderi sayısı adres türüne bağlı bir oranla üretilmelidir. Toplu teslim noktaları tek durakta çok gönderi taşıyabilmelidir.
2. Haftanın günü etkisi desteklenmelidir. İş yerleri cumartesi düşük, konutlar daha yüksek talep alır.
3. Hacim şoku günleri yapılandırılabilmelidir (ör. +%30 kampanya günü, −%25 düşük gün).
4. Talep tüm kollar için aynı olmalıdır. Talep, politikadan bağımsız ve önceden üretilir.

### Gereksinim 6: Planlama (yeni yapı ve mevcut yapı)

**Kullanıcı hikayesi:** Bir demo izleyicisi olarak, sabit bölgelerle dinamik planlamayı aynı günlerde görmek istiyorum ki aralarındaki fark açık olsun.

#### Kabul kriterleri

1. **Sabit bölgeler:** Isınma döneminin ortalama talebinden bir kez hesaplanmalı ve değişmemelidir. Her kıdemli kuryenin bir bölgesi olur.
2. **Sabit bölgenin kuryesi yoksa** (izin, ayrılma): Bölge yedek ya da yeni bir kuryeye verilmelidir. Bu kural yapılandırmadan seçilir.
3. **Dinamik planlama:**
   - Her gün o günün duraklarını, toplam iş yükünü vardiya bandına yaklaştıran sayıda ve dengeli kümelere bölmelidir.
   - Küme sayısı o gün müsait kurye sayısını aşmamalıdır.
4. **Rota:** Her küme için bir durak sırası çıkarılmalıdır (en yakın komşu + 2-opt). Planlanan süre şöyle hesaplanır: servis süresi (durak başına 1 dk + gönderi başına 1,5 dk) + yol süresi (kuş uçuşu km × yol katsayısı × dk/km).
5. Planlama sonucu kurye bilgisinden bağımsız olmalıdır. Kümeler önce üretilir, kurye ataması ayrı bir adımdır (Gereksinim 9).

### Gereksinim 7: Sonuç modeli

**Kullanıcı hikayesi:** Bir ürün sahibi olarak, her teslim denemesinin sonucunun açık ve denetlenebilir bir modelle belirlenmesini istiyorum ki hangi başarısızlığın bilgiyle önlenebilir olduğu ayrılabilsin.

#### Kabul kriterleri

1. Her teslim denemesi için başarısızlık olasılığı şu bileşenlerden hesaplanmalıdır:
   - **Bilgiden bağımsız temel oran:** Alıcı yok, adres hatalı. Hafıza bunu düzeltemez.
   - **Blok zorluğu ve kurye becerisi.**
   - **Navigasyon cezası:** Kuryenin blok tanıdıklığına göre azalır.
   - **Püf noktası cezası:** Kurye püf noktasını bilmiyorsa ve hafızadan geçerli ipucu almadıysa eklenir. Zamana bağlı püf noktalarında ceza sadece ilgili pencerede uygulanır (ör. öğle arası).
   - **Bilinen püf noktasının kalan süresi (`known_minutes`):** Bilinse de kimlik işlemi, arkadan dolaşma gibi ek dakika kalır (güvenlik 2, resepsiyon 1, arka giriş 1, yol çalışması 2 dk; VARSAYIM).
2. Her başarısızlık bir neden koduyla kaydedilmelidir: alıcı yok, adres bulunamadı, kapalı, giriş yapılamadı, yanlış erteleme (`wrong_deferral`: hafıza durağı kapalı sandı, durak aslında açıktı; gönderi o gün kaçar, bilgiyle önlenebilir sayılır), diğer. Gizli gerçekte ayrıca "bilgiyle önlenebilir mi" bayrağı tutulmalıdır.
3. Kapıda geçen süre: servis süresi × kurye hız çarpanı + tanıdık olmayan blokta navigasyon süresi + bilinmeyen püf noktalarının süre etkisi.
4. **Ortak rastgele sayılar (CRN):** Rastgele çekilişler (gün, gönderi) anahtarıyla sabitlenmelidir. Aynı gönderi tüm kollarda aynı rastgele sayıyla değerlendirilir.
5. Varış saati, rota sırası ve planlanan sürelerden hesaplanmalıdır. Zamana bağlı püf noktaları bu saate göre değerlendirilir.
6. **Öğle arası düzeltmesi:** Öğle arası bilinse de varış pencerenin içine düşerse ek dakika `min(pencere sonu − varış, quirks.lunch_wait_max)` olur (bekleme ya da sonra dönme). Bilgi ancak rota pencereyi önlerse bedavadır. (Faz 1'deki "bilen kurye saati kaydırır, ceza kalkar" kestirmesi hafızaya rota değişikliğinin faydasını bedavaya yazıyordu; kaldırıldı.)
7. **Kapı hızı tahmini** (`estimation.speed`) yalnız kuryenin tanıdık duraklarından yapılır: yabancı sokakta yol bulma dakikası kurye hızı sanılmaz.

### Gereksinim 8: Tanıdıklık ve öğrenme

**Kullanıcı hikayesi:** Bir ürün sahibi olarak, kuryenin bir bloğu zamanla öğrenmesini ve uzak kalınca unutmasını istiyorum ki dinamik planlamanın bilgi kaybı modelde doğal olarak ortaya çıksın.

#### Kabul kriterleri

1. **Blok tanıdıklığı:** Her kurye×blok çifti için 0–1 arası bir değer tutulmalıdır. Ziyaretle artar (doygunluk eğrisi), ziyaret edilmeyen günlerde yavaşça azalır. Parametreler yapılandırmadan gelir.
2. **Püf noktasını öğrenme:** Kurye bir püf noktasıyla karşılaştığında (başarısızlık ya da gecikme), onu yapılandırılabilir bir olasılıkla kişisel bilgisine eklemelidir.
3. **İpucunun etkisi:** Hafızadan geçerli bir ipucu alan kurye, yapılandırılabilir bir uyum olasılığıyla püf noktası cezasından kurtulmalıdır.
4. **Bayat bilgi:** Değişmiş bir püf noktası için kuryenin eski bilgisi ya da bayat hafıza kaydı ceza kaldırmamalıdır. Yanlış ipucu yapılandırılabilir küçük bir ek ceza getirmelidir.
5. **Isınma dönemi:** Tüm kollar ortak bir ısınma dönemiyle (varsayılan 20 iş günü, sabit bölge) başlamalıdır. Değerlendirme dönemi aynı başlangıç durumundan kollara ayrılmalıdır.

### Gereksinim 9: Politika arayüzleri ve deterministik politikalar

**Kullanıcı hikayesi:** Bir geliştirici olarak, atama ve hafıza mantığını simülatöre takılabilir arayüzler üzerinden yazmak istiyorum ki LLM ajanları sonradan aynı arayüzü uygulayabilsin.

#### Kabul kriterleri

1. **İki arayüz tanımlanmalıdır:**
   - `AssignmentPolicy`: kümeleri ve müsait kuryeleri alır, küme→kurye eşlemesi döndürür.
   - `MemoryPolicy`: rota için ipuçlarını döndürür; günün notlarını ve teslim olaylarını alır.
2. Politikalar yalnızca gözlemlenebilir verileri almalıdır: geçmiş teslimatlar, ziyaretler, notlar, takvim. Gizli gerçek nesneleri politikalara geçirilmemelidir. Bunu doğrulayan bir test olmalıdır.
3. **Deterministik politikalar:**
   - **Sabit bölge:** Kol A.
   - **Geçmişe bakmadan atama:** Kol B. Tohumlu rastgele eşleme.
   - **Uyuma göre atama:** Kol C. Beklenen başarısızlık + süre maliyetiyle Hungarian.
   - **Hafıza (ayrıştırma doğruluğu parametreli):** Kol D. Notları yapılandırılabilir doğrulukla doğru adrese ve doğru püf noktasına bağlar. Bu doğruluk ileride Hafıza Ajanı'nın ölçülen doğruluğuyla değiştirilir. Hafıza kayıtları plan ve rota için kısıta da çevrilir (Gereksinim 15) ve hasatla büyür (Gereksinim 16).
4. **Uyuma göre atama maliyeti:** Küme içindeki her durak için tahmini başarısızlık olasılığı ve süre toplanarak hesaplanmalıdır. Hafızada geçerli notu olan duraklarda tanıdık olmamanın cezası düşürülmelidir.
5. **Kontrollü öğrenme rotasyonu:** P2'ye ertelendi.

### Gereksinim 10: Kurye–bölge uyum tahmincisi

**Kullanıcı hikayesi:** Bir ürün sahibi olarak, kurye uyumunun bölge zorluğundan arındırılarak tahmin edilmesini istiyorum ki zor bölgede çalışan kurye haksız yere düşük görünmesin.

#### Kabul kriterleri

1. Tahminci, gözlemlenen geçmişten kurye×blok beklenen başarısızlık olasılığını hesaplamalıdır. Yöntem: bloğun genel oranı × kuryenin bloğa göre standartlaştırılmış oranı. Az veride önsel değere doğru büzülme uygulanır.
2. Rapor, tahmin edilen kurye etkisi ile gizli gerçek beceri arasındaki sıra korelasyonunu (Spearman) vermelidir. Aynı rapor, bölgeden arındırılmamış basit kurye başarısızlık oranının korelasyonunu da vermelidir. Böylece arındırmanın neden gerektiği gösterilir.
3. Tahminci saf bir fonksiyon olarak dışa açılmalıdır. Atama Ajanı'nın aracı olarak doğrudan kullanılabilmelidir.

### Gereksinim 11: Kurye notları

**Kullanıcı hikayesi:** Bir geliştirici olarak, gerçekçi ve kusurlu kurye notları istiyorum ki Hafıza Ajanı gerçek zorluklarla test edilebilsin.

#### Kabul kriterleri

1. Kurye bir püf noktasıyla karşılaştığında, kendi not bırakma eğilimi olasılığıyla bir not üretilmelidir. Notun alanları: kurye, zaman, GPS (gürültülü), ilgili gönderi barkodu, serbest metin.
2. Not metni Türkçe ve konuşma dilinde olmalıdır. Kalıp tabanlı ve çeşitlendirilmiş üretilir: yazım hatası, kısaltma, gereksiz bilgi.
3. Notların yapılandırılabilir bir kısmı şu zorlukları taşımalıdır:
   - kişisel veri tuzağı (alıcı adı, telefon, kişisel yargı)
   - belirsiz adres ("şu köşedeki bina")
   - yanlış bilgi
   - adresle ilgisiz not (gürültü)
   Eskimiş bilgi, püf noktası değiştikten sonra hafıza kaydında kendiliğinden oluşur.
4. Her notun gizli gerçek karşılığı saklanmalıdır: hangi adres, hangi püf noktası, kişisel veri var mı. Hafıza Ajanı'nın doğruluğu buna göre ölçülür.
5. Notlar ayrıca JSON olarak dışa aktarılabilmelidir. Hafıza Ajanı geliştirme ve değerlendirmesinde kullanılır.

### Gereksinim 12: Senaryolar

**Kullanıcı hikayesi:** Bir sunumcu olarak, hazır senaryoları tek parametreyle seçebilmek istiyorum ki demoda hikayenin kritik anlarını gösterebileyim.

#### Kabul kriterleri

1. En az şu senaryolar hazır olmalıdır:
   - **Normal:** Hiçbir olay yok.
   - **İzin dalgası:** 3 kıdemli kurye bir hafta izinde.
   - **Ayrılma ve yeni kurye:** 2 kıdemli ayrılır, yerine 2 yeni kurye başlar.
   - **Ödünç kurye:** Komşu şubeden 3 kurye. Tanıdıklık bu şubenin ortak sınır sokaklarında farklıdır (Gereksinim 18): biri doğu sınırını, biri kuzey sınırını dağıtıyor, biri hiçbirini tanımıyor.
   - **Hacim şoku:** Bir gün +%30, bir gün −%25.
2. Senaryolar yapılandırma üzerine katman olarak tanımlanmalı ve birleştirilebilmelidir.
3. Her senaryo için demoda gösterilecek "kritik gün" ve "kritik kurye" otomatik işaretlenmelidir. Seçim ölçütü: hikaye önceliği (komşu şubeden "kim gitsin" seçiminin yapıldığı gün, yani gelebilecek ödünç > kullanılan; sonra ödünç > yeni > yedek), sonra ipucu × yabancılık; aday yoksa kollar arası farkın en büyük olduğu gün ve kurye.
4. `hiring` senaryosu (Hedef 1 deneyi): değerlendirme gününde 4 kıdemli ayrılır, aynı gün 4 yeni kurye (N01–N04) başlar; ayrılanlar son üç gününde devir teslim hasadına girer.

### Gereksinim 13: Metrikler, rapor ve sağlamlık taraması

**Kullanıcı hikayesi:** Bir jüri üyesi olarak, kolların karşılaştırmasını ve varsayımlar değiştiğinde sonucun ne kadar dayanıklı olduğunu görmek istiyorum ki iddialara güvenebileyim.

#### Kabul kriterleri

1. Her kol ve her gün için şu metrikler hesaplanmalıdır (Faz 2: yüzde yerine adet ve dakika öne çıkar; bkz. Gereksinim 17):
   - ilk denemede teslim oranı
   - neden koduna göre başarısızlık dağılımı
   - bilgiyle önlenebilir başarısızlık sayısı
   - kurye sayısı (araç-gün)
   - toplam km
   - vardiya bandındaki kurye oranı
   - kuryeler arası iş yükü sapması (CV)
   - durak başına kapıda geçen süre
   - kuryenin yabancı olduğu bloklara düşen durak payı
   - hafıza kapsamı (yalnız D)
2. **Yeni ve ödünç kurye öğrenme eğrisi:** İlk 10 iş gününde günlük başarı oranı kol bazında raporlanmalıdır.
3. **Çıktılar:** Bir özet JSON'a, günlük ayrıntılı bir JSON'a ve insan tarafından okunabilir bir Markdown özetine yazılmalıdır. Arayüzün gün seçip haritada gösterebilmesi için günlük durak, küme, atama ve sonuç kayıtları da dışa aktarılmalıdır.
4. **Sağlamlık taraması:**
   - Simülatör, seçilen parametrelerin ızgarası üzerinde birden fazla seed ile koşabilmelidir. Varsayılan parametreler: tanıdıklık etkisi, püf noktası sıklığı, not bırakma eğilimi, hafıza ayrıştırma doğruluğu.
   - Her kombinasyonda kollar arası farkları kaydetmeli ve `sweep.json → manset` olarak raporlamalıdır: D − A ilk denemede teslim farkı (min … max, medyan, ±0,15 puan içinde kalma payı, ≥ 0 payı, seed'ler arası yayılım), kurye-gün farkı (%) ve D − C farkı (min … max, pozitif kalma payı). "D ≥ C ≥ B" sıralaması yalnız geriye uyumluluk için tutulur, manşet değildir (B rastgele atama olduğu için önemsizdir).
5. **Hız:** Varsayılan yapılandırmada tek bir çalıştırma (20 gün ısınma + 20 gün değerlendirme, 4 kol) sıradan bir dizüstü bilgisayarda 60 saniyenin altında tamamlanmalıdır. Sağlamlık taraması çok çekirdekli koşabilmelidir.

### Gereksinim 14: Yasaklı içerik koruması

**Kullanıcı hikayesi:** Bir ekip üyesi olarak, repoya yanlışlıkla gerçek veri ya da şirket içi ad girmesini otomatik olarak yakalamak istiyorum ki hackathon teslimi güvenli olsun.

#### Kabul kriterleri

1. Bir test, repodaki metin dosyalarını yasaklı kalıplar için taramalıdır: şirket içi sistem adları, iç alan adları, gerçek şube kimliği, gerçek bölge kodu biçimi. Başarısızlık durumunda dosya adını ve satırı göstermelidir.
2. Tarama `.kiro/`, `.venv/`, `runs/` ve testin kendi dosyasını dışlamalıdır.
3. Arayüze giden her dışa aktarım "app_data": true alanını taşımalıdır.

### Gereksinim 15: Hafıza-farkında plan ve rota (kol D)

**Kullanıcı hikayesi:** Bir ürün sahibi olarak, hafızanın yalnız kapıda ipucu vermesini değil planı ve rotayı da değiştirmesini istiyorum ki "hafıza optimizasyona serbestlik kazandırır" cümlesi aynı kolda doğru olsun.

#### Kabul kriterleri
1. `cm_sim/routing_memory.py` saf fonksiyonlardan oluşmalıdır (yalnız dizi ve sözlük alır; gizli gerçek yok). Üç adım:
   - **Planda erteleme:** bugün kapalı olduğu bilinen durak (cumartesi kapalı + Cumartesi, geçici kapalı) kümelemeden ÖNCE rotadan çıkar.
   - **Servis süresi düzeltmesi:** bilinen püf noktasının kalan süresi (`routing.extra_service_min`) durak ağırlığına (kümeleme) ve planlanan süreye eklenir.
   - **Pencere onarımı:** kapalı penceresi bilinen (öğle arası) durağın beklenen varışı pencereye ± `routing.window_margin_min` düşüyorsa, en az km artışıyla pencere dışına taşınır. Bedel (+km) raporlanır.
2. **Erteleme yalnız `routing.defer_min_sources` (2) bağımsız kaynakla** yapılır. Tek kaynaklı kapanış rotada kalır, kapıda ipucu olur. Yanlış erteleme gönderiyi kaçırır (`wrong_deferral`).
3. D, C'nin rotasını kopyalamaz: kendi planını (`plan`: düz sıra, düz km, düz süre, ertelenenler) kurar. `routing.enabled=false` ile D yalnız kapı ipucuna döner (ablasyon için).
4. Kol D ve Orkestratör'ün `compute_route` aracı AYNI fonksiyonları çağırır; canlı hafıza = simülasyonun o günkü hafızası iken ajanın hafızalı sırası kol D'nin yürüttüğü sırayla her günün her rotasında birebir aynı olmalıdır (test).
5. **Karşı-olgu:** her D rotası aynı kurye, aynı duraklar ve aynı rastgele sayılarla üç kez yürütülür: hafızasız, yalnız ipucu, hafızalı. Fark hafızanın rotaya katkısının ölçüsüdür. Karşı-olgu kuryenin o günkü bilgisiyle yapılır (hafıza olmasaydı kurye bazı püf noktalarını takılarak kendisi öğrenirdi); bu yüzden kol C ↔ D ve aynı rota karşı-olgusu ayrı raporlanır.
6. **Ablasyon** (`python -m cm_sim.ablation [--seeds 3]` → `ablation.json`): demo senaryoları × seed; varyantlar `hint_only`, `hint_harvest`, `hint_route`, `full`. Kol A, B, C her varyantta aynıdır; yalnız D değişir. Rotanın küçük katkısı (ilk denemeye katkı yok; fazla mesai ve bekleme düşer, km +%1) dürüstçe raporlanır.

### Gereksinim 16: Hasat (kol D)

**Kullanıcı hikayesi:** Bir ürün sahibi olarak, kıdemlinin bilgisinin yalnız tesadüfen bırakılan notlarla değil sistematik sorularla toplanmasını istiyorum.

#### Kabul kriterleri
1. Kol D'de plan kesinleşince (plan sonrası) hasat çalışır: bugünkü planda bölgeye yabancı kurye için hafızası boş duraklarını o bloğu en iyi tanıyan kıdemliye sorar. Parametreler: `memory.harvest_per_day` (30), `memory.harvest_per_senior` (3; ayrılan kuryede 10), `memory.p_answer` (0,8; VARSAYIM).
2. Ayrılan kuryeye son 3 gününde devir teslim soruları sorulur.
3. Cevap kıdemlinin gizli bilgisinden üretilir (simüle insan) ve `parse_accuracy` ile hafızaya geçer.
4. Atama matrisi (`assign/D`) hasattan ÖNCEKİ hafızayla, anlık görüntü hafızası (`memory/{gün}`) hasattan SONRAKİ hafızayla yazılır; matris yeniden hesaplanmaz (Orkestratör planı = simülatör planı eşitliği bozulmasın).
5. Günlük hasat istatistiği `harvest.json` olarak dışa aktarılır.

### Gereksinim 17: Hedef 1 ölçümü (öğrenme eğrisi)

**Kullanıcı hikayesi:** Bir jüri üyesi olarak, hafızanın yeni kuryeyi gerçekten daha hızlı "yetiştirdiğini" yüzde yerine adet ve dakikayla görmek istiyorum.

#### Kabul kriterleri
1. `python -m cm_sim.learning [--seeds 12] [--workers 8]` → `learning.json`. Senaryo `hiring`; her seed'de aynı dört yeni kurye iki kolda da çalışır (aynı rastgele sayılar).
2. Ölçüler kuryenin kaçıncı iş günü olduğuna göre: bilgiyle önlenebilir başarısız / 100 durak ve kapıda dk / durak. İki karşılaştırma: C ↔ D (iki ayrı dünya) ve aynı rota karşı-olgusu (D hafızasız).
3. **Ustalaşma günü:** 3 günlük hareketli ortalama, aynı koldaki kıdemli ortalamasının 1,1 katına indiği ilk gün (ortak eşik: kol C kıdemli düzeyi × 1,1).
4. **İlk hafta** (6 iş günü): kurye başına önlenebilir başarısız ve rota dakikası; ortalama ve %95 aralık (seed × kurye); manşet eşli fark (C − D).

### Gereksinim 18: Hedef 2 ("kim gitsin") farklılaşması

**Kullanıcı hikayesi:** Bir şube müdürü olarak, komşu şubeden kimin geleceğinin gerçek bir karar olmasını istiyorum; adaylar eşit görünmemeli.

#### Kabul kriterleri
1. Ödünç kimliği birden çok dönemde çalışabilmelidir (`calendar.borrowed[]` aynı kimlikle birden çok kayıt).
2. `border_side` (east, north, …), `border_depth_km` ve `border_familiarity`: komşu şubeyle ortak sınır sokaklarının tanıdıklığı gözlemlenebilir geçmiş olarak girer (kuryenin kendi şubesinden o sokakları dağıttığı günler). Performans ya da "önceki destek günü" ölçütü kullanılmaz (sıralamayı kapı hızı tahmini belirliyordu; ürün ilkesine aykırı).
3. Demo günü adayları tanıdık payına göre farklı çıkmalıdır (gün 32: Onur %86 > Gökhan %33 > Melis %0; Faz 5 verisinde %100 > %64 > %0); eşitlik olmamalıdır. Demo anı gün 32 · Gökhan'dır (`export.STORY_MOMENT`; o gün D'de yoksa sezgisel seçim).

### Gereksinim 19: Dışa aktarım (Faz 2 alanları)

#### Kabul kriterleri
1. D anlık görüntüsünde her rota `plan` (düz sıra, düz km, düz süre, ertelenenler) ve `counterfactual` (`memoryless`, `hint_only`, `memory`) taşımalıdır. `stops` yürütülen (hafızalı) sıradadır; plandan çıkan duraklar yalnız `plan.deferred`'dadır.
2. `summary.json → memory_routing` (gün ve kurye türü bazında dağılım: `type.{senior,reserve,new,borrowed}`) ve `learning_curve.json → same_route` yazılmalıdır. Tek rota rakamı dağılımsız gösterilmez.
3. `meta.json → critical`: `memory_gain` (demo kuryesi için aynı rota, hafızasız ↔ hafızalı dk).
4. `harvest.json`, `learning.json`, `ablation.json`; `publish` bunları `data/demo_run/` altına kopyalar.

### Gereksinim 20: Teslim zamanı: saate bağlı "alıcı yok" ve zaman analizi (Faz 2b)

**Kullanıcı hikayesi:** Bir şube müdürü olarak, "bir müşteri 10 ayrı gün hep 13:00'te geldik, hiç teslim edemedik" kalıbını sistemin kayıtlardan kendi bulup rotayı buna göre düzeltmesini istiyorum. (Faz 2'de "alıcı yok" saatten bağımsızdı; böyle bir kalıp var olamazdı.)

#### Kabul kriterleri
1. **Gizli bulunabilirlik profili:** her adresin profili vardır (`presence` bölümü: `home`, `worker`, `shop`, `office`, `reception`; saat dizileri hafta içi / Cumartesi ayrı; adres türüne göre `mix`; adres düzeyi `intensity` çarpanı). Profil ayrı RNG akışıyla (`S_PRESENCE=5`) kurulur; dünyanın geri kalanı değişmez. `presence.enabled=false` Faz 2 modeline döner.
2. **Durak düzeyinde, varış saatine bağlı yokluk** (`world.p_absent`): kapıda kimse yoksa duraktaki tüm gönderiler `recipient_absent` olur. Kalibrasyon hedefleri değişmez: 14/14 korunur.
3. **Teslim kaydı:** kol D'nin her denemesi (ertelenmemiş; teslim ya da `recipient_absent`) `TimeRecord`'na yazılır; bilgiye bağlı başarısızlık sayılmaz. Dışa: `delivery_log.json`.
4. **Zaman analizi (`cm_sim/delivery_time.py`, saf):** 5 dilim (09–12, 12–14, 14–16, 16–18, 18 sonrası); `counts_from_log(..., before_day)` yalnız geçmiş günleri sayar (gelecek sızıntısı yok); iki kademeli Beta-Binomial büzme (dilim → adres geneli → adres türü zaman şekli). Bulgular: `window` (kötü dilimde kendi ≥ 2 "alıcı yok", iyi dilimde kendi ≥ 2 deneme; güven = P(kötü > iyi) Beta nicelik integrali; `high` ≥ 0,95, `mid` ≥ 0,85) ve `confirmation` (kötü dilim belli, başka veri yok → hasat sorusu). Parametreler `time_analysis` bölümünde.
5. **Zaman onarımı (`routing_memory.repair_times`):** or-opt + 2-opt ters çevirme; amaç = sürüş dk + km × `time_km_cost_min` + Σ beklenen bulunamama × `time_revisit_min`; bilinen pencere ihlalini artırmaz; `plan_route(..., time_repair=)` `time_fail` döner. Kurallı politika `routing.time_min_confidence: mid`. Değişiklik sıra numaraları 1 tabanlı durak sırasıdır.
6. **Karşı-olgu `no_time`:** aynı hafızalı rota, zaman onarımı olmadan, aynı rastgele sayılarla. Dışa: `time.json`, `truth.presence`, `summary.time_analysis` (günlük bulgu/teyit/rotada, doğruluk, karşı-olgu farkı), `meta.time_example`, anlık görüntüde `counterfactual.no_time`, `time_stops`, `plan.time_fail`.
7. **Ablasyon:** varyantlar `no_time`, `full_g60`, `no_time_g60`; `time_contribution` geçmiş derinliği duyarlılığını gösterir.
8. **Dürüstlük:** gerçek Beykoz verisinde başarısızlık saati/nedeni boştur; etki gerçek veriyle kanıtlanamaz, simülasyonda mekanizma olarak gösterilir, büyüklüğünü pilot ölçer. Profiller ve paylar VARSAYIM'dır.
9. **Testler:** `sim/tests/test_delivery_time.py` (7 hızlı).

### Gereksinim 21: Onarım rotayı uzatmaz: sert kısıt ve kaydırılamayan bulgunun alternatifleri (Faz 2c)

**Kullanıcı hikayesi:** Bir şube müdürü olarak, ajanın bir durağı iyi saate taşırken rotayı uzatmasını ve kuryeyi fazla mesaiye sokmasını istemiyorum. Kural: ajan mevcut rotadan daha uzun bir rota çıkarmamalı. (Faz 2b'de onarım durağı akşama kaydırıp rotayı uzatabiliyordu.)

#### Kabul kriterleri
1. **Sert kısıt (`routing_memory.RepairLimits`, `plan_route(..., limits=)`):** pencere (öğle arası) onarımı ve zaman onarımı, *onarım öncesi rotaya* (erteleme sonrası, servis düzeltmeli düz sıra) göre: (a) beklenen rota süresini (sürüş + servis + bilinen öğle beklemesi) `routing.repair_max_extra_min` (0 dk) üstünde artıramaz; (b) km'yi `routing.repair_max_extra_km` (0,5 km) üstünde artıramaz; (c) vardiya bandı üstünü (`planning.band[1]`) aşamaz, onarım öncesi zaten aşıyorsa süre hiç artamaz; (d) kaydırılan durak vardiya bitişinden (beklenen varış) sonraya konamaz.
2. Kısıtı bozan hamle maliyetinden bağımsız reddedilir: beklenen başarısızlık maliyeti fazla mesaiyi "kazanç" diye satın alamaz. Servis süresi düzeltmesi sırayı değiştirmez; kısıtın iki tarafında da aynıdır. Config: `routing.repair_limits`, `repair_max_extra_min`, `repair_max_extra_km`, `time_blocked_diff`, `time_alternatives`. Zaman onarımının tabanı pencere onarımı **sonrası** rotadır (zaman-farkında ≤ zamansız ≤ onarım öncesi); karşı-olguda `diff_daily.expected_duration_min` ≤ tolerans ve `diff_daily.overtime_min` ≤ 0. Bekleme tahmini ±`repair_wait_margin_min` (30 dk) paylı pencereyle yapılır; zaman onarımı ve aktarmada öğle penceresi ihlali de bu geniş payla sayılır; km sınırı pencere + zaman birlikte onarım öncesine göre. Zaman hamlesi (aynı rota ve aktarma) km'yi hiç artıramaz (km toleransı yalnız pencere taşımasında).
3. **Kaydırılamayan bulgu:** `plan_route` çıktısı `time_blocked` (onarımdan sonra en iyi dilimden ≥ `time_blocked_diff` kötü dilimde kalan bulgu; `reason` ∈ no_good_hour | after_shift | route_duration | bant | km | pencere | gain_insufficient; `min_extra_min`). Sessizce düşmez.
4. **Alternatifler (`routing_memory.time_alternatives(routes, ...)`, kol D ve ajan aynı fonksiyon):** sırayla (i) aynı rota içinde kısıt dahilinde yer; (ii) **aktarma**: o saatte bölgeden geçen başka kuryenin rotasına ekleme (iki rotada birlikte: toplam süre ve km artmaz, hedef bandı aşmaz, durak vardiya bitişinden önce, öğle penceresi ihlali artmaz, toplam beklenen bulunamama düşer; kabul edilen aktarma sonrakilerde hesaba katılır); (iii) aktarma yoksa uygun dilim vardiya içindeyse **ertesi gün**, değilse **akşam teslimi / teslim noktası** önerisi. Hepsinde alıcıya önceden **SMS** önerisi (`sms_text`, kişisel bilgi yok).
5. **Karar müdürdedir:** simülasyon alternatifleri UYGULAMAZ; ölçülen etkide yoktur. Metinler `cm_sim.delivery_time.alternative_text`, `REASON_TEXT`, `OPTION_NAME`.
6. **Dışa aktarım:** `summary.time_analysis` → `constraint`, `overtime_route`, `alternatives`, `counterfactual_daily.*.planned_min`, `diff_daily.planned_min`, `daily.{unshiftable, transfer, next_day, evening_delivery_point}`; `time.json → alternatifler`; snapshot `plan.limits`, `plan.time_blocked`; `meta.time_example` (rota süresi artmamış, fazla mesaisiz, aynı rota içinde şartı öne alınır) ve `meta.time_example_constraint`; arm özetinde `route_minutes_per_day`.
7. **Ablasyon:** varyantlar `full_tol5` / `no_time_tol5` (tolerans +5 dk duyarlılığı) ve `unconstrained` / `no_time_unconstrained` (Faz 2b, eski); `time_contribution` çiftlerinde `tol5`, `unconstrained_2_b` ve ek sütunlar; varyant satırlarında `constraint_violation`, `constraint_max_min`, `constraint_max_km`, `unshiftable_day`, `transfer_day`.
8. **Dürüstlük:** kısıt ve alternatifler mekanizmadır; büyüklük simülasyonda ölçülür, gerçek veride saat boş olduğundan pilot ölçer. Eşikler ve tolerans VARSAYIM'dır.
9. **Testler:** `sim/tests/test_repair_limits.py` (7 hızlı); `sim/tests/test_anchored.py` güncellendi (pencere taşıması yalnız rota uzamıyorsa; değişiklik sayımı erteleme + servis düzeltmesini de sayar).

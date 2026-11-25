# Gereksinimler: Değerlendirme Ajanı, Bölge Ajanı ve ajan akışı

## Giriş

Sistem yalnız plan yapmaz; ertesi sabah kendi kararlarına bakar ve gerekeni düzeltir. Değerlendirme Ajanı hafıza kayıtlarını, süre tahminini ve atamayı gözden geçirir. Bölge Ajanı bilgiyi üç katmanda anlatır: durak (kapı kartı), küme (kuryenin sabah kartı), şube (müdürün zor blok haritası). Her ajanın yaptığı iş tek bir akışta görünür. Sözleşme: `docs/sozlesmeler.md` §12.

## Gereksinimler

### Gereksinim 1: Ajan akışı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, ajanların benim adıma ne yaptığını tek yerde görmek istiyorum.

#### Kabul kriterleri
1. WHEN bir ajan hafızayı değiştirdiğinde, soru açtığında, parametre ayarladığında ya da rapor sunduğunda THE SYSTEM SHALL akışa sıra numaralı bir olay yazmalıdır: ajan, tür, özet, durum.
2. THE SYSTEM SHALL akışa not metninin kendisini değil, Hafıza Ajanı'nın ayıklanmış sonucunu yazmalıdır.
3. WHEN müdür bir öneriyi onayladığında, reddettiğinde ya da bir düzeltmeyi geri aldığında THE SYSTEM SHALL olayın durumunu güncellemeli ve kararı ayrı bir olay olarak yazmalıdır.

### Gereksinim 2: Değerlendirme Ajanı
**Kullanıcı hikayesi:** Bir şube müdürü olarak, sistemin dünkü kararlarının işe yarayıp yaramadığını ve neyi düzelttiğini sabah bilmek istiyorum.

#### Kabul kriterleri
1. WHEN sabah değerlendirmesi çalıştığında THE SYSTEM SHALL son 5 günü önceki 5 günle karşılaştırmalı ve dört ölçünün yönünü bildirmelidir: ilk denemede teslim, yabancı sokakta başarısızlık, ipuçlu durakta başarısızlık, süre tahmini hatası.
2. WHEN ipucu gösterildiği halde bilgiyle ilgili nedenle teslim başarısız olduğunda THE SYSTEM SHALL ilgili kaydı şüpheli saymalıdır.
3. IF şüpheli kayıt tek kaynaklıysa ve en az iki kez çeliştiyse THEN THE SYSTEM SHALL kaydı düşürebilir; aksi halde yalnız teyide alır.
4. WHEN hafızası boş bir adreste en az iki günde bilgiyle ilgili başarısızlık tekrarlandığında THE SYSTEM SHALL oraya en son giden kıdemliye soru açmalıdır.
5. WHEN süre tahmini katsayıları sınama gününde hatayı düşürdüğünde THE SYSTEM SHALL katsayıları sınırlar içinde güncellemelidir.
6. THE SYSTEM SHALL atama değişikliğini yalnız öneri olarak sunmalıdır; müdür onaylamadan uygulanmaz.
7. THE SYSTEM SHALL bir günde en çok 12 otomatik eylem yapmalıdır; fazlası öneriye dönüşür.
8. WHEN müdür bir otomatik eylemi geri aldığında THE SYSTEM SHALL kaydı ya da parametreyi önceki haline döndürmelidir.
9. THE SYSTEM SHALL kuryeyi değil sistemin kararını değerlendirmelidir: kurye puanı, sıralaması ya da performans yargısı üretmez.

### Gereksinim 3: Bölge Ajanı
**Kullanıcı hikayesi:** Bir kurye olarak sabah kümemin zor yerlerini; bir müdür olarak şubede bilginin eksik olduğu blokları bilmek istiyorum.

#### Kabul kriterleri
1. THE SYSTEM SHALL blok zorluğunu, bloğun bilgi nedenli başarısız oranının (şube ortalamasına büzülmüş) şube ortalamasına oranı olarak hesaplamalıdır: en az 1,5 yüksek, en az 1,1 orta.
2. WHEN küme kartı istenirse THE SYSTEM SHALL kuryeye en çok dört kısa cümle vermelidir: kaç durak yeni sokakta, en önemli zorluk, kümede bilinen bilgi, hafıza boşluğu.
3. WHEN şube raporu istenirse THE SYSTEM SHALL zor blokları, hafızası boş zor blokları ve açılan soruları müdüre en çok dört cümleyle sunmalıdır.
4. THE SYSTEM SHALL soruyu yalnız hafızası boş zor bloğa açmalı; günde en çok 5 soru, aynı bloğa aynı gün en çok bir soru.
5. IF canlı yol tamamlanamazsa THEN THE SYSTEM SHALL aynı araçlarla kurallı yola düşmeli ve sonuçta `degraded: true` bildirmelidir.

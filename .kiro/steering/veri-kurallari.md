---
inclusion: always
---
# Veri, dürüstlük ve KVKK kuralları

## Veri izni (24 Kasım 2026)

- Şirket, saha verisinin (ham paket dahil) bu projede **her yerde** kullanılmasına izin verdi: simülasyon, ajanlar, arayüz ve sunum. Repo ham paketle birlikte şirket dışıyla (jüri, GitHub) paylaşılabilir; paketi ya da gerçek veri dosyalarını ayırmak gerekmez.
- İzinden bağımsız olarak süren kurallar:
  - **Şirket içi adlar:** Şirket içi sistem adları (mevcut çizelgeleme sistemi, dinamik planlama motoru, harita servisi), iç servis adresleri, şube kimliği ve gerçek bölge kodları koda, arayüze ve sunuma girmez (`sunum-dili.md` kural 1). `sim/tests/test_forbidden_content.py` bunu hackathon klasöründe denetler. Gerçek veri koda girerse bölgeler takma adlarla ("B01", "B02"…) anılır.
  - **KVKK** (aşağıda): Alıcı bilgisi ve kurye kimliği ekrana ve sunuma çıkmaz; hafıza kişiyi değil adresi anlatır.
  - **Etiket:** Gerçek veriden gelen her görünüm atfında "Gerçek veri" der. Simülasyon rakamları "Uygulama verisi · 1 aylık geçmiş" etiketini korur. Hangi dosyanın gerçek, hangisinin uygulama verisi olduğu `docs/veri-haritasi.md`'dedir.

## Bugünkü kullanım: uygulama verisi, gerçek harita

- Simülasyon ve ajanlar bugün uygulama katmanından gelen 1 aylık geçmiş veri ile çalışır. Ham kayıtlar (gerçek koordinat, barkod, kurye kimliği, bölge poligonu, rota, teslim kaydı) yalnız hikaye arayüzünün harita konumlarına girer (aşağıda "Gerçek harita"). İzin, ham veriyi simülasyona ya da ajanlara taşımayı serbest bırakır; taşınırsa bu bölüm ve `docs/veri-haritasi.md` güncellenir.
- Saha verisinden **türetilmiş, yuvarlanmış toplu değerler** uygulama verisini kalibre eder. Örnekler: günlük gönderi, durak başına gönderi, başarısızlık oranı, adres tekrar oranları, iş yükü sapması. Bu değerlerin tek yeri `sim/config/calibration.yaml`. Uyum `python -m cm_sim.calibration` ile raporlanır.
- Sunumda bu değerler "uygulama verisi, saha verisinin toplu özelliklerine kalibre edildi" diye anılır.
- Kalibrasyon hedefleri dışındaki parametreler (püf noktası etkileri, öğrenme, not eğilimi vb.) genel ve makul varsayımlardır; sağlamlık taraması bunları geniş aralıkta değiştirir.
- Ekonomi varsayımları (`agents/economics.yaml`) `ASSUMPTION` etiketlidir; sunumda şirket rakamı olarak gösterilmez.
- **Saha bilgisi (şube sahibinin beyanı):** mesai 09:00, bugünkü çıkış ~10:30, ayrıştırma okutmaya gömülünce ~09:30 (`sim/config/default.yaml → sabah`, Faz 5). Ölçülmüş veri değildir; VARSAYIM olarak sunulur, büyüklüğü pilot ölçer.

## Gerçek harita: hikaye arayüzünün konumları (ekip kararı)

- **Ne:** `ui-story/data/scene1.json` gerçek Beykoz verisinden türetilmiştir: 18 sabit bölge poligonu, yeni yapının 4–5 Mayıs 2026 dinamik bölgeleri ve o günlerin teslim noktaları (koordinatlar 4 haneye, ~10 m, yuvarlanmış). Sahne 2–5'te sim adresleri gerçek Beykoz teslim noktalarına deterministik eşlenir (`data/sim_mapping.json`, `data/scene2.json`): harita konumları gerçek, sonuçlar simülasyondur.
- **Neden:** Sorunun sahadaki karşılığı (sabit bölge ↔ dinamik bölge, yabancı sokak payı) yalnız gerçek haritada inandırıcı. Ekip bunu Faz 3b'de istisna olarak seçti; Faz 6'daki izinle istisna olmaktan çıktı.
- **Sınır:** Barkod, kurye kimliği/hash'i, bölge kodu, şube kimliği, iç servis adresi ve şirket içi sistem adları bu dosyalara girmez (`ui-story/tools/prepare.py` ayıklar; `sim/tests/test_forbidden_content.py` ad ve kimlikleri denetler, koordinatları denetlemez). Sahne 1 atfı "Gerçek veri", diğer sahneler "konumlar Beykoz saha verisi, sonuçlar simülasyon" der.
- **Ham paket:** Depo kökündeki `courier-memory-paket/` ham saha verisi ve şirket içi adlar içerir; hackathon klasörünün dışındadır ve yasaklı içerik denetimi onu taramaz. İzinle repoda kalır ve repoyla paylaşılabilir. Paketteki şirket içi adlar ham kaynağa aittir; koda, arayüze ve sunuma taşınmaz.

## Uygulama verisi ilkeleri

- **Gizli gerçek açıktır:** Her adresin püf noktaları, her kuryenin becerisi, her bloğun zorluğu simülatörde bilinir. Ajanların bunları veriden ne kadar doğru çıkardığı ölçülebilir.
- **Tekrar üretilebilirlik:** Aynı yapılandırma ve seed her zaman aynı sonucu verir.
- **Adil karşılaştırma:** Tüm kollar aynı talebi ve aynı rastgele sayıları kullanır (ortak rastgele sayılar, CRN). Kollar arasındaki fark gürültüden değil politikadan gelir.
- **Parametrelerin gerekçesi:** Her parametre `default.yaml` içinde gerekçesiyle belgelenir.
- **Etiket:** Arayüzde ve sunumdaki her grafikte "Uygulama verisi · 1 aylık geçmiş" etiketi görünür.

## Dürüstlük: simülasyon neyi kanıtlar

- Senaryoları fikri gösterecek şekilde seçmek serbesttir; demo bunun için var.
- Ama parametreleri biz seçtiğimiz için simülasyon **mekanizmayı** gösterir, etkinin **büyüklüğünü** kanıtlamaz. Sunumdaki dil buna göre kurulur: "Bu varsayımlar altında…".
- Sunumdaki her rakam bir çalıştırma kimliğine (yapılandırma + seed) bağlanır. "Bu rakam nereden?" sorusunun cevabı tek komuttur.
- **Sağlamlık taraması:** Ana varsayımlar geniş aralıkta değiştirildiğinde kolların sıralamasının değişip değişmediği raporlanır. Sunumun güçlü iddiası bu olur: "Varsayımı değiştirin, sıralama değişmiyor."
- Hafızanın çözemeyeceği başarısızlıklar modelde **vardır**: alıcı evde yok, adres hatalı girilmiş gibi. Simülasyon her başarısızlığı hafızaya bağlamaz.
- Gerçek etki ölçümü pilotun işidir: 4 hafta, A/B; dinamik rotaların yarısı hafızalı, yarısı hafızasız.

## KVKK ve çalışan verisi

- **Hafıza kişiyi değil adresi ve binayı anlatır.** Aşağıdakiler kaydedilmez:
  - alıcı adı, telefonu
  - sağlık, yaş, davranış yargısı ("huysuz adam")
- Kurye notlarına bilerek kişisel veri tuzakları konur. Hafıza Ajanı'nın bunları ayıkladığı demoda gösterilir.
- **Ses:** Metne çevrildikten sonra silinir. Notlar süreli saklanır.
- **Kurye–bölge uyumu:**
  - "Performans puanı" ve kurye sıralama tablosu yoktur. Uyum, kurye×blok düzeyinde ve bloğun genel ortalamasına göre ölçülür. Kuryeye tek bir puan verilmez.
  - Disiplin, prim ya da değerlendirme amacıyla kullanılmaz. Sadece atama önerisine girdidir.
  - Atama önerisinin son onayı insandadır ve gerekçesi okunabilir.
  - Kontrollü öğrenme rotasyonu: Kurye hafıza desteğiyle yeni bölgelere de gönderilir. Kimse kalıcı olarak "kötü rotaya" kilitlenmez.

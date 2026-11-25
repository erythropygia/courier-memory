---
inclusion: always
---
# Ürün: Courier Memory

## Bağlam

- **Şirket:** Aras Kargo (Türkiye, son-mil teslimat).
- **Geliştirme:** Kiro ile, spec odaklı.
- **Teslim:** çalışan demo **ve** sunum. İkisi de bu repodan çıkar.
- **Veri:** Her şey uygulama katmanından gelen 1 aylık geçmiş veri üzerinde çalışır (bkz. `veri-kurallari.md`).

## Problem

Her kuryenin kafasında yazılı olmayan bir bölge bilgisi var: "sitenin girişi arka sokaktan", "bu iş yeri cumartesi kapalı", "zil çalışmıyor, telefonla ara". Bu bilgi kişide yaşar. Aşağıdaki durumlarda kaybolur:

- **Dinamik planlama:** Bölgeler her sabah o günün gönderilerine göre yeniden çiziliyor. Kurye her gün aynı sokakta değil.
- **İzin, işten ayrılma, yeni kurye:** Bilgi kişiyle birlikte gidiyor.
- **Şubeler arası ödünç kurye:** Kuryenin yeni şubede bildiği adres sayısı tanım gereği sıfır.

Sonuç: ilk denemede teslim başarısı düşer, kapıda geçen süre uzar, aynı adrese ikinci sefer gidilir.

## Çözüm: birleşik sistem

Dinamik planlama motoru (kümeleme + rotalama) bağlamdır. Bu projede geliştirilmez, simülatörde basit bir benzeri çalışır. Üstüne dört ajan eklenir:

| Ajan | Görevi |
|---|---|
| **Orkestratör Ajanı** | Günü yönetir: hacmi okur, yoğunluğu ve kapasite açığını görür, açık kadar komşu şubeden kurye ister ("kim gitsin": bölge tanıklığı + hafıza kapsamı), çekirdek bölgeli atamayı ve riskli rotaları araçlarla hesaplatır, müdüre gerekçeli öneri sunar; müdür onaylar, reddeder ya da düzenler. Her adımı canlı iz olarak görünür (`docs/sozlesmeler.md` §5). |
| **Atama Ajanı** | Her sabah **çekirdek bölgeli dinamik planı** önerir: kümeler kuryelerin çekirdek bölgeleri etrafında kurulur, kurye kendi bölgesinde kalır, yalnız sınırlar ve fazla iş esner. İzinli, yeni ve ödünç kuryeyi yönetir. Kararını şube müdürüne gerekçesiyle anlatır, "ya şöyle olursa?" sorularını yanıtlar. Son onay insanda. |
| **Hafıza Ajanı** | Kurye notlarını (yazılı/sesli) ve teslim olaylarını adres bazında hafızaya çevirir. Notu adrese bağlar (hasat cevabında adres hazırdır: `address_id`), türünü ve geçerlilik süresini çıkarır; "12 ile 1.5 arası" gibi pencereleri yapılı alana (`window`) yazar, kişisel veriyi ayıklar, çelişkiyi çözer, bayat bilgiyi unutur. |
| **Hasat Ajanı** | Kuryenin bildiğini sistematik toplar. İki kaynak: (1) hafıza boşluğu: bugünkü planda bölgeye yabancı kuryenin gideceği, hafızası boş adreslere, o adresi bilen kıdemliye hedefli soru (kurye başına günde ≤ 3, şubede ≤ 30); (2) tekrarlayan başarısızlık: gün/saat örüntüsünden hipotez çıkarıp teyit sorusu yazar. Hipotez teyitsiz hafızaya yazılmaz. Cevap Hafıza Ajanı'ndan geçer. Demoda cevap simüle kıdemlidir (`SeniorSimulator`, açıkça etiketli). |
| **Brifing Ajanı** | Atama Ajanı'ndan "bu kurye şu bloklara yabancı" bilgisini alır. Müdürün onayladığı planı (yoksa simülasyon planını) ve hafızalı rotayı okur; dönüş saatini `EtaModel`'den alır, rota değişikliklerini söyler. İpuçlarını güne ve saate göre süzer (Cumartesi kapalı ipucu çarşamba söylenmez). Sabah brifingi ve kapıya yaklaşırken tek cümlelik ipucu verir. Kuryenin "hâlâ geçerli / değişmiş" geri bildirimini hafızaya döndürür. |

### İlke: kaydırmıyoruz, sınırı esnetiyoruz

"Kurye bir bölgede iyiyse neden kaydırıyorsunuz?" sorusunun cevabı yapının kendisidir:
- **Çekirdek bölge:** Her kuryenin geçmiş teslimatlarından öğrenilen bir çekirdek bölgesi vardır. Lojistikte "core area routing" olarak bilinen yaklaşım budur. Kurye her gün çekirdeğinde kalır; simülasyonda durakların ~%96'sında.
- **Esnek sınır:** Dinamik planlama kuryeyi değil sınırı ve fazla işi kaydırır. Hacim düşükse komşu çekirdekler birleşir; birleşen alanı kısmen tanıyan komşu alır. Hacim yüksekse yedek ya da ödünç kurye esnek kuşağa gider.
- **Zorunlu kaydırma:** İzin, ayrılma, yeni kurye, kampanya ve şubeler arası destek kaçınılmazdır. Courier Memory tam bu anlar için: bilgi kişiden adrese taşınır.
- **Performans puanı yok.** Belirleyici olan süreklilik (tanıdıklık) ve dengeli iş yüküdür.

### Değer: operasyon maliyeti

Kazanç yüzdeyle değil TL ve günlük adetle anlatılır. Bileşenler: kurye-gün, fazla mesai, başarısız teslim, km ve LLM maliyeti. Şelale şöyle ilerler: bugün → dinamik planlama (daha az kurye) → ajansız bilgi kaybı → Atama Ajanı (çekirdek bölge) → Hafıza + Brifing → sonuç. LLM maliyeti tasarrufun küçük bir kısmıdır; optimize senaryoda (önbellek + işe göre model) ihmal edilebilir düzeydedir.

**Sistemin tutkalı tek bir maliyet fonksiyonudur:**

```
beklenen_başarısızlık(kurye, küme) =
  Σ durak  P(başarısız | blok zorluğu, kurye×blok uyumu, [tanıdık VEYA hafızada geçerli not])
```

Hafızada geçerli notu olan durak, kurye o bloğu tanımasa da "güvenli" sayılır. Hafıza büyüdükçe atamanın serbestliği artar ve optimizasyon daha fazla verim çıkarır.

**Sunum cümlesi:** "Hafıza, optimizasyona serbestlik kazandırır."

### Hafıza planı ve rotayı değiştirir

Kol D artık C'nin rotasını kopyalamaz; hafıza kendi planını kurar (`cm_sim/routing_memory.py`):
- **Planda erteleme:** bugün kapalı bilinen durak (cumartesi kapalı, geçici kapalı) rotadan çıkar. Yalnız **en az iki bağımsız kaynakla** (tek kaynaklı kapanışın %38'i yanlıştı; yanlış erteleme teslimi kaçırır). Tek kaynaklı kapanış rotada kalır, brifingde "kapıda teyit edin" denir.
- **Servis süresi düzeltmesi:** bilinen püf noktasının kalan süresi (güvenlik, resepsiyon, arka giriş) kümelemeye ve ETA'ya girer.
- **Pencere onarımı:** öğle arası penceresine düşen varış, en az km artışıyla pencere dışına taşınır.
- Aynı fonksiyonları Orkestratör'ün `compute_route` aracı da çağırır: canlı hafıza simülasyonla aynıysa ajanın rotası kol D'nin yürüttüğü rotayla birebir aynıdır (test).
- Hafıza ayrıca **hasat** ile büyür (Hasat Ajanı, kol D'de plan sonrası).

### Teslim zamanı: ajan kalıbı kendi bulur

Sahibin itirazı: "bir müşteriye 10 ayrı gün hep 13:00'te gidip hiç teslim edemedik; ajan bunu analiz edip rotayı iyileştirmeli." Bunun için:
- Dünyada adres başına gizli bulunabilirlik profili var (evde, çalışan, dükkân, ofis, resepsiyon); yokluk durak düzeyindedir ve varış saatine bağlıdır.
- Ajan kayıtlardan (teslim saati + sonuç, notsuz) adres × zaman dilimi tablosu çıkarır ve kalıbı bulur ("12–14: 0/10 teslim · 16–18: 4/4 teslim → 16–18 öner"); güven seviyesi (yüksek/orta) ile rotaya alır; emin değilse hasatta kuryeye saat sorar. Rota, durağı iyi saate taşır (`repair_times`); hepsi `cm_sim.delivery_time` + `routing_memory` saf fonksiyonlarıyla, ajan = simülatör.
- **Dürüstlük notu:** gerçek Beykoz verisinde başarısızlık saati/nedeni boştur; bu etki gerçek veriyle kanıtlanamaz. Simülasyonda MEKANİZMA olarak gösterilir, büyüklüğünü pilot ölçer. Profiller ve paylar tahminidir; gösterilen adres seçilmiş örnektir, büyüklük `summary.time_analysis`'dedir.

### Onarım rotayı uzatmaz

Sahibin itirazı: zaman onarımı durağı akşama kaydırırken rotayı uzatıyor, fazla mesai yaratıyordu. Kural: **ajan mevcut rotadan daha uzun bir rota çıkarmaz.**
- Pencere ve zaman onarımı sert kısıtlıdır: beklenen rota süresi artmaz, km en fazla tolerans (0,5 km, yalnız öğle beklemesini kısaltan pencere taşımasında; zaman hamlesinde km hiç artmaz), vardiya bandı aşılmaz, durak vardiya bitişinden sonraya konmaz. Onarım fazla mesai satın almaz; beklenen başarısızlık "kazancı" kısıtı bozan hamleyi aklamaz.
- Kısıt yüzünden kaydırılamayan bulgu sessizce düşmez, **müdüre alternatif olur**: başka kuryenin rotasına aktarma, ertesi gün, akşam teslimi / teslim noktası; her birinde alıcıya önceden SMS önerisi. Karar müdürdedir; simülasyon alternatifleri uygulamaz, ölçülen etkide yoktur.
- Kısıt ve alternatifler `cm_sim.routing_memory` saf fonksiyonlarındadır; ajan = simülatör. Eşikler tahminidir, gerçek veride saat boş olduğundan büyüklüğü pilot ölçer.

### Sabah: ayrıştırma indirme okutmasında

Sahibin tespiti: mesai 09:00'da başlar ama kurye ~10:30'da çıkar (araçtan okutmalı indirme → kurye kendi gönderilerini ayrıştırır → zimmet → yükleme). Gönderiler ve kurye ataması araç gelmeden bellidir, rotalama 09:00'da hazırdır. Ayrıştırma kalkarsa çıkış en geç ~09:30 olur.
- **Mekanizma:** ayrıştırma indirme okutmasına gömülür: okutulan gönderi için ekranda "raf · kurye · yükleme sırası" (son durak önce yüklenir). Kurye rafını zimmetler, yükler, çıkar. Dinamik planlamada bu zorunludur: bölgeler her sabah değiştiği için kurye kendi alanının gönderilerini ezbere ayıramaz (hafıza problemiyle aynı kök).
- **Ajanın rolü (dürüst):** paket başına talimat plandan çıkan bir tablodur (LLM yok). Ajan planın sabaha hazır olmasını, raf ve yükleme sırasını (`sorting_plan`) ve istisnaları (planda olmayan gönderi → "esnek" raf; bugün kapalı bilinen adres → ertesi gün rafı) yönetir.
- **Ölçüm:** simülasyonda çıkış = mesai başı + sabah süresi; fazla mesai vardiya bitişinden (17:48) sayılır. Kol D'nin aynı rotası bugünkü sabahla karşı-olgu olarak yürütülür; ekonomide ayrı kalem. Süreler şube beyanıdır, büyüklüğü pilot ölçer. Çıkış 10:30'a çekilince bulunabilirlik profili yeniden kalibre edildi (kalibrasyon 14/14).
- **Ayrım:** hafızanın katkısını ölçen deneyler (tarama, Hedef 1, ablasyonun hafıza varyantları) sabahı tüm kollarda eşit tutar; "hafızanın katkısı" iddiaları sabahı içermez.

### Durak bilgi kartları

Kuryenin bıraktığı bilginin hepsi rotayı değiştirmez: "arabayı köşedeki eczanenin önüne bırak", "asansör yok, 5. kat", "bahçede köpek var". Bunlar **bilgi türleri**dir (park, bina erişimi, adres tarifi, hayvan, diğer): hafızaya yazılır, plana ve rotaya girmez, kuryeye **durak kartı** olarak verilir.
- Kartın anı vardır: park ve tarif bilgisi **durağa yaklaşırken** (400 m), zil/kat/köpek bilgisi **kapıda** (60 m). Bir anda en çok iki cümle (sürüş güvenliği).
- Kart kaynağını söyler: kaç kuryeden geldi, en son ne zaman teyit edildi. Tek kaynaklı bilgi "teyitsiz" görünür.
- **Kapı/bina şifresi asla kaydedilmez:** kişisel veri değildir ama sızarsa binaya erişim verir. Araç düzeyinde reddedilir.

### Sistemin kendini değerlendirmesi

- **Değerlendirme Ajanı** her sabah son 5 günü önceki 5 günle karşılaştırır. Kuryeyi değil **sistemin kararlarını** değerlendirir: ipucuna rağmen başarısız olan kaydı teyide alır ya da (tek kaynak + ≥ 2 çelişki) düşürür, hafızası boş tekrarlayan soruna kıdemliye soru açar, süre tahminini sınırlı ayarlar. Atama değişikliği yalnız öneridir, müdür onaylar. Her eylem geri alınabilir.
- **Bölge Ajanı** bilgiyi üç katmanda anlatır: durak (kapı kartı), küme (kuryenin sabah kartı), şube (müdürün zor blok haritası). Hafızası boş zor bloklar için kıdemliye soru açar (günde ≤ 5).

### Dürüst iddialar

- Hafızanın rotaya katkısı **küçük** ve böyle raporlanır: ilk denemeye katkı yok; değeri fazla mesai, bekleme (öğle penceresine varış, boşuna gidiş) ve +%1 km. "Rota kaliteyi artırır" denmez.
- Sağlamlık manşeti "D ≥ C ≥ B %100" **değildir**. Yerine aralıklar: D − A ve D − C farkı, kombinasyonlar boyunca en düşük … en yüksek (`sweep.headline`). D − A ilk denemede ±0,15 puan içinde kalır (kalite bugünkü düzeyde), kazanç maliyettedir.
- Gerçekleşen vardiya bandı payı modele duyarlıdır (`known_minutes`, `lunch_wait_max` tahmini); planlanan bantla birlikte söylenir.
- Hasat cevabı simülasyonda kıdemlinin gizli bilgisinden gelir; gerçek cevap oranı ve doğruluğu bilinmiyor (`p_answer` tahmini).

### Hedefler (analizden)

1. **Yeni kurye daha hızlı öğrenir:** yüzde yerine "bilgiyle önlenebilir başarısız / 100 durak", kuryenin kaçıncı iş günü olduğuna göre (`cm_sim.learning`, senaryo `hiring`, 12 seed). Manşet: ilk hafta eşli fark.
2. **"Kim gitsin" gerçek bir karar:** komşu şube kuryeleri ortak sınır sokaklarını kendi şubelerinden dağıtır; adayların tanıdık payı farklıdır, eşitlik çıkmaz (gün 32, alacağı kümede tanıdık durak: Onur %100 > Gökhan %64 > Melis %0; `docs/sunum_rakamlari.md` → "Kim gitsin").
3. **Hafıza rotayı değiştirir:** yukarıdaki üç adım; aynı rota hafızasız / yalnız ipucu / hafızalı yürütülerek ayrıştırılır (karşı-olgu).

## Kullanıcılar

- **Şube müdürü:** Sabah atama önerisini görür, gerekçeyi okur, senaryo sorar, onaylar.
- **Kurye:** Brifingi dinler, kapıda tek cümle duyar, 3 saniyelik not bırakır, tek tuşla doğrular. Sürerken ekrana bakmaz; yalnızca ses.
- **Yönetim:** Simülasyon panosunda kolları karşılaştırır, parametreleri kaydırıcılarla değiştirir.

## Demo hikayesi (sırayla)

Demo ve sunum aynı ekrandır: hikaye arayüzü (`ui-story/`, http://localhost:8000), 8 sahne, sunucu → ile ilerler; sunumun tamamı bu ekrandır. Ayrıntılı metin `docs/sunum.md` → "Demo metni".

1. **Sorun ve ilke:** açılış ("Sitenin girişi arka sokaktan"), gerçek Beykoz verisiyle sorun, ardından ilke (kaydırmıyoruz, sınırı esnetiyoruz) ve ajanlar + tek maliyet. Sorun kısmı: 18 sabit bölge → yeni yapının dinamik bölgeleri (daha az kurye, daha az yol) → ertesi gün bölgeler yeniden çizilir → geçmişe bakmadan atamada durakların çoğu kuryeye yabancı sokakta.
2. **Sabah (gün 32, kampanya, +%31 hacim):** Orkestratör günü planlar; her araç adımı canlı izde ve haritada: hacim → kapasite açığı 2 → "kim gitsin" (Onur, Gökhan; Melis değil) → çekirdek bölgeli atama → teslim zamanı bulguları → rota kontrolleri → müdüre öneri.
3. **Onay:** Müdür gerekçeyi ve riskleri okur (bant üstü rotalar; kısıt yüzünden kaydırılamayan bir teslim saati için akşam teslimi + SMS önerisi), "Onur gelmezse ne olur?" diye sorar; ajan iki yolu araçla hesaplar. Müdür onaylar (izde İNSAN).
4. **Kapıda:** Gökhan'ın sabah brifingi; rota oynatılır, notlu kapıda tek cümle ve "hâlâ geçerli"; Gökhan kişisel veri içeren bir not bırakır, Hafıza Ajanı ayıklar ve adrese bağlar; günler sonra aynı adrese giden Mehmet'in brifinginde bu not çıkar. Aynı rota hafızasız 457 dk ↔ hafızalı 414 dk.
5. **Hasat:** Hasat Ajanı günün sorularını çıkarır; Gökhan'ın rotasındaki boş adres için kıdemliye sorulur (simüle cevap, etiketli) → hafıza → rota planı değişir; saat teyidi bir teslimi doğru saate taşır; kayıtlardan "bu adreste öğlen kimse yok" kalıbı rotayı uzatmadan düzeltir.
6. **Öğrenme:** Yeni kuryenin ilk haftası (hafızalı ↔ hafızasız), dört yapı gün gün ve başarısızlık nedenleri, parametreleri değiştirin (81 kombinasyon: D − C her yerde pozitif), kalibrasyon 14/14, hafızanın parça parça katkısı.
7. **Değer:** Operasyon maliyeti şelalesi (TL), dört yapı yan yana, ölçek, LLM maliyeti temkinli ↔ optimize (ajan başına model seçilebilir), parametre kaydırıcıları.
8. **Kapanış:** AWS + Kiro ile nasıl yapıldı, sorumlu yapay zekâ, pilot (4 hafta, tek şube, A/B), tek cümle.

## Öncelik katmanları

Süre belirsiz. Her katman kendi başına sunulabilir olmalı. Önce P0 baştan sona biter, sonra P1'e geçilir.

- **P0, olmazsa olmaz:**
  - Dünya ve simülatör (4 kol)
  - Orkestratör Ajanı (gün akışı, komşu şubeden kurye kararı, insan onayı, canlı iz)
  - Atama Ajanı (araçlarla, gerekçe ve senaryo sorusu)
  - Hafıza Ajanı (yazılı not)
  - Hasat Ajanı (hafıza boşluğu ve hipotez soruları; mock kurallı yedek + simüle kıdemli cevabı)
  - Brifing Ajanı (tek cümle, tarayıcı sesi)
  - Demo arayüzü (harita, kaydırıcılar)
  - Sunum
- **P1:**
  - Amazon Polly sesi
  - Amazon Transcribe ile sesli not
  - DynamoDB'de hafıza
  - Ajanları Bedrock AgentCore Runtime'da barındırma
  - "Hâlâ geçerli mi?" geri bildirim döngüsü
- **P2:**
  - Amazon Location geofence ile kapıya ~150 m kala tetik
  - EventBridge ile teslim olay akışı
  - Kontrollü öğrenme rotasyonu
  - İki şubeli tam simülasyon (bugün: komşu şube aday havuzu + karar aracı)

## Spec yol haritası

Altı spec, bu sırayla (`.kiro/specs/`):

1. `dunya-simulator`: Dünya, simülatör, deterministik politikalar, hafıza-farkında rota, hasat, karşı-olgu, öğrenme ve ablasyon deneyleri, metrikler, kalibrasyon. Diğer her şey bunun üstüne kurulur.
2. `agents`: Atama, Hafıza, Brifing ve Hasat ajanları; `mock / live / record / replay`.
3. `orchestrator`: Günü yöneten Orkestratör Ajanı, ajan izi, rota aracı, insan onayı ve akış uç noktaları.
4. `economics`: Token ölçümü ve TL ekonomi hesabı.
5. `api-arayuz`: FastAPI ve demo arayüzü (hikaye: Gereksinim 7).
6. `sabah-akisi`: şubede sabah; ayrıştırma indirme okutmasında, çıkış saati, simülatör + ajan + API + arayüz + ekonomi.

Sunum metni `docs/sunum.md` içindedir; ayrı spec değildir.

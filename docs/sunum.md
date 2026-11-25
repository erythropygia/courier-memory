# Sunum taslağı, demo metni ve olası sorular

> **Rakamların tek kaynağı:** `docs/sunum_rakamlari.md`. `python -m agents.presentation_figures` ile verilerden otomatik üretilir. Aşağıdaki değerler bugünkü verinin örnekleridir; canlı ölçümden sonra güncellenir.
>
> Tüm rakamlar **uygulama verisi (1 aylık geçmiş)** sonucudur ve kaynakları (tahmini parametre, şube beyanı) belirtilerek sunulur. Uygulama verisi, saha verisinden türetilmiş toplu hedeflere kalibre edilmiştir (14/14). Kurye-gün ve başarısız teslim maliyetleri tahmini parametredir.

## Tek cümle

**Dinamik planlamaya ajansız geçmek sahada maliyeti artırır; Courier Memory ile aynı geçiş, kaliteyi koruyup şube başına yılda milyonlarca lira tasarruf sağlar. Kuryeyi kaydırmıyoruz, sınırı esnetiyoruz.**

## Akış (8 dk sunum + 5 dk demo)

| # | Slayt | Mesaj | Görsel | Hikaye (sahne/adım) |
|---|---|---|---|---|
| 1 | **Courier Memory** | "Sitenin girişi arka sokaktan." Bu bilgi bir kuryenin kafasında. | — | 1/0 |
| 2 | **Bugün: sabit bölge** | Kurye bölgesini tanır, kalite iyi. Ama bölgeler yıllar önce çizildi; talep kaydı. Bazı kuryeler fazla mesaide, bazıları erken bitiriyor; zirve için fazladan kurye tutuluyor. | Bugün sütunu: kurye/gün, vardiya bandında %33, iş yükü sapması | 1/1–2 |
| 3 | **Geçiş: dinamik planlama** | Daha az kurye ve dengeli iş yükü. Ama kurye geçmişe bakılmadan atanırsa bölge bilgisi kaybolur: başarısız teslim ve fazla mesai patlar. | "Yeni yapı, ajansız" sütunu (risk) | 1/3–5 |
| 4 | **Kaydırmıyoruz, sınırı esnetiyoruz** | Çekirdek bölgeli dinamik plan: kurye kendi bölgesinde kalır, yalnız sınır ve fazla iş esner. Kaydırma yalnız zorunlu anlarda. | Kendi bölgesinde durak payı: bugün %97, ajansız %63, **Courier Memory %96** | 1/6 |
| 5 | **Zorunlu anlar için hafıza** | İzin, ayrılma, yeni ve ödünç kurye: bilgi kişiden adrese taşınır, kapıda tek cümleyle geri verilir. | Üç ajan + tek maliyet şeması | 1/7 |
| 6 | **Canlı demo** | Aşağıdaki metin | — | 2–5 |
| 7 | **Değer: operasyon maliyeti şelalesi** | Bugün → daha az kurye → ajansız bilgi kaybı → Atama Ajanı geri kazanır → Hafıza + Brifing → Sabah (ayrıştırma okutmada) → sonuç | Şelale (TL/gün ve TL/yıl) | 7/1 |
| 8 | **Üç durum yan yana** | Aynı gönderiler, üç yapı | Tablo: kurye, kendi bölgesinde, başarısız teslim, fazla mesai, TL/gün, gönderi başı TL, yıllık fark | 7/2 |
| 9 | **Token maliyeti** | LLM maliyeti tasarrufun küçük bir kısmı. Optimize senaryoda (önbellek + işe göre model) ihmal edilebilir. | Temkinli ↔ optimize: TL/gün, kuruş/gönderi, tasarrufa oranı | 7/4 |
| 10 | **Parametreleri değiştirin** | Sağlamlık taraması, 81 kombinasyon: D − A ilk denemede +0,00 … +0,31 puan (medyan +0,09; %78'i ±0,15 içinde, hiçbirinde negatif değil), kurye-gün −%6,6 … −%8,0; hafızanın katkısı (D − C) +0,18 … +0,53 puan, her kombinasyonda pozitif | D − A ve D − C aralıkları (`sunum_rakamlari.md` → Sağlamlık). "D ≥ C ≥ B" önemsiz, kullanmayın | 6/2 |
| 11 | **AWS + Kiro ile nasıl yaptık** | Bedrock'ta Claude (araç kullanan ajanlar), Polly, (P1) DynamoDB / AgentCore. Kiro: steering, altı spec, kabul testleri. `.kiro/` klasörünü gösterin. | 104 test (99 hızlı + 5 yavaş) | 8/0 |
| 12 | **Sorumlu yapay zekâ ve pilot** | Kişi değil adres; kişisel veri araç düzeyinde reddedilir; performans puanı yok, son karar müdürde. Pilot: 4 hafta, tek şube, A/B. | — | 8/1–3 |

**Örnek değerler (uzun dönem, şube başına):**

| | Bugün (sabit bölge) | Yeni yapı, ajansız | Yeni yapı + Courier Memory |
|---|---|---|---|---|
| Kurye/gün | 22,3 | 20,1 | 20,1 |
| Kendi bölgesinde durak payı | %97 | %63 | %96 |
| Önlenebilir başarısızlık (60 gün) | 1.981 | 5.645 | 1.847 |
| Vardiya bandında (gerçekleşen süre) | %33 | %5 | %45 |
| Fazla mesai dk/gün | 739 | 3.572 | 612 |

(Dünya modelinde bilinen öğle arası pencere içinde bedava değildir; bilinen püf noktasının kalan süresi vardır. Planlanan bant ve kalibrasyon bundan etkilenmez.)

Operasyon maliyeti TL/gün, gönderi başı TL ve yıllık fark için `sunum_rakamlari.md` dosyasına bakın.

**Ekonomi slaytları (7–9) nasıl anlatılır:**
1. **Yüzde değil para.** "İlk denemede teslim %96,8 ↔ %96,9" demeyin. "Günde X başarısız teslim, Y saat fazla mesai, Z TL" deyin.
2. **Şelalenin hikayesi.** Dinamik planlamanın kurye tasarrufu ajansız geçişte bilgi kaybıyla fazlasıyla geri gider. Atama Ajanı'nın çekirdek bölgeli planı bunu geri kazanır; Hafıza + Brifing kalanı kapatır.
3. **Temkin.** Tasarrufun çoğu kurye-gün maliyetinden gelir ve bu maliyet tahminidir; kaydırıcıyla gösterin. Km tasarrufu iddia etmiyoruz: simülasyon coğrafyasında oluşmuyor.
4. **Token.** Temkinli senaryoda (Opus 5.5, önbelleksiz; Orkestratör, senaryo soruları, Hasat ve hasat cevapları dahil) LLM maliyeti tasarrufun ~%2–3'ü. Optimize senaryoda (önbellek, Hafıza/Brifing/Hasat Haiku 5.5, Atama/Orkestratör Sonnet 5.5) %0,2 civarı. Kalite iddiası canlı değerlendirmeyle desteklenir.

## Demo metni: hikaye arayüzü (8 sahne)

Demo ve sunum aynı ekrandır: http://localhost:8000 (→ `/story/`). Sunucu → / boşluk ile adım adım ilerler, ← geri, 1–8 sahne, R sahneyi baştan, A açıklama satırı (her adımda "Ne oluyor · Ekranda · Veri"; izleyici sahneyi kendi de okuyabilir); adres `#sahne/adım` (adım 0'dan sayılır). **Sunumun tamamı bu ekrandır:** yukarıdaki akış tablosunun son sütunu her slaytın sahnesini ve adımını verir; ayrı slayt dosyası gerekmez. API yoksa sahneler kayıtlı yanıtla oynar (rozet "API yok · kayıtlı yanıt"). Rakamlar bugünkü verinin örnekleridir; değişirse `sunum_rakamlari.md` ve ekrandaki değer geçerlidir.

1. **Sorun ve ilke (2 dk).** *Açılış (1/0):* sokak düzeyinde Beykoz, "Sitenin girişi arka sokaktan. Bu bilgi bir kuryenin kafasında." *Sorun (1/1–5, gerçek Beykoz verisi):* 18 sabit bölge, 21 kurye → yeni yapının dinamik bölgeleri: 19 kurye, 5 günde araç-gün −%17, yol −%31. Ertesi gün bölgeler yeniden çizilir. Kurye geçmişine bakılmadan atanırsa durakların ~%87'si kuryeye yabancı sokakta (bugün %4). "Verimlilik geliyor, ama kuryenin bilgisi kayboluyor." *İlke (1/6, uygulama verisi):* "Kuryeyi kaydırmıyoruz, sınırı esnetiyoruz": kendi bölgesinde durak payı bugün %97, ajansız %63, Courier Memory %96. *Ajanlar (1/7):* zorunlu anlar (izin, ayrılma, yeni ve komşu şubeden kurye, kampanya) → Orkestratör + dört ajan (araç adlarıyla) → tek maliyet fonksiyonu: "Hafıza, optimizasyona serbestlik kazandırır."
2. **Sabah (60 sn, gün 32, Çarşamba, kampanya).** "Günü planla" → Orkestratör izi canlı (rozet: mod). Hacim 3.668 gönderi (+%31) → 26 kurye-gün gerekli, yerelde 24: açık 2 → "kim gitsin": Onur (alacağı kümede durakların %100'ünü tanıyor), Gökhan (%64), Melis (%0); eşitlik yok → çekirdek bölgeli atama (%94 kendi bölgesinde) → teslim kayıtlarından 11 durakta "şu saatte kimse yok" kalıbı rotaya girdi (rota uzamadan) → rota kontrolleri → ayrıştırma planı (26 raf, çıkış 10:30 → 09:30) → müdüre öneri.
3. **Onay (60 sn).** Gerekçe paneli. Riskler: 14 kurye bant üstünde (ilk 3 haritada), 2 durağın teslim saati kural yüzünden aynı rotada kaydırılamadı → akşam teslimi / teslim noktası + alıcıya SMS önerisi, karar müdürde. Soru çipi "Onur gelmezse ne olur?": ajan iki yolu araçla hesaplar: (1) Melis gelir: beklenen başarısız +1,6, bant üstü +32 dk; (2) kimse gelmez: bant üstü +511 dk. Serbest soru da sorulabilir ("Onur yerine Melis giderse?"). **ONAYLA** → izde İNSAN satırı. *Sabah (3/5, 08:30 araç geldi):* indirme okutmasında her gönderi için "raf · kurye · yükleme sırası" (son durak önce); planda olmayan gönderi "esnek" rafa, müdür ekranına; ortalama çıkış 09:33 ↔ bugünkü süreç 10:33 (−60 dk). "Kurye ayrıştırma yapmıyor; paket başına talimat plandan, ajan istisnayı yönetir. Süreler saha bilgisi, pilot ölçer."
4. **Kapıda (2 dk).** Gökhan'ın telefonu: "Bugün 45 durak, 59 gönderi; tahmini dönüş 13:29; 16 durakta bölgeyi ilk kez görüyorsun, bunların 7 tanesinde hafızada not var." (09:30 çıkıştan) → Rota oynar (yabancı duraklar rotanın sonunda); notlu kapıda tek cümle sesli, "✓ Hâlâ geçerli". 31. durakta Gökhan not bırakır: "zil bozuk Ayşe hanım çok huysuz telefonla arayın" → Zil, **kişisel veri ayıklandı**, hafızaya "Zil çalışmıyor; alıcıyı telefonla arayın." (Gürültü çipi kaydedilmez; izleyici kendi notunu yazabilir.) → Gün 35: aynı adrese Tolga gidiyor, 74. durakta bu cümle brifinginde. → "Gökhan bu sokağı hiç görmedi, ama sokak onu tanıyor": aynı rota hafızasız 352 dk → hafızalı 312 dk (−40 dk; tek rota; ödünç kuryelerde ortalama 57 dk, p10–p90 35–78).
5. **Hasat (60 sn).** "Bugünün soruları": 21 hafıza boşluğu, 3 hipotez, 5 saat teyidi (kurye başına ≤ 3, şubede ≤ 30). Gökhan'ın rotasındaki boş adres için kıdemliye (Tolga) soru → **simüle kıdemli**: "Gönderileri resepsiyona bırakıyoruz" → Hafıza Ajanı: Resepsiyon → planlanan süre 214 → 215 dk. Saat teyidi: "akşam 5'ten sonra evdeler" (İbrahim'in rotası) → aynı rotada 16–18'e kaydırmak rotayı en az +11 dk uzatırdı → kural (rota uzamaz) → müdüre alternatif (başka kurye / ertesi gün + SMS). Kayıtlardan, notsuz: bir iş yerinde 12–14 arası 1/3, 14–16 arası 6/6 teslim → gün 34'te 12:52 (alıcı yok) yerine 14:53 (teslim); planlanan rota süresi −0,3 dk.
6. **Öğrenme (45 sn).** Yeni kuryenin ilk haftası: hafızayla kurye başına 7,5 [5,2–9,8] önlenebilir başarısız daha az (ana rakam). Kıdemli düzeyine C 14, D 10 günde; eşik ölçüsü sınırda hassas, öne çıkarmayın. Parametreleri değiştirin: 81 kombinasyonda D − C hep pozitif, D − A kalite bugünkü düzeyde. Hafızanın parça parça katkısı: önlenebilir başarısızdaki düşüş kapıdaki ipucundan; rota ve teslim zamanı fazla mesaiyi azaltır. *Soru gelirse:* "Dört yapı, gün gün" (ajansız geçişte önlenebilir nedenler artar) ve kalibrasyon 14/14 tablosu.
7. **Değer (60 sn).** "Şube başına günde 16.604 TL, yılda 5,1 milyon TL"; başarısız teslim 96 → 89/gün; ajansız aynı geçiş günde +35.862 TL. Şelale: sabah ayrı kalem (10.179 TL/gün, neredeyse tamamı fazla mesai; süreler şube beyanı), hafıza + brifing kendi kalemi. Dört yapı yan yana. Temkinli ↔ Optimize: LLM 228 → 19 TL/gün (tasarrufun %1,4'ü → %0,1'i). Kaydırıcı: "Kurye-gün maliyetini değiştirin" (tahmini parametre). *Soru gelirse:* ölçek (1/10/100 şube) ve ajan başına model seçici.

8. **Kapanış (2 dk).** *AWS + Kiro (8/0):* Bedrock'ta Claude, beş ajan araç kullanarak; dört mod aynı iz; ajan başına model (tablo `/api/status`'dan canlı); Polly; sırada DynamoDB, AgentCore, Transcribe. Kiro: 5 steering, 6 spec (gereksinim → tasarım → 83 görev), 104 kabul testi, 408/408 birebir rota, yeniden kurulum kiti; `.kiro/` klasörünü açın. *Sorumlu yapay zekâ (8/1):* kişi değil adres, performans puanı yok, son karar insanda, dürüst rakam. *Pilot (8/2):* 4 hafta, tek şube, A/B (rotaların yarısı hafızalı); ilk iş başarısız teslimde saat/neden alanı. *Son (8/3):* "Kuryeyi kaydırmıyoruz, sınırı esnetiyoruz. Bilgi kişiden adrese taşınır." + 5,1 mn TL/yıl, 96 → 89.

**Prova notları:** Sahne 2 her başladığında canlı hafızayı sıfırlar (tekrarlar aynı başlar). Canlı modda Orkestratör 30–60 sn sürebilir; iz paneli bekleme noktalarını gösterir. Ses yoksa (`/api/speech` 501) tarayıcı sesi kullanılır; tarayıcıda Türkçe ses yoksa cümle yine ekranda büyük yazılıdır. Eski tek sayfa ayrıntı ekranları `/legacy` adresindedir ("şu kurye?" sorusu gelirse).

## Olası sorular ve cevaplar

1. **"Kurye bir bölgede iyiyse neden kaydırıyorsunuz? Dinamik planlamanın anlamı ne?"**
   - Kaydırmıyoruz. Çekirdek bölgeli dinamik planda kurye kendi bölgesinde kalır; simülasyonda durakların %96'sında, sabit bölgedeki %97'ye çok yakın.
   - Dinamik planlama kuryeyi değil **sınırı ve fazla işi** kaydırır. Pazartesi hacim yüksek, cumartesi düşük, kampanyada +%30; sabit sınır bunu karşılayamaz, bu yüzden bugün bazı kuryeler fazla mesaide, bazıları erken bitiriyor.
   - Esnek sınırla aynı iş günde ~2 kurye daha azla ve dengeli iş yüküyle yapılıyor.
   - Kaydırma yalnız zorunlu anlarda olur (izin, ayrılma, yeni kurye, kampanya, şubeler arası destek); hafıza tam bu anlar için.
2. **"Bu rakamlar gerçek mi?"**
   - Uygulama katmanından gelen 1 aylık geçmiş veri, saha verisinin toplu özelliklerine kalibre (14/14): hacim, adres tekrar oranları, başarısızlık oranı, iş yükü dağılımı ve dinamik geçişteki kurye ve vardiya bandı farkları.
   - Ham veri kullanılmadı. Büyüklüğü 4 haftalık A/B pilotu ölçer.
3. **"Ajansız geçiş gerçekten bu kadar kötü mü?"**
   - "Geçmişe bakmadan atama" en kötü durumdur. Gerçekte müdür kısmen sezgiyle atar, gerçek kayıp bu ikisinin arasındadır.
   - Manşet tasarruf ise ajansız senaryoya değil bugüne göre hesaplanır.
4. **"Token maliyeti?"**
   - Temkinli senaryoda tasarrufun ~%1,4'ü (230 TL/gün). Optimize senaryoda (önbellek + işe göre model) %0,1 (19 TL/gün).
   - Canlı ölçüm `data/usage.jsonl`'e yazılır; tahmin yerine ölçüm gösterilir.
5. **"Küçük model kaliteyi düşürmez mi?"**
   - Hafıza Ajanı'nın işi kalıplıdır (adres bul, tür çıkar, kişisel veriyi ayıkla); hesap araçlarda.
   - Her modeli aynı kurye notlarıyla ölçüyoruz: `CM_MODEL_MEMORY=... python -m agents.evaluate`. Model, ölçülen doğruluğa göre seçilir.
6. **"Km?"** Simülasyon coğrafyasında dinamik plan km'yi belirgin değiştirmiyor; km tasarrufu iddia etmiyoruz.
7. **"Kuryeler not bırakır mı?"**
   - Temkinli tahmin: karşılaşmaların ~%29'u nota dönüşür.
   - Hafıza ayrıca teslim kayıtlarından öğrenir.
   - Kaydırıcıyla not eğilimini yarıya indirin: sıralama değişmez.
8. **"KVKK?"** Kişi değil adres. Ad, telefon, yaş, sağlık ve yargı araç düzeyinde reddedilir; ses metne çevrildikten sonra silinir.
9. **"Performans izleme mi?"** Hayır. Belirleyici süreklilik (tanıdıklık) ve dengeli iş yükü; kurye puanı ve sıralaması yok; son karar müdürde.
10. **"Gerçek sisteme entegrasyon?"**
    - Çekirdek bölge, mevcut dinamik planlamanın kümeleme adımına tanıdıklık terimi olarak eklenir.
    - Hafızadaki zaman pencereleri planlamaya kısıt olarak girer.
11. **"Kiro'yu nasıl kullandınız?"** Steering, 11 spec, skill'ler, hook'lar ve projenin MCP sunucusu; kabul testleri (147 test).
12. **"Sabah bir saat nereden çıkıyor? Bunu ajan mı yapıyor?"**
    - 09:00 mesai, ~10:30 çıkış, ayrıştırma kalkınca ~09:30: şube beyanı. Pilotun ilk ölçüsü zimmet okutmasının zaman damgası.
    - Mekanizma bir süreç değişikliği: ayrıştırma indirme okutmasına gömülür, ekranda "raf · kurye · yükleme sırası". Dinamik planlamada zorunlu: bölgeler her sabah değiştiği için kurye kendi gönderisini ezbere ayıramaz.
    - Paket başına talimat plandan çıkan bir tablodur, LLM yok. Ajan planı sabaha hazır eder, raf ve yükleme sırasını kurar, istisnaları yönetir (planda olmayan gönderi "esnek" rafa, bugün kapalı bilinen adres ertesi gün rafına).
    - Ölçülen: aynı rotalar bir saat erken başlayınca vardiya içinde biter; fazla mesai yaklaşık yarıya iner. Teslim kalitesine etkisi belirsiz, iddia etmiyoruz. Açılan kapasite paraya çevrilmedi.

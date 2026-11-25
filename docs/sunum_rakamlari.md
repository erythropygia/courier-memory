# Sunum rakamları (otomatik üretildi)

> Kaynak: `data/demo_run/` · çalıştırma `leave_wave+turnover+borrowed_courier+volume_shock-s42-00e214fe` · **Uygulama verisi · 1 aylık geçmiş**; tahmini parametrelerle.

## Uzun dönem (60 iş günü): manşet

| Kol | İlk denemede teslim | Bilgiyle önlenebilir başarısızlık | Kurye/gün | Vardiya bandında | İş yükü sapması | Hafıza kapsamı |
|---|---|---|---|---|---|---|
| A · Mevcut yapı · sabit bölge | %96,58 | 2.046 | 22,3 | %33 | %33 | %0,0 |
| B · Yeni yapı · geçmişe bakmadan atama | %94,38 | 5.651 | 20,1 | %5 | %16 | %0,0 |
| C · Yeni yapı · çekirdek bölgeli dinamik plan | %96,51 | 2.221 | 20,1 | %46 | %20 | %0,0 |
| D · Yeni yapı · çekirdek bölge + hafıza | %96,82 | 1.799 | 20,2 | %43 | %20 | %21,5 |

- C ← B (uyumlu atama): ilk denemede teslim +2,13 puan, önlenebilir başarısızlık −%60,7
- D ← C (hafıza + brifing): +0,31 puan, önlenebilir başarısızlık −%19,0
- D ← A (yeni yapı + hafıza vs mevcut yapı): araç-gün −%9,4, ilk denemede teslim +0,23 puan
- B ← A (yeni yapı, ajansız): ilk denemede teslim -2,20 puan

**Manşet cümlesi:** Yeni yapı + Courier Memory, mevcut yapının ilk denemede teslim kalitesini (%96,6 → %96,8) %9 daha az kuryeyle ve dengeli iş yüküyle (iş yükü sapması %33 → %20; vardiya bandında %33 → %43) korur.

## Demo dönemi (20 iş günü, senaryolar: leave_wave, turnover, borrowed_courier, volume_shock)

| Kol | İlk denemede teslim | Bilgiyle önlenebilir başarısızlık | Kurye/gün | Vardiya bandında | İş yükü sapması | Hafıza kapsamı |
|---|---|---|---|---|---|---|
| A · Mevcut yapı · sabit bölge | %96,13 | 922 | 22,3 | %30 | %36 | %0,0 |
| B · Yeni yapı · geçmişe bakmadan atama | %93,61 | 2.350 | 20,4 | %3 | %15 | %0,0 |
| C · Yeni yapı · çekirdek bölgeli dinamik plan | %95,97 | 1.056 | 20,4 | %36 | %22 | %0,0 |
| D · Yeni yapı · çekirdek bölge + hafıza | %96,27 | 926 | 20,4 | %36 | %22 | %17,1 |

- C ← B (uyumlu atama): ilk denemede teslim +2,37 puan, önlenebilir başarısızlık −%55,1
- D ← C (hafıza + brifing): +0,30 puan, önlenebilir başarısızlık −%12,3
- D ← A (yeni yapı + hafıza vs mevcut yapı): araç-gün −%8,5, ilk denemede teslim +0,14 puan
- B ← A (yeni yapı, ajansız): ilk denemede teslim -2,52 puan

**Demo anı:** gün 32 (Çar), kurye Gökhan (O02).

## Kim gitsin (Hedef 2) · gün 32: 26 kurye-gün gerekli, yerelde 24 → açık 2

| Sıra | Aday | Aldığı kümede tanıdık durak | Hafıza kapsamı (yabancı durak) | Beklenen dk | Plan maliyeti |
|---|---|---|---|---|---|
| 1 | Onur | %100 | %100 | 470 | 739,9 |
| 2 | Gökhan | %64 | %38 | 239 | 744,1 |
| 3 | Melis | %0 | %40 | 263 | 745,6 |

Önerilen: Onur, Gökhan; eşitlik: yok. Sıra: adayla kurulan planın toplam beklenen maliyeti (başarısızlık + süre); bölge tanıklığı ve hafıza kapsamı bu maliyete girer.

**Hafıza Gökhan'a 40 dk kazandırdı** (aynı kurye, aynı duraklar, aynı gün: hafızasız 352 dk → yalnız kapı ipucu 312 → hafızalı 312 dk; başarısız 0 → 0). Tek rota, tek gün: aşağıdaki dağılımla birlikte söyleyin.

## Hafıza rotayı değiştirir (Hedef 3) · kol D, aynı rota karşı-olgusu, şube-gün ortalaması

| | Hafızasız | Yalnız kapı ipucu | Hafızalı (ipucu + rota) |
|---|---|---|---|
| Toplam rota dakikası | 11.132 | 10.822 | 10.796 |
| km | 610,7 | 610,7 | 611,4 |
| Bilgiyle önlenebilir başarısız | 59,1 | 46,2 | 46,3 |
| Kapalı penceresine (öğle) denk gelen varış | 14,2 | 14,6 | 12,8 |
| Öğle arası bekleme dk | 40 | 74 | 50 |
| Kapalı kapıya gidiş | 24,1 | 22,9 | 20,9 |

Kurye türüne göre rota başına hafıza kazancı (dk; hafızasız − hafızalı; p10 / medyan / p90):

- Ödünç (7 rota-gün): ort. 57 dk (35 / 63 / 78); bunun rota payı 1,6 dk; önlenen başarısız 1,00/rota
- Yeni (17 rota-gün): ort. 48 dk (34 / 51 / 60); bunun rota payı 0,1 dk; önlenen başarısız 2,06/rota
- Yedek (77 rota-gün): ort. 21 dk (0 / 19 / 46); bunun rota payı 0,8 dk; önlenen başarısız 0,95/rota
- Kıdemli (307 rota-gün): ort. 13 dk (-2 / 9 / 32); bunun rota payı 1,4 dk; önlenen başarısız 0,46/rota

- Planda erteleme (iki kaynakla teyitli kapanış): 48 durak, bunun 8'i yanlış (açık çıktı; başarısız sayıldı).
- ETA hatası (|gerçekleşen − planlanan|, rota başına): C 126 dk → D 99 dk (hafızadaki ek servis süresi plana girdiği için).

## Teslim zamanı analizi (kayıtlardan, notsuz) · kol D, aynı rota: zaman onarımı var ↔ yok, şube-gün

| | Rotaya alınan bulgu/gün | Taşınan durak/gün | Bulgu doğruluğu (gizli gerçek) | Alıcı yok (gönderi/gün) | Tekrar ziyaret (durak/gün) | km/gün | Fazla mesai dk/gün | Beklenen rota süresi dk/gün | Taşınan duraklarda başarısız |
|---|---|---|---|---|---|---|---|---|---|
| Demo (20 gün) | 5,2 | 1,5 | %92 | -0,65 | -0,60 | -0,04 | -1,8 | -6,5 | 16 → 5 (30 durak) |
| Uzun dönem (60 gün) | 10,6 | 1,6 | %94 | -0,61 | -0,63 | -0,04 | -0,6 | -8,1 | 51 → 23 (93 durak) |

- Sert kısıt, Demo (20 gün): 408 rotada ihlal 0, yeni bant üstü 0; onarım öncesine göre en çok +0,0 dk ve +0,50 km (tolerans +0 dk / +0,5 km). Kısıt yüzünden aynı rotada kaydırılamayan 37 bulgu: aktarma 2, ertesi gün 10, akşam/teslim noktası 25 önerisi (+SMS; müdür kararı, uygulanmadı).
- Sert kısıt, Uzun dönem (60 gün): 1213 rotada ihlal 0, yeni bant üstü 0; onarım öncesine göre en çok +0,0 dk ve +0,49 km (tolerans +0 dk / +0,5 km). Kısıt yüzünden aynı rotada kaydırılamayan 197 bulgu: aktarma 12, ertesi gün 71, akşam/teslim noktası 114 önerisi (+SMS; müdür kararı, uygulanmadı).

- Ablasyon, 20 günlük geçmiş (3 seed, tam − zamansız): alıcı yok -0,97 [-1,85, -0,40]/gün, tekrar ziyaret -0,60, km -1,47, fazla mesai -7,7 dk/gün, ilk denemede +0,023 puan; aynı rota: alıcı yok -0,75, fazla mesai -1,0 [-1,3, -0,8] dk, beklenen rota süresi -6,3 [en çok -3,8] dk/gün
- Ablasyon, 60 günlük geçmiş (duyarlılık) (3 seed, tam − zamansız): alıcı yok -1,43 [-2,80, -0,05]/gün, tekrar ziyaret -1,62, km -1,67, fazla mesai +17,2 dk/gün, ilk denemede +0,073 puan; aynı rota: alıcı yok -1,47, fazla mesai -2,8 [-3,7, -2,0] dk, beklenen rota süresi -16,2 [en çok -13,9] dk/gün
- Ablasyon, tolerans +5 dk (duyarlılık) (3 seed, tam − zamansız): alıcı yok -1,25 [-1,95, -0,40]/gün, tekrar ziyaret -1,08, km +0,30, fazla mesai -2,6 dk/gün, ilk denemede +0,046 puan; aynı rota: alıcı yok -0,90, fazla mesai -0,7 [-1,3, -0,1] dk, beklenen rota süresi -4,1 [en çok -3,8] dk/gün
- Ablasyon, kısıtsız (eski) (3 seed, tam − zamansız): alıcı yok -1,90 [-2,95, -0,25]/gün, tekrar ziyaret -1,45, km -1,30, fazla mesai -14,8 dk/gün, ilk denemede +0,062 puan; aynı rota: alıcı yok -1,43, fazla mesai -0,3 [-0,6, +0,3] dk, beklenen rota süresi +0,0 [en çok +0,0] dk/gün

**Demo örneği (seçilmiş; büyüklük yukarıdaki tablo):** gün 34 (Cum), Ali, Blok 19-11 No 37 (iş yeri). Geçmiş 10 deneme: Sal 15:44 ✓, Pzt 16:35 ✓, Sal 12:22 ✗, Per 13:21 ✓, Sal 14:31 ✓, Per 15:52 ✓, Pzt 14:50 ✓, Çar 14:04 ✓, Pzt 14:59 ✓, Sal 12:53 ✗. Bulgu: 12–14: 1/3 teslim · 14–16: 6/6 teslim → 14–16 öner (güven yüksek, P = 0,999). Rota: 60. → 84. sıra, tahmini bulunamama %52 → %1, -0,08 km, rota süresi -0,2 dk. Aynı gün, aynı rastgele sayılar: zamansız 12:52 recipient_absent → zaman-farkında 14:53 delivery; rota fazla mesaisi 0 → 0 dk.

**Kısıt örneği (seçilmiş):** gün 30 (Pzt). Blok 18-26 No 6: Barış rotasında 12:02 (tahmini bulunamama %73); en iyi saat 18 sonrası ama aynı rotada kaydırılamadı: uygun saate taşımak rotayı uzatırdı; en az +0.7 dk (kural: rota uzamaz, fazla mesai yok). Öneri: Mustafa rotasına aktar (1. sıra, 09:45, %42); iki rota toplamı -0.5 dk, -0.16 km, Mustafa vardiya içinde (508 dk). Alıcıya önceden SMS. Müdür onayı gerekir.

- Dürüstlük: gerçek Beykoz verisinde başarısızlık saati ve nedeni boş; bu etki gerçek veriyle kanıtlanamaz. Simülasyonda **mekanizma** olarak gösterilir (bulunabilirlik profilleri tahminidir); büyüklüğü pilot ölçer.

## Bilgi hasadı (kol D, simülasyon)

- 20 günde 514 hedefli soru (günde ~26; 90'i ayrılan kuryeye devir teslim sorusu), 103 cevap, 98 yeni hafıza kaydı. Soruların çoğu "bildiğim sorun yok" ile döner (411); bu, adreslerin çoğunda püf noktası olmadığı içindir.

## Yeni kuryenin ilk haftası (Hedef 1) · işe alım deneyi, 12 seed × 4 yeni kurye

- İlk 6 iş gününde bilgiyle önlenebilir başarısız teslim (kurye başına): hafızasız (C) 21,5 [19,1 – 24,0], hafızalı (D) 14,0 [12,0 – 16,0]; **eşli fark (aynı kurye, aynı seed) 7,5 [5,2 – 9,8]** (%95 aralık).
- İlk hafta rota dakikası farkı (C − D): 440 [184 – 696] dk.
- Ustalaşma günü (3 günlük ortalama ≤ 1.1 × bugünkü kıdemli düzeyi (kol C kıdemli ortalaması)): C 14 · D 10. Gürültülü bir ölçü; manşette ilk hafta farkını kullanın.

## Hafızanın katkısı parça parça (demo senaryoları × 3 seed; ort. [min, max])

| Varyant | D − C ilk denemede (puan) | Önlenebilir başarısız (D/C) | Fazla mesai D − C (dk/gün) | km D − C |
|---|---|---|---|---|
| Yalnız kapı ipucu (öğle düzeltmesiyle) | +0,23 [+0,21, +0,27] | −%15,2 | -151 | +0,0 |
| + hasat | +0,25 [+0,23, +0,29] | −%16,5 | -174 | +0,0 |
| + hafıza-farkında rota | +0,27 [+0,23, +0,32] | −%13,7 | -184 | +7,0 |
| İpucu + hasat + rota + zaman analizi (yayımlanan D) | +0,26 [+0,26, +0,27] | −%13,2 | -245 | +3,8 |
| Tam − teslim zamanı analizi | +0,24 [+0,22, +0,26] | −%13,8 | -238 | +5,3 |
| Tam, sert kısıt kapalı (eski) | +0,31 [+0,23, +0,40] | −%14,3 | -272 | +7,9 |
| Tam + sabah (ayrıştırma okutmada; D − C sabahı da içerir) | +0,28 [+0,25, +0,32] | −%15,6 | -1.177 | +3,6 |

## Sabah: ayrıştırma indirme okutmasında · kol D, aynı rota bugünkü sabahla

- Şube beyanı (pilot ölçer): mesai 09:00; bugünkü süreç (indirme → kurye kendi ayrıştırır → zimmet → yükleme) 90 dk → çıkış ~10:30; ayrıştırma okutmaya gömülünce 30 dk → ~09:30; kurye başına sapma σ 10 dk. Vardiya bitişi 17:48; fazla mesai bu saatten sayılır.

- Karşı-olgu: kol D'nin aynı planı, ipuçları ve rastgele sayıları; yalnız çıkış saati bugünkü sabahla. Hafızanın katkısını ölçen deneyler (tarama, öğrenme, ablasyonun hafıza varyantları) sabahı tüm kollarda eşit tutar.

**Uzun dönem (60 iş günü)** (60 gün, şube-gün ortalaması)

| | Ayrıştırma okutmada (D) | Aynı rota, bugünkü sabahla | Fark |
|---|---|---|---|
| Ortalama çıkış | 09:30 | 10:30 | -60 dk |
| Ortalama dönüş | 18:01 | 19:03 | -62 dk |
| Vardiya bitişinden sonra dönen rota | %64 | %81 | -17 puan |
| Fazla mesai dk/gün | 933 | 1.852 | -919 |
| Başarısız teslim/gün | 89,3 | 91,2 | -1,8 |
| … alıcı yok | 38,2 | 39,8 | -1,5 |

**Demo dönemi (20 iş günü)** (20 gün, şube-gün ortalaması)

| | Ayrıştırma okutmada (D) | Aynı rota, bugünkü sabahla | Fark |
|---|---|---|---|
| Ortalama çıkış | 09:30 | 10:30 | -60 dk |
| Ortalama dönüş | 18:19 | 19:20 | -62 dk |
| Vardiya bitişinden sonra dönen rota | %69 | %84 | -15 puan |
| Fazla mesai dk/gün | 1.255 | 2.198 | -944 |
| Başarısız teslim/gün | 106,0 | 106,5 | -0,5 |
| … alıcı yok | 37,8 | 39,2 | -1,5 |

- Ablasyon (tam + sabah − tam, aynı seed, 3 seed): fazla mesai -932 dk/gün [-1.002, -863], dönüş -61 dk, alıcı yok +0,55 [-0,20, +1,05]/gün, ilk denemede +0,015 puan. Fazla mesai ve dönüş karşı-olguyla aynı; teslim tarafında fark yok (aralık sıfırı kapsıyor). **Sağlam olan fazla mesai ve dönüş; teslim etkisi belirsiz, sunumda iddia etmeyin.**

- Ekonomi: sabah kalemi günde 10.179 TL, yılda 3,1 mn TL (fazla mesai 919 dk/gün daha az → 10.050 TL; başarısız 1,8/gün daha az → 128 TL). Erken çıkışın vardiya içinde açtığı kapasite (daha az kurye ihtiyacı) para değerine çevrilmedi.

## Operasyon maliyeti (manşet, şube başına, long_term ortalaması)

**Şube başına günde 16.604 TL, yılda 5,1 milyon TL daha düşük operasyon maliyeti; başarısız teslim bugünkü düzeyde (96 → 89/gün). Ajansız aynı geçiş maliyeti günde 35.862 TL artırırdı.**

| | Bugün (sabit bölge) | Yeni yapı, ajansız | Yeni yapı + Courier Memory |
|---|---|---|---|
| Kurye/gün | 22,3 | 20,1 | 20,2 |
| Kendi bölgesinde durak payı | %97 | %63 | %96 |
| Başarısız teslim/gün | 96 | 158 | 89 |
| Fazla mesai saat/gün | 29 | 89 | 16 |
| Operasyon maliyeti TL/gün | 107.782 | 143.644 | 91.178 |
| Gönderi başına TL | 38,32 | 51,08 | 32,42 |
| Yıllık fark (bugüne göre) | — | +11,0 mn TL | −5,1 mn TL |

**Şelale (TL/gün):** Bugün (sabit bölge) 107.782 → Dinamik planlama: daha az kurye, dengeli iş yükü −7.350 → Ajansız: bölge bilgisi kaybı (başarısız teslim, fazla mesai) +43.212 → Atama Ajanı: çekirdek bölgeli plan, kurye kendi bölgesinde −41.764 → Hafıza + Brifing: bilgi kişiden adrese −523 → Sabah: ayrıştırma indirme okutmasında (kurye ayrıştırma yapmaz, erken çıkar) −10.179 → Yeni yapı + Courier Memory 91.178

**Ölçek (yıllık operasyon tasarrufu):** 1 şube → 5,1 mn TL; 10 şube → 50,8 mn TL; 100 şube → 508,1 mn TL

**LLM senaryoları:** Temkinli: tüm ajanlar Opus 5.5, önbelleksiz: 244,6 TL/gün, 8,70 kuruş/gönderi, tasarrufun %1,47'si; Optimize: önbellek + işe göre model (Hafıza/Brifing/Hasat Haiku 5.5, Atama/Orkestratör Sonnet 5.5): 18,9 TL/gün, 0,67 kuruş/gönderi, tasarrufun %0,11'si

## Ajanların maliyeti ve getirisi (temkinli senaryo, şube-gün, long_term ortalaması, 60 gün)

- Hacim: 2.812 gönderi, 20,2 kurye, 41,5 not, 88 ajan çağrısı/gün
- **LLM maliyeti: 245 TL/gün · gönderi başına 8,7 kuruş** (not başı 2,58 TL, brifing başı 1,25 TL; token kaynağı: tahmin)
- **Hafıza + Brifing'in katkısı (C'ye göre, manşet):** günde 7,0 başarısız teslim ve 62 dk fazla mesai daha az → doğrudan 1.176 TL/gün, net 932 TL/gün, **getiri 4,8×**; ayrıca 1,9 kurye-saat/gün kapasite
- Üç ajanın birlikte katkısı (B'ye göre, üst sınır): günde 68,6 başarısız teslim daha az, getiri 217×
- Şube başına yıllık: LLM 74.848 TL, net kazanç (C'ye göre) 285.192 TL
- Ölçek: 1 şube → net 0,3 milyon TL/yıl; 10 şube → net 2,9 milyon TL/yıl; 100 şube → net 28,5 milyon TL/yıl
- Model kaldıracı (bilgi): Claude Opus 5.5 245 TL/gün (8,70 kuruş/gönderi); Claude Sonnet 5.5 122 TL/gün (4,35 kuruş/gönderi); Claude Haiku 5.5 6 TL/gün (0,22 kuruş/gönderi)
- Parametreler (tahmini; şirket rakamıyla değiştirin): kurye-gün 3.500 TL, başarısız deneme 71 TL, kur 45,0, önbellek kapalı (temkinli)

## Sağlamlık

- 81 parametre kombinasyonu × 2 seed. **Yeni yapı + hafıza (D) bugüne (A) göre ilk denemede teslim: +0,00 … +0,31 puan** (medyan +0,09; kombinasyonların %78'inde ±0,15 puan içinde, %100'inde ≥ 0; seed'ler arası yayılım ort. 0,09 puan), kurye-gün -8,0 … -6,6%.
- **Hafızanın katkısı (D − C): +0,18 … +0,53 puan**, kombinasyonların %100'inde pozitif.
- ("D ≥ C ≥ B" %100: B rastgele atama olduğu için önemsiz; manşet değil.)

## Kalibrasyon

- Uygulama verisi saha verisinden türetilmiş toplu hedeflere uyumlu: **14/14**
  - Günlük teslimat gönderisi: uygulama 2.768 ✓
  - Günlük farklı teslim noktası: uygulama 2.344 ✓
  - Durak başına gönderi: uygulama 1,18 ✓
  - Mevcut yapıda günlük çalışan kurye (ek kuryeler dahil): uygulama 22,00 ✓
  - Başarısız teslim / deneme (mevcut yapı): uygulama 0,040 ✓
  - Durağın adresine önceki 1 gün içinde gidilmiş olma payı: uygulama 0,153 ✓
  - … önceki 5 gün içinde: uygulama 0,499 ✓
  - … önceki 12 gün içinde: uygulama 0,683 ✓
  - 13 günde yalnız bir kez gidilen adres payı: uygulama 0,603 ✓
  - Mevcut yapıda kurye iş yükü değişim katsayısı: uygulama 0,327 ✓
  - Dinamik planda kurye iş yükü değişim katsayısı: uygulama 0,215 ✓
  - Dinamik planda kurye-gün farkı (göreli): uygulama -0,118 ✓
  - Mevcut yapıda planlanan süresi vardiya bandında olan kurye payı: uygulama 0,531 ✓
  - Dinamik planda planlanan süresi vardiya bandında olan kurye payı: uygulama 0,918 ✓
  (Hedef değerler şirket içi toplu özettir; sunumda gösterilmez.)

## Kurye–bölge uyumu tahmincisi

- Gizli gerçek beceriyle sıra korelasyonu 0,62 (bölgeden arındırılmamış ham oran 0,59).

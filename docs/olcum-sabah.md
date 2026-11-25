# Ölçüm: sabah akışı (Faz 5)

> Uygulama verisi · 1 aylık geçmiş · bu varsayımlar altında. Sabah süreleri şube sahibinin saha bilgisidir (VARSAYIM); büyüklüğü pilot ölçer. Eski = Faz 4 yayımı, yeni = Faz 5 yayımı (`izin_dalgasi+ayrilma_yeni+odunc_kurye+hacim_soku-s42-316f18d7`). Rakamlar `docs/sunum_rakamlari.md` ile aynı kaynaktan.

## Ne değişti, nasıl ölçüldü

- **Model:** mesai 09:00. Kurye mesai başı + sabah süresinden sonra çıkar: bugünkü süreç (okutmalı indirme → kurye kendi gönderilerini ayrıştırır → zimmet → yükleme) 90 dk, ayrıştırma indirme okutmasına gömülünce (kurye rafını zimmetler) 30 dk; kurye başına sapma σ 10 dk (kollar arası ortak). Eski modelde herkes 09:00'da çıkıyordu.
- **Fazla mesai** artık vardiya bitişinden (17:48) sayılır; geç çıkış da fazla mesai yaratır. Eskiden rota süresi bant üstünü (528 dk) aşınca sayılıyordu (09:00 çıkışta aynı şey).
- **Kollar:** A, B, C bugünkü süreçle (~10:30), D (Courier Memory) ayrıştırmasız (~09:30) çıkar.
- **Sabahın katkısı üç yoldan ölçüldü:** (1) kol D'nin aynı rotası, aynı ipuçları ve rastgele sayılarla bugünkü sabahla yürütülür (karşı-olgu); (2) ablasyonda `full_morning − tam` (3 seed); (3) ekonomide ayrı şelale kalemi.
- **Hafıza iddiaları sabahtan ayrık:** tarama, Hedef 1 ve ablasyonun hafıza varyantları sabahı tüm kollarda eşit tutar.
- **Kalibrasyon:** çıkış 10:30'a çekilince başarısız teslim oranı 0,044 çıktı (hedef 0,038, tolerans %15) → ofisin 18:00 sonrası bulunamama varsayımı 0,15 → 0,06. Sonuç 14/14 (başarısız oranı 0,041 → 0,040).

## 1. Sabahın katkısı: aynı rota, aynı gün, yalnız çıkış saati farklı

**Uzun dönem (60 iş günü)** (60 gün, şube-gün ortalaması)

| | Bugünkü sabah (aynı rota) | Ayrıştırma okutmada | Fark |
|---|---|---|---|
| Ortalama çıkış | 10:30 | 09:30 | -60 dk |
| Ortalama dönüş | 19:03 | 18:01 | -62 dk |
| Vardiya bitişinden sonra dönen rota | %81 | %64 | -17 puan |
| Fazla mesai dk/gün | 1.852 | 933 | -919 |
| Başarısız teslim/gün | 91,2 | 89,3 | -1,8 |
| … alıcı yok | 39,8 | 38,2 | -1,5 |
| … bilgiyle önlenebilir | 30,3 | 30,0 | -0,3 |

**Demo dönemi (20 iş günü; kampanya, izin dalgası, ödünç kurye)** (20 gün, şube-gün ortalaması)

| | Bugünkü sabah (aynı rota) | Ayrıştırma okutmada | Fark |
|---|---|---|---|
| Ortalama çıkış | 10:30 | 09:30 | -60 dk |
| Ortalama dönüş | 19:20 | 18:19 | -62 dk |
| Vardiya bitişinden sonra dönen rota | %84 | %69 | -15 puan |
| Fazla mesai dk/gün | 2.198 | 1.255 | -944 |
| Başarısız teslim/gün | 106,5 | 106,0 | -0,5 |
| … alıcı yok | 39,2 | 37,8 | -1,5 |
| … bilgiyle önlenebilir | 45,2 | 46,3 | +1,1 |

**Ablasyon** (`full_morning − tam`, aynı seed, 3 seed × 4 senaryo; ort. [en düşük … en yüksek]): fazla mesai -932 dk/gün [-1.002 … -863], dönüş -61 dk, alıcı yok +0,55/gün, ilk denemede +0,015 puan. Fazla mesai ve dönüş her seed'de aynı yönde ve karşı-olgu kadar. Teslim tarafı farklı: alıcı yok [-0,20 … +1,05], yani ablasyonda erken çıkışın teslime etkisi görülmüyor (iki ayrı dünya: hafıza farklı birikir, plan kendi çıkışına göre kurulur). **Sağlam olan fazla mesai ve dönüş saati; teslim etkisi belirsiz.**

## 2. Para: operasyon maliyeti (uzun dönem, şube başına)

| Şelale adımı | Eski TL/gün | Yeni TL/gün |
|---|---|---|
| Bugün (sabit bölge) | 96.585 | 107.782 |
| Dinamik planlama: daha az kurye, dengeli iş yükü | -7.583 | -7.350 |
| Ajansız: bölge bilgisi kaybı (başarısız teslim, fazla mesai) | 35.919 | 43.212 |
| Atama Ajanı: çekirdek bölgeli plan, kurye kendi bölgesinde | -36.039 | -41.764 |
| Hafıza + Brifing: bilgi kişiden adrese | -1.315 | -539 |
| Sabah: ayrıştırma indirme okutmasında (kurye ayrıştırma yapmaz, erken çıkar) | — | -10.179 |
| Yeni yapı + Courier Memory | 87.567 | 91.162 |

- **Manşet:** günde 9.018 → **16.620 TL**, yılda 2,8 → **5,1 mn TL** (bugüne göre). Başarısız teslim/gün: bugün 96, ajansız 158, Courier Memory 89.
- **Sabah kalemi:** günde 10.179 TL, yılda 3,1 mn TL (fazla mesai 919 dk/gün → 10.050 TL; başarısız -1,8/gün → 128 TL). Kalemin neredeyse tamamı fazla mesaiden; belirsiz teslim etkisi paraya neredeyse girmiyor.
- **Hafızanın getirisi** (yalnız hafıza, sabah hariç): 7,4× → 5,1×; LLM maliyetinin tasarrufa oranı %2,6 → %1,4. Hafızanın kalemi küçüldü (-1.315 → -539 TL/gün): artık sabah hariç ölçülüyor (D bugünkü sabahla ↔ C) ve 10:30 çıkışlı dünyada D ile C'nin fazla mesai farkı daraldı.
- Bugünün (A) maliyeti de arttı: model artık 10:30 çıkışın fazla mesaisini sayıyor. Manşetin büyümesinin bir kısmı bu düzeltmeden, bir kısmı sabah kaleminden gelir; şelale ikisini ayırır. Erken çıkışın vardiya içinde açtığı kapasite (daha az kurye ihtiyacı) para değerine çevrilmedi.

## 3. Dünyanın yeni hâli (uzun dönem, eski → yeni)

| Kol | Çıkış | Dönüş | İlk denemede teslim | Fazla mesai saat/gün | Alıcı yok/gün | Bilgiyle önlenebilir (60 gün) |
|---|---|---|---|---|---|---|
| A · Mevcut yapı · sabit bölge | 10:30 | 18:09 | %96,58 → %96,58 | 12,3 → 29,4 | 42,9 → 41,7 | 1.981 → 2.046 |
| B · Yeni yapı · geçmişe bakmadan atama | 10:30 | 22:15 | %94,07 → %94,38 | 59,5 → 89,0 | 51,8 → 42,8 | 5.645 → 5.651 |
| C · Yeni yapı · çekirdek bölgeli dinamik plan | 10:31 | 19:13 | %96,46 → %96,51 | 11,9 → 31,9 | 41,1 → 40,0 | 2.243 → 2.221 |
| D · Yeni yapı · çekirdek bölge + hafıza | 09:30 | 18:04 | %96,74 → %96,82 | 10,2 → 15,6 | 39,8 → 38,2 | 1.847 → 1.799 |

Rota süresi ve planlanan vardiya bandı ölçüleri (kalibrasyon hedefleri) değişmedi; değişen, teslimin günün hangi saatine düştüğü ve fazla mesainin tanımı.

## 4. Hafıza iddiaları korunuyor mu (sabah eşit)

| Ölçü | Eski | Yeni |
|---|---|---|
| Tarama: hafızanın katkısı D − C (puan) | +0,09 … +0,45 | +0,18 … +0,53 |
| Tarama: D − A (puan) | -0,09 … +0,21 | +0,00 … +0,31 |
| Tarama: D − C pozitif kombinasyon | %100 | %100 |
| Tarama: D − A ±0,15 içinde | %88 | %78 |
| Hedef 1: ilk hafta eşli fark (önlenebilir) | 6,2 [4,1–8,4] | 7,5 [5,2–9,8] |
| Hedef 1: kıdemli düzeyine (gün) | C 14 → D 9 | C 14 → D 10 |
| Ablasyon hint_only: önlenebilir D/C | -15,4% | -15,2% |
| Ablasyon tam: önlenebilir D/C | -15,4% | -13,2% |

Bu deneylerde tüm kollar 10:30'da çıkar (bugünkü sabah); dünya Faz 4'ünkünden farklı olduğu için rakamlar da kayar. Yön korunuyor: D − C her kombinasyonda pozitif, ilk hafta farkı büyüdü. Yeni kuryenin kıdemli düzeyine ulaştığı gün (3 günlük ortalama ≤ 1,1 × kıdemli) D'de 9 → 10; bu eşik ölçüsü sınırda hassastır (zaman onarımı düzeltmesinden önceki ara koşuda 13 çıkmıştı, D'nin eğrisi 10–12. günlerde eşiğin %4–5 üstündeydi). Sunumda ana rakam ilk hafta farkı. Tarama D − A aralığı yukarı kaydı (+0,00 … +0,31 puan): D hiçbir kombinasyonda A'nın altında değil.

## Sınırlar

- 10:30 / 09:30 ve kurye sapması saha bilgisi ve VARSAYIM'dır; ölçülmüş değildir. Pilotun ilk ölçüsü şube çıkış saati olmalı (zimmet okutması zaman damgası).
- Karşı-olgu D'nin 09:30'a göre kurulmuş planını 10:30'da yürütür; bugünkü süreçte plan 10:30'a göre kurulurdu. Teslim tarafındaki karşı-olgu farkının (alıcı yok) bir kısmı bu uyumsuzluktan olabilir; ablasyon (plan kendi çıkışına göre) teslimde fark göstermiyor. Fazla mesai ve dönüş iki ölçümde de aynı.
- Ayrıştırmanın okutmaya gömülmesi bir süreç değişikliğidir (ekran/etiket, raf düzeni); ajan planı, raf ve yükleme sırasını ve istisnaları yönetir, paket başına LLM yoktur.
- Erken çıkışın yarattığı kapasite (aynı işi daha az kuryeyle) modellenmedi; kazanç fazla mesai ve teslim saatinden gelir.

# Simülasyon raporu: leave_wave+turnover+borrowed_courier+volume_shock-s42-00e214fe

> **Uygulama verisi · 1 aylık geçmiş.** Rakamlar bu varsayımlar altında geçerlidir; mekanizmayı gösterir, etkinin büyüklüğünü kanıtlamaz.

Senaryolar: leave_wave, turnover, borrowed_courier, volume_shock · seed 42 · 20 gün ısınma + 20 gün değerlendirme

| Kol | İlk denemede teslim | Bilgiyle önlenebilir başarısızlık | Kurye/gün | Km/gün | Vardiya bandında | Yabancı durak payı | Hafıza kapsamı |
|---|---|---|---|---|---|---|---|
| A · Mevcut yapı · sabit bölge | %96,13 | 922 | 22.3 | 601 | %30 | %4,6 | %0,0 |
| B · Yeni yapı · geçmişe bakmadan atama | %93,61 | 2350 | 20.4 | 606 | %3 | %63,4 | %0,0 |
| C · Yeni yapı · çekirdek bölgeli dinamik plan | %95,97 | 1056 | 20.4 | 608 | %36 | %6,0 | %0,0 |
| D · Yeni yapı · çekirdek bölge + hafıza | %96,27 | 926 | 20.4 | 611 | %36 | %5,8 | %17,1 |

## Farklar
- Uyuma göre atama (C), geçmişe bakmadan atamaya (B) göre: ilk denemede teslim +2.37 puan, önlenebilir başarısızlık -55.1%.
- Hafıza (D), uyumlu atamanın (C) üstüne: +0.30 puan, önlenebilir başarısızlık -12.3%.
- Yeni yapı (D), mevcut yapıya (A) göre: araç-gün -8.5%, km +1.7%, ilk denemede teslim +0.14 puan.

## Uyum tahmincisi doğrulaması
- Tahmin edilen kurye etkisi ile gizli gerçek beceri arasındaki sıra korelasyonu: 0.625 (bölge zorluğundan arındırılmamış ham oran: 0.591; n = 28).

## Demo anı
- Gün 32 (değerlendirme günü 13), kurye O02. Hafıza bu kuryeye +40 dk kazandırdı (aynı rota, hafızasız 352 → hafızalı 312 dk).

## Hafıza rotayı nasıl değiştiriyor (kol D, aynı rota karşı-olgusu, gün başına)
| | Hafızasız | Yalnız kapı ipucu | Hafızalı (ipucu + rota) |
|---|---|---|---|
| Toplam rota dk | 11132.5 | 10821.6 | 10795.6 |
| km | 610.7 | 610.7 | 611.4 |
| Önlenebilir başarısız | 59.1 | 46.2 | 46.3 |
| Öğle arasına denk gelen varış | 14.2 | 14.6 | 12.8 |
| Kapalı kapıya gidiş | 24.1 | 22.9 | 20.9 |

## Teslim zamanı analizi (kol D, kayıtlardan; aynı rota zaman onarımı var ↔ yok, gün başına)
- Rotaya alınan bulgu 5,2/gün, taşınan durak 1,5/gün; bulguların gizli gerçekle uyumu %92.
- Alıcı yok -0.65 gönderi/gün, tekrar ziyaret -0.60 durak/gün, km -0.04, fazla mesai -1.8 dk/gün.
- Taşınan 30 durakta başarısız: zamansız 16 → zaman-farkında 5.
- Sert kısıt (Faz 2c): 408 rotada ihlal 0, yeni bant üstü 0; onarım öncesine göre en çok +0.0 dk, +0.50 km (tolerans +0 dk / +0.5 km). Planlanan süre farkı -0.1 dk/gün.
- Kısıt yüzünden kaydırılamayan 37 bulgu: evening_delivery_point 25, next_day 10, transfer 2 (müdür kararı; uygulanmadı).

# Simülasyon raporu: long_term-s42-78a6f8c3

> **Uygulama verisi · 1 aylık geçmiş.** Rakamlar bu varsayımlar altında geçerlidir; mekanizmayı gösterir, etkinin büyüklüğünü kanıtlamaz.

Senaryolar: long_term · seed 42 · 20 gün ısınma + 60 gün değerlendirme

| Kol | İlk denemede teslim | Bilgiyle önlenebilir başarısızlık | Kurye/gün | Km/gün | Vardiya bandında | Yabancı durak payı | Hafıza kapsamı |
|---|---|---|---|---|---|---|---|
| A · Mevcut yapı · sabit bölge | %96,58 | 2046 | 22.3 | 596 | %33 | %2,9 | %0,0 |
| B · Yeni yapı · geçmişe bakmadan atama | %94,38 | 5651 | 20.1 | 602 | %5 | %37,5 | %0,0 |
| C · Yeni yapı · çekirdek bölgeli dinamik plan | %96,51 | 2221 | 20.1 | 604 | %46 | %4,0 | %0,0 |
| D · Yeni yapı · çekirdek bölge + hafıza | %96,82 | 1799 | 20.2 | 605 | %43 | %3,9 | %21,5 |

## Farklar
- Uyuma göre atama (C), geçmişe bakmadan atamaya (B) göre: ilk denemede teslim +2.13 puan, önlenebilir başarısızlık -60.7%.
- Hafıza (D), uyumlu atamanın (C) üstüne: +0.31 puan, önlenebilir başarısızlık -19.0%.
- Yeni yapı (D), mevcut yapıya (A) göre: araç-gün -9.4%, km +1.6%, ilk denemede teslim +0.23 puan.

## Uyum tahmincisi doğrulaması
- Tahmin edilen kurye etkisi ile gizli gerçek beceri arasındaki sıra korelasyonu: 0.698 (bölge zorluğundan arındırılmamış ham oran: 0.559; n = 30).

## Demo anı
- Gün 38 (değerlendirme günü 19), kurye O03. Hafıza bu kuryeye +142 dk kazandırdı (aynı rota, hafızasız 880 → hafızalı 738 dk).

## Hafıza rotayı nasıl değiştiriyor (kol D, aynı rota karşı-olgusu, gün başına)
| | Hafızasız | Yalnız kapı ipucu | Hafızalı (ipucu + rota) |
|---|---|---|---|
| Toplam rota dk | 10736.5 | 10352.4 | 10320.8 |
| km | 604.4 | 604.4 | 605.3 |
| Önlenebilir başarısız | 44.1 | 29.9 | 30.0 |
| Öğle arasına denk gelen varış | 14.3 | 14.5 | 12.1 |
| Kapalı kapıya gidiş | 18.0 | 15.9 | 15.1 |

## Teslim zamanı analizi (kol D, kayıtlardan; aynı rota zaman onarımı var ↔ yok, gün başına)
- Rotaya alınan bulgu 10,6/gün, taşınan durak 1,6/gün; bulguların gizli gerçekle uyumu %94.
- Alıcı yok -0.61 gönderi/gün, tekrar ziyaret -0.63 durak/gün, km -0.04, fazla mesai -0.6 dk/gün.
- Taşınan 93 durakta başarısız: zamansız 51 → zaman-farkında 23.
- Sert kısıt (Faz 2c): 1213 rotada ihlal 0, yeni bant üstü 0; onarım öncesine göre en çok +0.0 dk, +0.49 km (tolerans +0 dk / +0.5 km). Planlanan süre farkı -0.1 dk/gün.
- Kısıt yüzünden kaydırılamayan 197 bulgu: evening_delivery_point 114, next_day 71, transfer 12 (müdür kararı; uygulanmadı).
